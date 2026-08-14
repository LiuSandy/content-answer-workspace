"""重建 BM25 索引：为 content/heading_path 配置中文兼容 tokenizer

原索引使用 pg_search 默认 tokenizer（按空白/标点切词），中文整句无空格
导致 BM25 召回对中文知识库基本失效。chinese_compatible tokenizer 将
CJK 字符逐字切分，配合 BM25 评分可正确支持中文检索。

Revision ID: 20260726_bm25_zh
Revises: 20260722_knowledge_rag
Create Date: 2026-07-26
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '20260726_bm25_zh'
down_revision: Union[str, None] = '20260722_knowledge_rag'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_CREATE_ZH_INDEX = """
CREATE INDEX IF NOT EXISTS knowledge_chunks_bm25_idx
ON knowledge_chunks USING bm25
  (id, content, heading_path, workspace_id, owner_id, document_id, index_version, chunk_type)
WITH (
  key_field='id',
  text_fields='{
    "content": {"tokenizer": {"type": "chinese_compatible"}},
    "heading_path": {"tokenizer": {"type": "chinese_compatible"}}
  }'
);
"""

_CREATE_DEFAULT_INDEX = """
CREATE INDEX IF NOT EXISTS knowledge_chunks_bm25_idx
ON knowledge_chunks USING bm25
  (id, content, heading_path, workspace_id, document_id, index_version, deleted_at)
WITH (key_field='id');
"""


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS knowledge_chunks_bm25_idx;")
    op.execute(_CREATE_ZH_INDEX)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS knowledge_chunks_bm25_idx;")
    op.execute(_CREATE_DEFAULT_INDEX)
