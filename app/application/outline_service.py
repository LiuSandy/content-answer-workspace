"""OutlineService：观点采访与大纲生命周期（roadmap R6）。

- 大纲与观点快照存入 AIOperation.input_metadata，operation type 为 outline。
- 每个 section 具有稳定 id/order/heading/keyPoints/wordCountEstimate。
- confirmed 快照不可被旧 lock_version 覆盖。
"""
from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..domain.dto import (
    AgentError,
    ChatResponsePayload,
    LLMMessage,
)
from ..errors import DocumentConflictError
from ..persistence.models.content import SourceItem
from ..persistence.models.documents import AIOperation, AnswerDocument

logger = logging.getLogger(__name__)

_default_sections: list[dict] = []


@dataclass
class GenerateOutlineResult:
    operation_id: str
    viewpoint_questions: list[str] | None
    outline: list[dict]
    status: str  # draft | confirmed


@dataclass
class OutlineError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


class OutlineService:
    def __init__(self, session: AsyncSession):
        self._session = session

    # ── 生成 ──────────────────────────────────────────────────────────────

    async def generate(
        self,
        document_id: uuid.UUID,
        source_item_id: uuid.UUID,
        workspace_id: str,
        expected_lock_version: int,
        viewpoint_answers: dict[str, str] | None = None,
    ) -> GenerateOutlineResult:
        doc = await self._session.get(AnswerDocument, document_id)
        if not doc:
            raise OutlineError("not_found", "Document not found")
        if doc.lock_version != expected_lock_version:
            raise DocumentConflictError(
                expected=expected_lock_version, actual=doc.lock_version
            )

        source = await self._session.get(SourceItem, source_item_id)
        source_content = source.content or "" if source else ""

        questions, sections = await self._llm_generate(
            source_content, viewpoint_answers
        )

        operation = AIOperation(
            document_id=document_id,
            operation_type="outline",
            status="completed",
            input_metadata={
                "outlineStatus": "draft",
                "viewpointQuestions": questions,
                "viewpointAnswers": viewpoint_answers or {},
                "outline": sections,
                "sourceItemId": str(source_item_id),
                "documentLockVersion": expected_lock_version,
            },
            completed_at=datetime.now(timezone.utc),
        )
        self._session.add(operation)
        await self._session.commit()
        await self._session.refresh(operation)

        return GenerateOutlineResult(
            operation_id=str(operation.id),
            viewpoint_questions=questions,
            outline=sections,
            status="draft",
        )

    # ── 获取当前大纲 ──────────────────────────────────────────────────────

    async def get_current(self, document_id: uuid.UUID) -> GenerateOutlineResult | None:
        stmt = (
            select(AIOperation)
            .where(
                AIOperation.document_id == document_id,
                AIOperation.operation_type == "outline",
            )
            .order_by(AIOperation.created_at.desc())
            .limit(1)
        )
        op = (await self._session.execute(stmt)).scalar_one_or_none()
        if not op:
            return None
        meta = op.input_metadata or {}
        return GenerateOutlineResult(
            operation_id=str(op.id),
            viewpoint_questions=meta.get("viewpointQuestions"),
            outline=meta.get("outline") or [],
            status=meta.get("outlineStatus", "draft"),
        )

    # ── 编辑大纲 ────────────────────────────────────────────────────────

    async def update(
        self,
        document_id: uuid.UUID,
        sections: list[dict],
        viewpoint_answers: dict[str, str] | None,
        expected_lock_version: int,
    ) -> GenerateOutlineResult:
        current = await self._get_latest_op(document_id)
        if not current:
            raise OutlineError("not_found", "No outline to update")
        await self._check_confirmed_not_stale(
            current, document_id, expected_lock_version
        )

        current.input_metadata = {
            **(current.input_metadata or {}),
            "outline": sections,
            "viewpointAnswers": viewpoint_answers or {},
            "documentLockVersion": expected_lock_version,
        }
        await self._session.commit()

        return GenerateOutlineResult(
            operation_id=str(current.id),
            viewpoint_questions=current.input_metadata.get("viewpointQuestions"),
            outline=sections,
            status=current.input_metadata.get("outlineStatus", "draft"),
        )

    # ── 重生成 ──────────────────────────────────────────────────────────

    async def regenerate(
        self,
        document_id: uuid.UUID,
        source_item_id: uuid.UUID,
        workspace_id: str,
        expected_lock_version: int,
        viewpoint_answers: dict[str, str] | None = None,
    ) -> GenerateOutlineResult:
        existing = await self._get_latest_op(document_id)
        if existing:
            await self._check_confirmed_not_stale(
                existing, document_id, expected_lock_version
            )

        return await self.generate(
            document_id, source_item_id, workspace_id, expected_lock_version,
            viewpoint_answers=viewpoint_answers,
        )

    # ── 确认 ────────────────────────────────────────────────────────────

    async def confirm(
        self,
        document_id: uuid.UUID,
        expected_lock_version: int,
    ) -> GenerateOutlineResult:
        op = await self._get_latest_op(document_id)
        if not op:
            raise OutlineError("not_found", "No outline to confirm")

        doc = await self._session.get(AnswerDocument, document_id)
        if not doc:
            raise OutlineError("not_found", "Document not found")
        if doc.lock_version != expected_lock_version:
            raise DocumentConflictError(
                expected=expected_lock_version, actual=doc.lock_version
            )

        meta = op.input_metadata or {}
        if meta.get("outlineStatus") == "confirmed":
            raise OutlineError("already_confirmed", "Outline already confirmed")

        op.input_metadata = {
            **meta,
            "outlineStatus": "confirmed",
            "documentLockVersion": expected_lock_version,
        }
        await self._session.commit()

        return GenerateOutlineResult(
            operation_id=str(op.id),
            viewpoint_questions=meta.get("viewpointQuestions"),
            outline=meta.get("outline") or [],
            status="confirmed",
        )

    # ── 内部 ────────────────────────────────────────────────────────────

    async def _get_latest_op(self, document_id: uuid.UUID) -> AIOperation | None:
        stmt = (
            select(AIOperation)
            .where(
                AIOperation.document_id == document_id,
                AIOperation.operation_type == "outline",
            )
            .order_by(AIOperation.created_at.desc())
            .limit(1)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def _check_confirmed_not_stale(
        self, op: AIOperation, document_id: uuid.UUID, expected_lock_version: int
    ) -> None:
        meta = op.input_metadata or {}
        if meta.get("outlineStatus") == "confirmed":
            doc = await self._session.get(AnswerDocument, document_id)
            if doc and doc.lock_version != expected_lock_version:
                raise DocumentConflictError(
                    expected=expected_lock_version, actual=doc.lock_version,
                )

    async def _llm_generate(
        self, source_content: str, viewpoint_answers: dict[str, str] | None
    ) -> tuple[list[str] | None, list[dict]]:
        from ..prompts.registry import prompt_registry

        extra = ""
        if viewpoint_answers:
            answers_text = "\n".join(
                f"  Q: {q}\n  A: {a}" for q, a in viewpoint_answers.items()
            )
            extra = f"\n\n【用户对采访问题的回答】\n{answers_text}"

        rendered = prompt_registry.render(
            "outline.answer_outline",
            source_content=source_content + extra,
        )
        msgs = rendered.to_llm_request().messages
        system_prompt = msgs[0].content if msgs else ""
        user_prompt = msgs[1].content if len(msgs) > 1 else ""

        from .agent.adapters import DeepSeekLLMAdapter
        llm = DeepSeekLLMAdapter()
        raw = await llm.analyze(system_prompt, user_prompt)
        result = self._parse_outline_json(raw)
        return result.get("viewpointQuestions"), result.get("outline") or []

    @staticmethod
    def _parse_outline_json(raw: str) -> dict:
        try:
            if "```json" in raw:
                raw = raw.split("```json")[1].split("```")[0]
            elif "```" in raw:
                raw = raw.split("```")[1].split("```")[0]
            data = json.loads(raw)
        except (json.JSONDecodeError, IndexError):
            return {"viewpoint_questions": None, "outline": []}
        return data

    @staticmethod
    def _section_id(existing: list[dict], idx: int) -> str:
        for s in existing:
            if s.get("order") == idx + 1:
                return s["id"]
        return str(uuid.uuid4())
