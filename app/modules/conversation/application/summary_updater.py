"""分支级滚动摘要更新（roadmap R4）。

SummaryUpdater 只负责「覆盖哪些消息、增量摘要、乐观版本 CAS」；LLM 摘要函数
由调用方注入，便于测试与替换。旧异步任务晚完成时因版本过期被拒绝，不覆盖新摘要。
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Awaitable, Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.conversation.adapters.db.chats import Message
from app.modules.conversation.adapters.db.summaries import BranchSummary

logger = logging.getLogger(__name__)


class SummaryConflictError(Exception):
    """摘要 CAS 冲突：目标版本已过期，写入被拒绝。"""


@dataclass
class SummaryUpdateResult:
    summary: str
    covered_message_ids: list[str]
    version: int
    stale: bool = False


class SummaryUpdater:
    def __init__(self, session: AsyncSession, summarizer: Callable[[str], Awaitable[str]]) -> None:
        self._session = session
        self._summarizer = summarizer

    async def get(
        self,
        chat_id: uuid.UUID,
        branch_root_message_id: uuid.UUID | None,
    ) -> BranchSummary | None:
        stmt = select(BranchSummary).where(
            BranchSummary.chat_id == chat_id,
            BranchSummary.branch_root_message_id == branch_root_message_id,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def update_incremental(
        self,
        chat_id: uuid.UUID,
        branch_root_message_id: uuid.UUID | None,
        branch_messages: list[Message],
        expected_version: int,
    ) -> SummaryUpdateResult:
        """增量更新摘要：只摘要自上次覆盖以来的新消息，CAS 写回。

        expected_version：调用方读取到的版本；实际版本更大则视为过期（stale=True），
        不写库，由调用方决定重试或放弃。
        """
        existing = await self.get(chat_id, branch_root_message_id)
        current_version = existing.version if existing else 0
        if existing and current_version != expected_version:
            return SummaryUpdateResult(
                summary=existing.summary,
                covered_message_ids=list(existing.covered_message_ids or []),
                version=current_version,
                stale=True,
            )

        covered = set(existing.covered_message_ids or []) if existing else set()
        new_messages = [m for m in branch_messages if str(m.id) not in covered]
        if not new_messages:
            return SummaryUpdateResult(
                summary=existing.summary if existing else "",
                covered_message_ids=list(covered),
                version=current_version,
            )

        new_content = "\n".join(
            f"{m.role}: {m.content or ''}" for m in new_messages if m.content
        )
        try:
            new_summary = await self._summarizer(new_content)
        except Exception as e:  # noqa: BLE001 - 摘要失败静默降级，不阻断对话
            logger.warning("Branch summary generation failed: %s", e)
            new_summary = existing.summary if existing else ""

        merged = f"{existing.summary}\n{new_summary}".strip() if existing and existing.summary else new_summary
        new_covered = sorted(covered | {str(m.id) for m in new_messages})
        last_id = new_messages[-1].id

        if existing:
            existing.summary = merged
            existing.covered_message_ids = new_covered
            existing.last_covered_message_id = last_id
            existing.version = current_version + 1
        else:
            existing = BranchSummary(
                chat_id=chat_id,
                branch_root_message_id=branch_root_message_id,
                summary=merged,
                covered_message_ids=new_covered,
                last_covered_message_id=last_id,
                version=1,
            )
            self._session.add(existing)
        await self._session.commit()
        await self._session.refresh(existing)

        return SummaryUpdateResult(
            summary=existing.summary,
            covered_message_ids=list(existing.covered_message_ids or []),
            version=existing.version,
        )
