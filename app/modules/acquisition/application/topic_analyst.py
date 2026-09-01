"""TopicAnalystService：Top-N LLM 评估与个性化匹配（roadmap R8）。

- 扫描后对前 N 条未评估机会调用 LLM 打分。
- 注入 active 用户记忆做个性化匹配。
- 失败静默降级，保留规则分。
- 手动重评幂等（已评估的也可再评）。
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from sqlalchemy import select, update

from app.modules.acquisition.adapters.db.opportunity_models import OpportunityFeedModel
from .llm import get_acquisition_llm

logger = logging.getLogger(__name__)


class TopicAnalystService:
    def __init__(self, session):
        self.session = session

    async def evaluate_top_n(
        self,
        workspace_id: str = "default",
        top_n: int = 5,
        interest_tags: list[str] | None = None,
    ) -> int:
        """对前 N 条未评估机会做 LLM 个性化评估；返回评估条数。"""
        stmt = (
            select(OpportunityFeedModel)
            .where(
                OpportunityFeedModel.workspace_id == workspace_id,
                OpportunityFeedModel.llm_evaluated.is_(None),
            )
            .order_by(OpportunityFeedModel.opportunity_score.desc())
            .limit(top_n)
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        if not rows:
            return 0

        active_memories = await self._get_active_memories(workspace_id)
        tags = interest_tags or []
        count = 0

        for row in rows:
            try:
                llm_score, llm_reason, user_match = await self._evaluate_one(
                    row.question_title, tags, active_memories
                )
                row.llm_score = llm_score
                row.llm_reason = llm_reason
                row.user_match_reason = user_match
                row.llm_evaluated = "true"
                row.llm_evaluated_at = datetime.now(timezone.utc)
                count += 1
            except Exception as e:
                logger.warning("Topic evaluation failed for %s: %s", row.id, e)
                row.llm_evaluated = "false"
            await self.session.commit()

        return count

    async def re_evaluate(self, opportunity_id: str) -> dict | None:
        """手动重评某条机会（幂等）。"""
        row = await self.session.get(OpportunityFeedModel, opportunity_id)
        if not row:
            return None

        active_memories = await self._get_active_memories(row.workspace_id)
        try:
            llm_score, llm_reason, user_match = await self._evaluate_one(
                row.question_title, [], active_memories
            )
            row.llm_score = llm_score
            row.llm_reason = llm_reason
            row.user_match_reason = user_match
            row.llm_evaluated = "true"
            row.llm_evaluated_at = datetime.now(timezone.utc)
            await self.session.commit()
            return {"id": row.id, "llmScore": llm_score, "llmReason": llm_reason, "userMatchReason": user_match}
        except Exception as e:
            logger.warning("Re-evaluation failed for %s: %s", opportunity_id, e)
            row.llm_evaluated = "false"
            await self.session.commit()
            return None

    async def _evaluate_one(
        self, title: str, tags: list[str], memories: list[dict]
    ) -> tuple[float, str, str]:
        from app.platform.prompts.registry import prompt_registry
        mem_list = "\n".join(
            f"- {m.get('content')}" for m in memories[:5]
        ) or "无已知偏好"

        rendered = prompt_registry.render(
            "analysis.topic_evaluation",
            question_title=title,
            interest_tags=json.dumps(tags, ensure_ascii=False),
            user_memories=mem_list,
        )
        llm = get_acquisition_llm()
        raw = await llm.generate_structured(
            rendered.to_llm_request(),
        ) or ""
        return self._parse_evaluation(raw)

    async def _get_active_memories(self, workspace_id: str) -> list[dict]:
        from app.platform.database.session import get_session_factory
        factory = get_session_factory()
        async with factory() as session:
            stmt = (
                select("content", "memory_type")
                .where("workspace_id", workspace_id, "status", "active")
                .limit(20)
            )
            rows = []
            try:
                from app.modules.memory.adapters.db.models import UserMemoryModel
                stmt = (
                    select(UserMemoryModel.content, UserMemoryModel.memory_type)
                    .where(
                        UserMemoryModel.workspace_id == workspace_id,
                        UserMemoryModel.status == "active",
                    )
                    .limit(20)
                )
                result = await session.execute(stmt)
                rows = [{"content": r[0], "memory_type": r[1]} for r in result.all()]
            except Exception:
                pass
            return rows

    @staticmethod
    def _parse_evaluation(raw: str) -> tuple[float, str, str]:
        try:
            data = json.loads(raw)
            score = float(data.get("score", 50))
            reason = str(data.get("reason", ""))[:500]
            user_match = str(data.get("userMatch", ""))[:300]
            return score, reason, user_match
        except (json.JSONDecodeError, ValueError):
            return 50.0, "评估失败，保留规则分", ""
