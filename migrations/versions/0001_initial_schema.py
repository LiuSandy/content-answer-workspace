"""初始 Schema：创建所有核心业务表

Revision ID: 0001_initial_schema
Revises: 
Create Date: 2026-07-11

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── chats ──────────────────────────────────────────────────────────────
    op.create_table(
        "chats",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("title", sa.String(500), nullable=False, server_default="新对话"),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_chats_workspace_id", "chats", ["workspace_id"])
    op.create_index("ix_chats_created_at", "chats", ["created_at"])

    # ── messages ───────────────────────────────────────────────────────────
    op.create_table(
        "messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("chat_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("chats.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("message_type", sa.String(50), nullable=False, server_default="text"),
        sa.Column("content", sa.Text, nullable=True),
        sa.Column("payload", postgresql.JSONB, nullable=True),
        sa.Column("run_id", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_messages_chat_id", "messages", ["chat_id"])
    op.create_index("ix_messages_chat_id_created_at", "messages", ["chat_id", "created_at"])

    # ── source_items ───────────────────────────────────────────────────────
    op.create_table(
        "source_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("platform", sa.String(50), nullable=False),
        sa.Column("external_id", sa.String(200), nullable=True),
        sa.Column("url", sa.String(2000), nullable=False),
        sa.Column("title", sa.String(1000), nullable=False),
        sa.Column("content", sa.Text, nullable=True),
        sa.Column("author", sa.String(200), nullable=True),
        sa.Column("summary", sa.Text, nullable=True),
        sa.Column("metrics", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("raw_metadata", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_unique_constraint(
        "uq_source_items_platform_external_id", "source_items", ["platform", "external_id"]
    )
    op.create_index("ix_source_items_platform", "source_items", ["platform"])
    op.create_index("ix_source_items_url", "source_items", ["url"])

    # ── chat_source_items ──────────────────────────────────────────────────
    op.create_table(
        "chat_source_items",
        sa.Column("chat_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("chats.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("source_item_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("source_items.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("display_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_chat_source_items_chat_id", "chat_source_items", ["chat_id"])
    op.create_index("ix_chat_source_items_source_item_id", "chat_source_items", ["source_item_id"])

    # ── collection_runs ────────────────────────────────────────────────────
    op.create_table(
        "collection_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("chat_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("chats.id", ondelete="CASCADE"), nullable=False),
        sa.Column("platform", sa.String(50), nullable=False),
        sa.Column("query", sa.Text, nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("result_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("idempotency_key", sa.String(200), nullable=True, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_collection_runs_chat_id", "collection_runs", ["chat_id"])

    # ── answer_versions（先建，document 会 FK 到它）────────────────────────
    op.create_table(
        "answer_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),  # FK 后加
        sa.Column("version_number", sa.Integer, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column(
            "version_type",
            sa.Enum(
                "initial_generation", "inline_refinement", "full_rewrite",
                "manual_checkpoint", "restored",
                name="version_type_enum",
            ),
            nullable=False,
        ),
        sa.Column("instruction", sa.Text, nullable=True),
        sa.Column("restored_from_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("prompt_id", sa.String(200), nullable=True),
        sa.Column("prompt_version", sa.String(50), nullable=True),
        sa.Column("provider", sa.String(100), nullable=True),
        sa.Column("model", sa.String(200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # ── answer_documents ───────────────────────────────────────────────────
    op.create_table(
        "answer_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "source_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("source_items.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("current_content", sa.Text, nullable=True),
        sa.Column(
            "current_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("answer_versions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("lock_version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_answer_documents_source_item_id", "answer_documents", ["source_item_id"])

    # 补加 answer_versions 的 FK（避免循环依赖建表顺序问题）
    op.create_foreign_key(
        "fk_answer_versions_document_id",
        "answer_versions", "answer_documents",
        ["document_id"], ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_answer_versions_restored_from",
        "answer_versions", "answer_versions",
        ["restored_from_version_id"], ["id"],
        ondelete="SET NULL",
    )
    op.create_unique_constraint(
        "uq_answer_versions_doc_num", "answer_versions", ["document_id", "version_number"]
    )
    op.create_index("ix_answer_versions_document_id", "answer_versions", ["document_id"])

    # ── ai_operations ──────────────────────────────────────────────────────
    op.create_table(
        "ai_operations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("chat_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("answer_documents.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("operation_type", sa.String(50), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("prompt_id", sa.String(200), nullable=True),
        sa.Column("prompt_version", sa.String(50), nullable=True),
        sa.Column("provider", sa.String(100), nullable=True),
        sa.Column("model", sa.String(200), nullable=True),
        sa.Column("model_parameters", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("input_metadata", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column(
            "result_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("answer_versions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("input_tokens", sa.Integer, nullable=True),
        sa.Column("output_tokens", sa.Integer, nullable=True),
        sa.Column("latency_ms", sa.Integer, nullable=True),
        sa.Column("error_code", sa.String(100), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_ai_operations_document_id", "ai_operations", ["document_id"])
    op.create_index("ix_ai_operations_chat_id", "ai_operations", ["chat_id"])
    op.create_index("ix_ai_operations_status", "ai_operations", ["status"])

    # ── app_settings ───────────────────────────────────────────────────────
    op.create_table(
        "app_settings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("key", sa.String(200), nullable=False, unique=True),
        sa.Column("value", sa.Text, nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("app_settings")
    op.drop_table("ai_operations")
    op.drop_index("ix_answer_versions_document_id", "answer_versions")
    op.drop_constraint("uq_answer_versions_doc_num", "answer_versions")
    op.drop_constraint("fk_answer_versions_restored_from", "answer_versions")
    op.drop_constraint("fk_answer_versions_document_id", "answer_versions")
    op.drop_table("answer_documents")
    op.drop_table("answer_versions")
    op.execute("DROP TYPE IF EXISTS version_type_enum")
    op.drop_table("collection_runs")
    op.drop_table("chat_source_items")
    op.drop_table("source_items")
    op.drop_table("messages")
    op.drop_table("chats")
