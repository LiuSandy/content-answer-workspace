"""add opportunity_feeds and agent_settings tables

Revision ID: 20260804_opp
Revises: 20260804_quality
Create Date: 2026-08-04
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


revision: str = '20260804_opp'
down_revision: Union[str, None] = '20260804_quality'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'opportunity_feeds',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('workspace_id', sa.String(length=100), nullable=False),
        sa.Column('platform', sa.String(length=50), nullable=False),
        sa.Column('question_title', sa.Text(), nullable=False),
        sa.Column('question_url', sa.Text(), nullable=False),
        sa.Column('hot_score', sa.Float(), nullable=False, server_default='0'),
        sa.Column('match_score', sa.Float(), nullable=False, server_default='0'),
        sa.Column('competition_score', sa.Float(), nullable=False, server_default='0'),
        sa.Column('recency_score', sa.Float(), nullable=False, server_default='0'),
        sa.Column('opportunity_score', sa.Float(), nullable=False, server_default='0'),
        sa.Column('existing_answer_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('pushed', sa.String(length=20), nullable=False, server_default='false'),
        sa.Column('scanned_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('raw_metadata', JSONB(), nullable=False, server_default='{}'),
    )
    op.create_index('ix_opportunity_feeds_workspace_score', 'opportunity_feeds',
                    ['workspace_id', 'opportunity_score'])
    op.create_index('ix_opportunity_feeds_pushed', 'opportunity_feeds', ['pushed'])

    op.create_table(
        'agent_settings',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('workspace_id', sa.String(length=100), nullable=False, unique=True),
        sa.Column('proactive_sensing_enabled', sa.String(length=20), nullable=False, server_default='true'),
        sa.Column('interest_tags', JSONB(), nullable=False, server_default='[]'),
        sa.Column('push_time_window', JSONB(), nullable=False, server_default='{}'),
        sa.Column('scan_interval_hours', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table('agent_settings')
    op.drop_index('ix_opportunity_feeds_pushed', table_name='opportunity_feeds')
    op.drop_index('ix_opportunity_feeds_workspace_score', table_name='opportunity_feeds')
    op.drop_table('opportunity_feeds')