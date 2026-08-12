"""verify memory vectors and add retrieval filter index

Revision ID: 20260813_memory_vectors
Revises: 20260812_outline_versions
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260813_memory_vectors"
down_revision: Union[str, None] = "20260812_outline_versions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    with op.get_context().autocommit_block():
        op.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))

    # vector(1536) 本身会约束新写入；这里审计升级前的已有非空数据，
    # 避免在异常维度存在时继续创建一个表面可用、实际不可检索的索引。
    op.execute(
        sa.text(
            """
            DO $$
            DECLARE invalid_count bigint;
            BEGIN
              SELECT count(*) INTO invalid_count
              FROM user_memories
              WHERE embedding IS NOT NULL AND vector_dims(embedding) <> 1536;
              IF invalid_count > 0 THEN
                RAISE EXCEPTION 'user_memories contains % invalid embedding dimensions', invalid_count;
              END IF;
            END $$
            """
        )
    )
    op.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_user_memories_embedding_hnsw "
            "ON user_memories USING hnsw (embedding vector_cosine_ops)"
        )
    )
    op.create_index(
        "ix_user_memories_workspace_status",
        "user_memories",
        ["workspace_id", "status"],
        unique=False,
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_user_memories_workspace_status",
        table_name="user_memories",
        if_exists=True,
    )
