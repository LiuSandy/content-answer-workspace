"""add branch_summaries + memory status/vector evolution

R4：分支级滚动摘要表；R5 记忆完善所需的状态/证据列、embedding 向量化与 HNSW 索引。
升级时先校验既有 ARRAY embedding 维度，再转换为 vector(1536)，最后创建 cosine HNSW 索引。

Revision ID: 20260805_context_memory_evolve
Revises: 20260805_foundation
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision: str = '20260805_context_memory_evolve'
down_revision: Union[str, None] = '20260805_foundation'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EXPECTED_EMBEDDING_DIM = 1536


def validate_embedding_dimension(value: list | None) -> bool:
    """迁移可测试的维度校验：非空且长度必须为 1536。"""
    if value is None:
        return False
    if not isinstance(value, (list, tuple)):
        return False
    return len(value) == EXPECTED_EMBEDDING_DIM


def upgrade() -> None:
    # ── 分支滚动摘要表（R4） ────────────────────────────────────────────────
    op.create_table(
        'branch_summaries',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('chat_id', UUID(as_uuid=True), sa.ForeignKey('chats.id', ondelete='CASCADE'), nullable=False),
        sa.Column('branch_root_message_id', UUID(as_uuid=True), nullable=True),
        sa.Column('summary', sa.Text(), nullable=False, server_default=''),
        sa.Column('covered_message_ids', JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column('last_covered_message_id', UUID(as_uuid=True), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_unique_constraint(
        'uq_branch_summaries_chat_root', 'branch_summaries', ['chat_id', 'branch_root_message_id']
    )
    op.create_index('ix_branch_summaries_chat_root', 'branch_summaries', ['chat_id', 'branch_root_message_id'])

    # ── 记忆演化（R5）：status / evidence ──────────────────────────────────
    op.add_column('user_memories', sa.Column('status', sa.String(length=20), nullable=False, server_default='active'))
    op.add_column('user_memories', sa.Column('evidence', sa.Text(), nullable=True))
    # 旧显式记忆回填 active（server_default 已生效，这里显式更新保证语义一致）
    op.execute("UPDATE user_memories SET status = 'active' WHERE status IS NULL OR status = ''")

    # ── embedding 向量化：ARRAY(Float) → vector(1536) + HNSW ──
    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        # 确保 pgvector 扩展已启用（paradedb 镜像已预装）
        # autocommit_block 同时支持在线迁移与 `alembic --sql` 离线渲染；
        # 不能在迁移中另开 bind.engine 连接，否则离线模式会在这里提前终止。
        with op.get_context().autocommit_block():
            op.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))
        # 转换：array → json → text → vector
        op.execute(sa.text("ALTER TABLE user_memories ADD COLUMN embedding_v vector(1536)"))
        op.execute(sa.text(
            "UPDATE user_memories SET embedding_v = (array_to_json(embedding)::text)::vector "
            "WHERE embedding IS NOT NULL AND array_length(embedding, 1) = 1536"
        ))
        op.execute(sa.text("ALTER TABLE user_memories DROP COLUMN embedding"))
        op.execute(sa.text("ALTER TABLE user_memories RENAME COLUMN embedding_v TO embedding"))
        # 创建 HNSW 余弦索引
        op.execute(sa.text(
            "CREATE INDEX IF NOT EXISTS ix_user_memories_embedding_hnsw ON user_memories "
            "USING hnsw (embedding vector_cosine_ops)"
        ))


def downgrade() -> None:
    try:
        op.execute("DROP INDEX IF EXISTS ix_user_memories_embedding_hnsw")
    except Exception:
        pass
    try:
        with op.get_context().autocommit_block():
            op.execute(
                "ALTER TABLE user_memories ADD COLUMN embedding_backup ARRAY(FLOAT)"
            )
            op.execute(
                "UPDATE user_memories SET embedding_backup = embedding::float[] "
                "WHERE embedding IS NOT NULL"
            )
    except Exception:
        pass

    op.drop_index('ix_branch_summaries_chat_root', table_name='branch_summaries')
    op.drop_constraint('uq_branch_summaries_chat_root', 'branch_summaries')
    op.drop_table('branch_summaries')
