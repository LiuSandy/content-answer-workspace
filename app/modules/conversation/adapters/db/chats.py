"""Chat 和 Message 领域模型；对应 chats 和 messages 表。"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.platform.database import Base


class Chat(Base):
    """一次完整的聊天上下文，包含多轮消息和多篇帖子。"""

    __tablename__ = "chats"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False, default="新对话")
    # 预留多用户扩展，第一版为 NULL
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    # 关系
    messages: Mapped[list[Message]] = relationship(
        "Message", back_populates="chat", order_by="Message.created_at", cascade="all, delete-orphan"
    )
    chat_source_items: Mapped[list[ChatSourceItem]] = relationship(
        "ChatSourceItem",
        back_populates="chat",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_chats_workspace_id", "workspace_id"),
        Index("ix_chats_created_at", "created_at"),
    )


class Message(Base):
    """Chat 内的单条消息；涵盖用户输入、AI 回复、工具结果和结构化帖子卡片。"""

    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    chat_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chats.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # user / assistant / tool
    # 消息类型：text / source_card / source_list / tool_status / error
    message_type: Mapped[str] = mapped_column(String(50), nullable=False, default="text")
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 结构化数据（source_list 内容、tool 参数等）
    payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # Agent 执行 run_id，用于 SSE 关联和前端去重
    run_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    parent_message_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("messages.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # 关系
    chat: Mapped[Chat] = relationship("Chat", back_populates="messages")

    __table_args__ = (
        Index("ix_messages_chat_id", "chat_id"),
        Index("ix_messages_chat_id_created_at", "chat_id", "created_at"),
    )


# 注册跨模块 ORM 关系；导入发生在本模块所有 class 声明完成之后。
from app.modules.conversation.adapters.db.sources import ChatSourceItem  # noqa: E402,F401
