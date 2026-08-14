"""add page-level large PDF ingestion state

Revision ID: 20260815_large_pdf_pages
Revises: 20260814_knowledge_ingestion
Create Date: 2026-08-13
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260815_large_pdf_pages"
down_revision: Union[str, None] = "20260814_knowledge_ingestion"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("knowledge_ingestion_jobs", sa.Column("total_pages", sa.Integer(), server_default="0", nullable=False))
    op.add_column("knowledge_ingestion_jobs", sa.Column("completed_pages", sa.Integer(), server_default="0", nullable=False))
    op.add_column("knowledge_ingestion_jobs", sa.Column("succeeded_pages", sa.Integer(), server_default="0", nullable=False))
    op.add_column("knowledge_ingestion_jobs", sa.Column("failed_pages", sa.Integer(), server_default="0", nullable=False))
    op.add_column("knowledge_ingestion_jobs", sa.Column("current_page", sa.Integer(), nullable=True))

    op.create_table(
        "knowledge_ingestion_pages",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("markdown_path", sa.Text(), nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("lease_owner", sa.String(128), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["knowledge_ingestion_jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_knowledge_ingestion_pages_job_id", "knowledge_ingestion_pages", ["job_id"])
    op.create_index("ix_knowledge_ingestion_pages_status", "knowledge_ingestion_pages", ["status"])
    op.create_index("ix_knowledge_ingestion_pages_lease_expires_at", "knowledge_ingestion_pages", ["lease_expires_at"])
    op.create_index(
        "uq_knowledge_ingestion_page_number",
        "knowledge_ingestion_pages",
        ["job_id", "page_number"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_table("knowledge_ingestion_pages")
    op.drop_column("knowledge_ingestion_jobs", "current_page")
    op.drop_column("knowledge_ingestion_jobs", "failed_pages")
    op.drop_column("knowledge_ingestion_jobs", "succeeded_pages")
    op.drop_column("knowledge_ingestion_jobs", "completed_pages")
    op.drop_column("knowledge_ingestion_jobs", "total_pages")
