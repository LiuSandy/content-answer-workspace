"""UserMemory 持久化模型；spec 3.4 节。

使用 pgvector 存储 embedding，支持显式/隐式/工作习惯三类记忆。
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

try:
    from pgvector.sqlalchemy import Vector
    _HAS_PGVECTOR = True
except Exception:
    _HAS_PGVECTOR = False
    Vector = None  # type: ignore

from .. import Base


class UserMemoryModel(Base):
    """用户长期记忆；spec 3.4 节。"""

    __tablename__ = "user_memories"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[str] = mapped_column(String(100), nullable=False)
    # explicit / implicit / work_pattern
    memory_type: Mapped[str] = mapped_column(String(20), nullable=False)
    # general / conversation / answer_format / writing_style / audience /
    # platform / source_preference / workflow
    memory_scope: Mapped[str] = mapped_column(
        String(32), nullable=False, default="general", server_default="general"
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # 向量化存储；若 pgvector 不可用退化为 null
    if _HAS_PGVECTOR:
        embedding: Mapped[list | None] = mapped_column(
            Vector(1536), nullable=True
        )
    else:
        embedding: Mapped[dict | None] = mapped_column(
            "embedding", nullable=True, type_=None
        )
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.8)
    # active / pending_confirmation / rejected（roadmap R5）
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    # 显式记忆的证据来源（原始语句、链接等），供前端 trace 详情
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 来源 session_id 或 behavior event
    source: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_activated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    activation_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        Index("ix_user_memories_workspace_type", "workspace_id", "memory_type"),
        Index("ix_user_memories_workspace_status", "workspace_id", "status"),
        Index(
            "ix_user_memories_workspace_status_scope",
            "workspace_id",
            "status",
            "memory_scope",
        ),
    )
