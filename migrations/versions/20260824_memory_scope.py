"""add intent-aware scope to user memories

Revision ID: 20260824_memory_scope
Revises: 20260815_large_pdf_pages
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260824_memory_scope"
down_revision: Union[str, None] = "20260815_large_pdf_pages"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "user_memories",
        sa.Column(
            "memory_scope",
            sa.String(length=32),
            nullable=False,
            server_default="general",
        ),
    )
    op.execute(
        "UPDATE user_memories SET memory_scope = CASE "
        "WHEN memory_type = 'implicit' THEN 'writing_style' "
        "WHEN memory_type = 'work_pattern' THEN 'workflow' "
        "ELSE 'general' END"
    )
    op.create_index(
        "ix_user_memories_workspace_status_scope",
        "user_memories",
        ["workspace_id", "status", "memory_scope"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_user_memories_workspace_status_scope",
        table_name="user_memories",
    )
    op.drop_column("user_memories", "memory_scope")
