"""AnswerDocument、AnswerVersion 和 AIOperation 领域模型；对应回答创作的核心表。"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .. import Base

# VersionType 枚举值，与 AnswerVersion.version_type 一一对应
VERSION_TYPE_INITIAL_GENERATION = "initial_generation"
VERSION_TYPE_INLINE_REFINEMENT = "inline_refinement"
VERSION_TYPE_FULL_REWRITE = "full_rewrite"
VERSION_TYPE_MANUAL_CHECKPOINT = "manual_checkpoint"
VERSION_TYPE_RESTORED = "restored"


class AnswerDocument(Base):
    """一篇帖子对应的回答工作区；保存编辑器当前最新内容和乐观锁版本号。

    乐观锁规则：
    - 自动保存和 AI 操作都必须携带 expected_lock_version
    - 数据库 lock_version 与 expected_lock_version 不一致时返回 409 Conflict
    - 每次成功写入后 lock_version 自增
    """

    __tablename__ = "answer_documents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # 每篇帖子最多一个 Document
    source_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("source_items.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    # 编辑器当前显示的最新内容（包含未形成正式版本的人工修改）
    current_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 指向最后一个正式版本（可为 NULL，表示尚无正式版本）
    current_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("answer_versions.id", ondelete="SET NULL"), nullable=True
    )
    # 当前选中的大纲快照。恢复文章历史版本时同步切换到该版本所用大纲。
    current_outline_operation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "ai_operations.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_answer_documents_current_outline_operation",
        ),
        nullable=True,
    )
    # 乐观锁版本号，从 1 开始
    lock_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # R10 发布状态：draft → ready → published
    publish_status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    publish_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # 预留多用户扩展
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    # 关系
    source_item: Mapped[SourceItem] = relationship("SourceItem", back_populates="answer_document")
    versions: Mapped[list[AnswerVersion]] = relationship(
        "AnswerVersion",
        back_populates="document",
        foreign_keys="AnswerVersion.document_id",
        order_by="AnswerVersion.version_number",
        cascade="all, delete-orphan",
    )
    current_version: Mapped[AnswerVersion | None] = relationship(
        "AnswerVersion",
        foreign_keys=[current_version_id],
        primaryjoin="AnswerDocument.current_version_id == AnswerVersion.id",
        uselist=False,
    )
    ai_operations: Mapped[list[AIOperation]] = relationship(
        "AIOperation",
        back_populates="document",
        foreign_keys="AIOperation.document_id",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_answer_documents_source_item_id", "source_item_id"),
        Index(
            "ix_answer_documents_current_outline_operation_id",
            "current_outline_operation_id",
        ),
    )


class AnswerVersion(Base):
    """回答的完整历史快照；每个重要创作节点保存一份完整内容，不存 Diff。"""

    __tablename__ = "answer_versions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("answer_documents.id", ondelete="CASCADE"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    # 完整回答内容（不是 Diff）
    content: Mapped[str] = mapped_column(Text, nullable=False)
    version_type: Mapped[str] = mapped_column(
        Enum(
            VERSION_TYPE_INITIAL_GENERATION,
            VERSION_TYPE_INLINE_REFINEMENT,
            VERSION_TYPE_FULL_REWRITE,
            VERSION_TYPE_MANUAL_CHECKPOINT,
            VERSION_TYPE_RESTORED,
            name="version_type_enum",
        ),
        nullable=False,
    )
    # 用户给该版本的指令（润色/重写指令）
    instruction: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 恢复版本时指向被恢复的源版本
    restored_from_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("answer_versions.id", ondelete="SET NULL"), nullable=True
    )
    # 生成该文章版本时采用的大纲快照。
    outline_operation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ai_operations.id", ondelete="SET NULL"), nullable=True
    )
    # Prompt 溯源信息
    prompt_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # 模型溯源信息
    provider: Mapped[str | None] = mapped_column(String(100), nullable=True)
    model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # 关系
    document: Mapped[AnswerDocument] = relationship(
        "AnswerDocument",
        back_populates="versions",
        foreign_keys=[document_id],
    )

    __table_args__ = (
        # 同一文档内版本号唯一
        UniqueConstraint("document_id", "version_number", name="uq_answer_versions_doc_num"),
        Index("ix_answer_versions_document_id", "document_id"),
        Index("ix_answer_versions_outline_operation_id", "outline_operation_id"),
    )


class AIOperation(Base):
    """一次 AI 生成、润色或重写任务的完整执行记录；记录状态、用量和 Prompt 溯源。"""

    __tablename__ = "ai_operations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    chat_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("answer_documents.id", ondelete="CASCADE"), nullable=True
    )
    # generate / inline_refine / full_rewrite / chat
    operation_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # pending / running / completed / failed / cancelled
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    prompt_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    provider: Mapped[str | None] = mapped_column(String(100), nullable=True)
    model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    model_parameters: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    input_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # 结构化报告（质检、选题评估等）写输出字段，不占用输入字段
    output_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # 成功后关联生成的版本
    result_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("answer_versions.id", ondelete="SET NULL"), nullable=True
    )
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # 关系
    document: Mapped[AnswerDocument | None] = relationship(
        "AnswerDocument", back_populates="ai_operations", foreign_keys=[document_id]
    )

    __table_args__ = (
        Index("ix_ai_operations_document_id", "document_id"),
        Index("ix_ai_operations_chat_id", "chat_id"),
        Index("ix_ai_operations_status", "status"),
    )


# 延迟导入避免循环引用
from typing import TYPE_CHECKING  # noqa: E402

if TYPE_CHECKING:
    from .content import SourceItem
