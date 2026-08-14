"""add persistent knowledge source ingestion jobs

Revision ID: 20260814_knowledge_ingestion
Revises: 20260813_memory_vectors
Create Date: 2026-08-12
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260814_knowledge_ingestion"
down_revision: Union[str, None] = "20260813_memory_vectors"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "knowledge_source_files",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", sa.String(128), nullable=False),
        sa.Column("owner_id", sa.String(128), nullable=False),
        sa.Column("ingest_source", sa.String(32), nullable=False),
        sa.Column("original_filename", sa.String(512), nullable=False),
        sa.Column("original_relative_path", sa.Text(), nullable=False),
        sa.Column("current_relative_path", sa.Text(), nullable=False),
        sa.Column("extension", sa.String(32), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("knowledge_document_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("failure_code", sa.String(64), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["knowledge_document_id"], ["knowledge_documents.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("workspace_id", "owner_id", "content_hash", "status", "knowledge_document_id"):
        op.create_index(f"ix_knowledge_source_files_{column}", "knowledge_source_files", [column])

    op.create_table(
        "knowledge_ingestion_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_file_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("stage", sa.String(64), nullable=False),
        sa.Column("progress_current", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("progress_total", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("progress_percent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("checkpoint", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("lease_owner", sa.String(128), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["source_file_id"], ["knowledge_source_files.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_knowledge_ingestion_jobs_source_file_id", "knowledge_ingestion_jobs", ["source_file_id"])
    op.create_index("ix_knowledge_ingestion_jobs_status", "knowledge_ingestion_jobs", ["status"])
    op.create_index("ix_knowledge_ingestion_jobs_lease_expires_at", "knowledge_ingestion_jobs", ["lease_expires_at"])
    op.execute(
        "CREATE UNIQUE INDEX uq_knowledge_ingestion_active_source "
        "ON knowledge_ingestion_jobs (source_file_id) WHERE status IN ('queued', 'running')"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_knowledge_ingestion_active_source")
    op.drop_table("knowledge_ingestion_jobs")
    op.drop_table("knowledge_source_files")
