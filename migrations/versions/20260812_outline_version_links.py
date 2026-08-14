"""link answer versions to versioned outline operations

Revision ID: 20260812_outline_versions
Revises: 53965b1ce218
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260812_outline_versions"
down_revision: Union[str, None] = "53965b1ce218"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "answer_documents",
        sa.Column("current_outline_operation_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        "fk_answer_documents_current_outline_operation",
        "answer_documents",
        "ai_operations",
        ["current_outline_operation_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_answer_documents_current_outline_operation_id",
        "answer_documents",
        ["current_outline_operation_id"],
    )
    op.add_column(
        "answer_versions",
        sa.Column("outline_operation_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        "fk_answer_versions_outline_operation",
        "answer_versions",
        "ai_operations",
        ["outline_operation_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_answer_versions_outline_operation_id",
        "answer_versions",
        ["outline_operation_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_answer_versions_outline_operation_id", table_name="answer_versions")
    op.drop_constraint(
        "fk_answer_versions_outline_operation", "answer_versions", type_="foreignkey"
    )
    op.drop_column("answer_versions", "outline_operation_id")
    op.drop_index(
        "ix_answer_documents_current_outline_operation_id",
        table_name="answer_documents",
    )
    op.drop_constraint(
        "fk_answer_documents_current_outline_operation",
        "answer_documents",
        type_="foreignkey",
    )
    op.drop_column("answer_documents", "current_outline_operation_id")
