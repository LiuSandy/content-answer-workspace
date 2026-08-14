"""add user_memories table for long-term memory

Revision ID: 20260804_mem
Revises: 20260804_plan
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


revision: str = '20260804_mem'
down_revision: Union[str, None] = '20260804_plan'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 尝试创建 pgvector extension（若不存在则跳过，向量字段用 JSONB 兜底）
    use_vector = False
    try:
        with op.get_context().autocommit_block():
            op.execute("CREATE EXTENSION IF NOT EXISTS vector")
        use_vector = True
    except Exception:
        use_vector = False

    if use_vector:
        op.create_table(
            'user_memories',
            sa.Column('id', UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column('workspace_id', sa.String(length=100), nullable=False),
            sa.Column('memory_type', sa.String(length=20), nullable=False),
            sa.Column('content', sa.Text(), nullable=False),
            sa.Column('embedding', sa.dialects.postgresql.ARRAY(sa.Float()), nullable=True),
            sa.Column('confidence', sa.Float(), nullable=False, server_default='0.8'),
            sa.Column('source', sa.String(length=200), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column('last_activated_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('activation_count', sa.Integer(), nullable=False, server_default='0'),
        )
    else:
        op.create_table(
            'user_memories',
            sa.Column('id', UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column('workspace_id', sa.String(length=100), nullable=False),
            sa.Column('memory_type', sa.String(length=20), nullable=False),
            sa.Column('content', sa.Text(), nullable=False),
            sa.Column('embedding', JSONB(), nullable=True),
            sa.Column('confidence', sa.Float(), nullable=False, server_default='0.8'),
            sa.Column('source', sa.String(length=200), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column('last_activated_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('activation_count', sa.Integer(), nullable=False, server_default='0'),
        )

    op.create_index('ix_user_memories_workspace_type', 'user_memories', ['workspace_id', 'memory_type'])


def downgrade() -> None:
    op.drop_index('ix_user_memories_workspace_type', table_name='user_memories')
    try:
        op.execute("DROP INDEX IF EXISTS ix_user_memories_embedding_hnsw")
    except Exception:
        pass
    op.drop_table('user_memories')