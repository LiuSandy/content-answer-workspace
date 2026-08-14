"""add quality_scores table for reflection self-evaluation

Revision ID: 20260804_quality
Revises: 20260726_bm25_zh
Create Date: 2026-08-04

新增 quality_scores 表，持久化反思循环每次自评的 5 维分数、弱点总结
与定向修正指令。一次 AI 生成操作因反思循环最多产生 3 条记录（iteration=1..3）。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


revision: str = '20260804_quality'
down_revision: Union[str, None] = '20260726_bm25_zh'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'quality_scores',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('ai_operation_id', UUID(as_uuid=True),
                  sa.ForeignKey('ai_operations.id', ondelete='SET NULL'), nullable=True),
        sa.Column('document_id', UUID(as_uuid=True),
                  sa.ForeignKey('answer_documents.id', ondelete='CASCADE'), nullable=False),
        sa.Column('version_id', UUID(as_uuid=True),
                  sa.ForeignKey('answer_versions.id', ondelete='SET NULL'), nullable=True),
        sa.Column('iteration', sa.Integer(), nullable=False),
        sa.Column('overall_score', sa.Float(), nullable=False),
        sa.Column('dimensions', JSONB(), nullable=False, server_default='{}'),
        sa.Column('weakness_summary', sa.Text(), nullable=True),
        sa.Column('refinement_instruction', sa.Text(), nullable=True),
        sa.Column('converged', sa.String(length=20), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        'ix_quality_scores_document_iteration',
        'quality_scores',
        ['document_id', 'iteration'],
    )
    op.create_index(
        'ix_quality_scores_ai_operation_id',
        'quality_scores',
        ['ai_operation_id'],
    )


def downgrade() -> None:
    op.drop_index('ix_quality_scores_ai_operation_id', table_name='quality_scores')
    op.drop_index('ix_quality_scores_document_iteration', table_name='quality_scores')
    op.drop_table('quality_scores')