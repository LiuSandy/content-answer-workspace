"""add publish_metrics table + answer_documents publish fields + opportunity_feeds LLM eval fields

Revision ID: 53965b1ce218
Revises: 20260805_context_memory_evolve
Create Date: 2026-08-07 03:53:23.354071+00:00

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '53965b1ce218'
down_revision: Union[str, None] = '20260805_context_memory_evolve'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('publish_metrics',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('document_id', sa.UUID(), nullable=False),
        sa.Column('views', sa.Integer(), nullable=True),
        sa.Column('likes', sa.Integer(), nullable=True),
        sa.Column('comments', sa.Integer(), nullable=True),
        sa.Column('collects', sa.Integer(), nullable=True),
        sa.Column('recorded_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('label', sa.String(length=100), nullable=True),
        sa.ForeignKeyConstraint(['document_id'], ['answer_documents.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.add_column('answer_documents', sa.Column('publish_status', sa.String(length=20), nullable=False, server_default='draft'))
    op.add_column('answer_documents', sa.Column('publish_url', sa.Text(), nullable=True))
    op.add_column('answer_documents', sa.Column('published_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('opportunity_feeds', sa.Column('llm_evaluated', sa.String(length=5), nullable=True))
    op.add_column('opportunity_feeds', sa.Column('llm_score', sa.Float(), nullable=True))
    op.add_column('opportunity_feeds', sa.Column('llm_reason', sa.Text(), nullable=True))
    op.add_column('opportunity_feeds', sa.Column('user_match_reason', sa.Text(), nullable=True))
    op.add_column('opportunity_feeds', sa.Column('llm_evaluated_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('opportunity_feeds', 'llm_evaluated_at')
    op.drop_column('opportunity_feeds', 'user_match_reason')
    op.drop_column('opportunity_feeds', 'llm_reason')
    op.drop_column('opportunity_feeds', 'llm_score')
    op.drop_column('opportunity_feeds', 'llm_evaluated')
    op.drop_column('answer_documents', 'published_at')
    op.drop_column('answer_documents', 'publish_url')
    op.drop_column('answer_documents', 'publish_status')
    op.drop_table('publish_metrics')
