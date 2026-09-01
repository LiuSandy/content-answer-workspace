"""add indexes for ingestion retention cleanup

Revision ID: 20260901_ingestion_cleanup_indexes
Revises: 20260824_memory_scope
"""
from typing import Sequence, Union

from alembic import op


revision: str = "20260901_ingestion_cleanup_indexes"
down_revision: Union[str, None] = "20260824_memory_scope"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_knowledge_ingestion_jobs_status_completed_at",
        "knowledge_ingestion_jobs",
        ["status", "completed_at"],
    )
    op.create_index(
        "ix_knowledge_ingestion_pages_status_completed_at",
        "knowledge_ingestion_pages",
        ["status", "completed_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_knowledge_ingestion_pages_status_completed_at",
        table_name="knowledge_ingestion_pages",
    )
    op.drop_index(
        "ix_knowledge_ingestion_jobs_status_completed_at",
        table_name="knowledge_ingestion_jobs",
    )
