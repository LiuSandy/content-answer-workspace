"""分支级滚动摘要持久化（roadmap R4）。

唯一键 (chat_id, branch_root_message_id)：同一分支共享一份摘要；
covered_message_ids + last_covered_message_id 记录摘要覆盖到哪条消息，
version 乐观版本号用于 compare-and-swap，旧异步任务不得覆盖新摘要。
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.database import Base


class BranchSummary(Base):
    """分支滚动摘要；供 ContextComposer 在超预算时注入，替代被裁剪的旧消息。"""

    __tablename__ = "branch_summaries"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    chat_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chats.id", ondelete="CASCADE"), nullable=False
    )
    # 分支根消息 ID（get_message_path 的 path[0].id）
    branch_root_message_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # 摘要已覆盖的消息 ID（JSONB 数组），用于增量摘要
    covered_message_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    last_covered_message_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    # 乐观版本号；更新采用 compare-and-swap，旧任务晚完成不得覆盖
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "chat_id",
            "branch_root_message_id",
            name="uq_branch_summaries_chat_root",
        ),
        Index("ix_branch_summaries_chat_root", "chat_id", "branch_root_message_id"),
    )
