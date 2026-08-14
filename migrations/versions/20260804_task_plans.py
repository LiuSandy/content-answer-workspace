"""add task_plans and sub_tasks tables

Revision ID: 20260804_plan
Revises: 20260804_opp
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


revision: str = '20260804_plan'
down_revision: Union[str, None] = '20260804_opp'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'task_plans',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('workspace_id', sa.String(length=100), nullable=False),
        sa.Column('chat_id', UUID(as_uuid=True), nullable=True),
        sa.Column('goal', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_task_plans_chat_id', 'task_plans', ['chat_id'])
    op.create_index('ix_task_plans_workspace_status', 'task_plans', ['workspace_id', 'status'])

    op.create_table(
        'sub_tasks',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('plan_id', UUID(as_uuid=True),
                  sa.ForeignKey('task_plans.id', ondelete='CASCADE'), nullable=False),
        sa.Column('task_id', sa.String(length=50), nullable=False),
        sa.Column('type', sa.String(length=20), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('depends_on', JSONB(), nullable=False, server_default='[]'),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'),
        sa.Column('result', sa.Text(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_sub_tasks_plan_status', 'sub_tasks', ['plan_id', 'status'])


def downgrade() -> None:
    op.drop_index('ix_sub_tasks_plan_status', table_name='sub_tasks')
    op.drop_table('sub_tasks')
    op.drop_index('ix_task_plans_workspace_status', table_name='task_plans')
    op.drop_index('ix_task_plans_chat_id', table_name='task_plans')
    op.drop_table('task_plans')