"""SourceItem、ChatSourceItem 和 CollectionRun 领域模型；对应平台内容采集的核心表。"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.platform.database import Base


class SourceItem(Base):
    """从平台采集或 URL 解析得到的标准化帖子；跨 Chat 共享，同一帖子只存一份。"""

    __tablename__ = "source_items"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    platform: Mapped[str] = mapped_column(String(50), nullable=False)  # zhihu / xiaohongshu / ...
    # 平台原生 ID（如知乎问题 ID）；无稳定 ID 时为 NULL，用规范化 URL 去重
    external_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    url: Mapped[str] = mapped_column(String(2000), nullable=False)
    title: Mapped[str] = mapped_column(String(1000), nullable=False)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    author: Mapped[str | None] = mapped_column(String(200), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 平台指标（点赞数、收藏数等）
    metrics: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # 平台原始元数据（不做结构约束）
    raw_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # 关系
    chat_source_items: Mapped[list[ChatSourceItem]] = relationship(
        "ChatSourceItem", back_populates="source_item", cascade="all, delete-orphan"
    )
    answer_document: Mapped[AnswerDocument | None] = relationship(
        "AnswerDocument",
        back_populates="source_item",
        uselist=False,
    )

    __table_args__ = (
        # 首选去重键：(platform, external_id)
        UniqueConstraint("platform", "external_id", name="uq_source_items_platform_external_id"),
        Index("ix_source_items_platform", "platform"),
        Index("ix_source_items_url", "url"),
    )


class ChatSourceItem(Base):
    """Chat 与 SourceItem 的多对多关联表；记录展示顺序，同一帖子可出现在多个 Chat 中。"""

    __tablename__ = "chat_source_items"

    chat_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chats.id", ondelete="CASCADE"), primary_key=True
    )
    source_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("source_items.id", ondelete="CASCADE"), primary_key=True
    )
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # 关系
    chat: Mapped[Chat] = relationship(
        "Chat",
        back_populates="chat_source_items",
    )
    source_item: Mapped[SourceItem] = relationship("SourceItem", back_populates="chat_source_items")

    __table_args__ = (
        Index("ix_chat_source_items_chat_id", "chat_id"),
        Index("ix_chat_source_items_source_item_id", "source_item_id"),
    )


class CollectionRun(Base):
    """一次主题采集请求的执行记录；记录状态、平台和参数，供前端显示进度和历史。"""

    __tablename__ = "collection_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    chat_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chats.id", ondelete="CASCADE"), nullable=False
    )
    platform: Mapped[str] = mapped_column(String(50), nullable=False)
    query: Mapped[str | None] = mapped_column(Text, nullable=True)
    # pending / running / completed / failed
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    result_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 幂等键，防止重试产生重复采集记录
    idempotency_key: Mapped[str | None] = mapped_column(String(200), nullable=True, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("ix_collection_runs_chat_id", "chat_id"),)


# 注册跨模块 ORM 关系；导入发生在本模块所有 class 声明完成之后。
from app.modules.conversation.adapters.db.chats import Chat  # noqa: E402,F401
from app.modules.documents.adapters.db.models import AnswerDocument  # noqa: E402,F401
