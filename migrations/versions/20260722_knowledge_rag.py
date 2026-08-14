"""add private knowledge rag tables

Revision ID: 20260722_knowledge_rag
Revises: 3b22ddb2e5e9
Create Date: 2026-07-22 11:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision: str = '20260722_knowledge_rag'
down_revision: Union[str, None] = '3b22ddb2e5e9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 建立扩展
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_search;")

    # 创建 knowledge_documents
    op.create_table(
        'knowledge_documents',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('workspace_id', sa.String(length=128), nullable=False),
        sa.Column('owner_id', sa.String(length=128), nullable=False),
        sa.Column('source_type', sa.String(length=32), nullable=False),
        sa.Column('title', sa.String(length=512), nullable=False),
        sa.Column('source_uri', sa.Text(), nullable=True),
        sa.Column('author', sa.String(length=256), nullable=True),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('source_path', sa.Text(), nullable=True),
        sa.Column('source_url', sa.Text(), nullable=True),
        sa.Column('markdown_path', sa.Text(), nullable=True),
        sa.Column('candidate_markdown_path', sa.Text(), nullable=True),
        sa.Column('source_content_hash', sa.String(length=64), nullable=True),
        sa.Column('markdown_content_hash', sa.String(length=64), nullable=True),
        sa.Column('markdown_revision', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('has_manual_edits', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('conversion_confidence', sa.Float(), nullable=True),
        sa.Column('conversion_error', sa.Text(), nullable=True),
        sa.Column('converter_version', sa.String(length=64), nullable=True),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('active_index_version', sa.String(length=64), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_knowledge_documents_workspace_id', 'knowledge_documents', ['workspace_id'], unique=False)
    op.create_index('ix_knowledge_documents_owner_id', 'knowledge_documents', ['owner_id'], unique=False)
    op.create_index('ix_knowledge_documents_status', 'knowledge_documents', ['status'], unique=False)
    op.create_index('ix_knowledge_documents_deleted_at', 'knowledge_documents', ['deleted_at'], unique=False)

    # 创建 knowledge_chunks
    op.create_table(
        'knowledge_chunks',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('document_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('parent_chunk_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('workspace_id', sa.String(length=128), nullable=False),
        sa.Column('owner_id', sa.String(length=128), nullable=False),
        sa.Column('chunk_type', sa.String(length=16), nullable=False),
        sa.Column('chunk_index', sa.Integer(), nullable=False),
        sa.Column('heading_path', sa.Text(), nullable=True),
        sa.Column('markdown_anchor', sa.String(length=256), nullable=True),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('token_count', sa.Integer(), nullable=False),
        sa.Column('embedding', Vector(1536), nullable=True),
        sa.Column('embedding_model', sa.String(length=128), nullable=True),
        sa.Column('index_version', sa.String(length=64), nullable=False),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['document_id'], ['knowledge_documents.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['parent_chunk_id'], ['knowledge_chunks.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_knowledge_chunks_document_id', 'knowledge_chunks', ['document_id'], unique=False)
    op.create_index('ix_knowledge_chunks_parent_chunk_id', 'knowledge_chunks', ['parent_chunk_id'], unique=False)
    op.create_index('ix_knowledge_chunks_workspace_id', 'knowledge_chunks', ['workspace_id'], unique=False)
    op.create_index('ix_knowledge_chunks_owner_id', 'knowledge_chunks', ['owner_id'], unique=False)
    op.create_index('ix_knowledge_chunks_chunk_type', 'knowledge_chunks', ['chunk_type'], unique=False)
    op.create_index('ix_knowledge_chunks_index_version', 'knowledge_chunks', ['index_version'], unique=False)
    op.create_index('ix_knowledge_chunks_deleted_at', 'knowledge_chunks', ['deleted_at'], unique=False)

    # 创建 HNSW 索引 与 BM25 索引 (由 ParadeDB pg_search 驱动)
    op.execute("""
    CREATE INDEX IF NOT EXISTS knowledge_chunks_vector_hnsw_idx
    ON knowledge_chunks USING hnsw (embedding vector_cosine_ops)
    WHERE chunk_type = 'child' AND deleted_at IS NULL;
    """)

    op.execute("""
    CREATE INDEX IF NOT EXISTS knowledge_chunks_bm25_idx
    ON knowledge_chunks USING bm25
      (id, content, heading_path, workspace_id, document_id, index_version, deleted_at)
    WITH (key_field='id');
    """)

    # 创建 retrieval_traces
    op.create_table(
        'retrieval_traces',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('workspace_id', sa.String(length=128), nullable=False),
        sa.Column('owner_id', sa.String(length=128), nullable=False),
        sa.Column('chat_id', sa.String(length=128), nullable=True),
        sa.Column('ai_operation_id', sa.String(length=128), nullable=True),
        sa.Column('original_query', sa.Text(), nullable=False),
        sa.Column('rewritten_query', sa.Text(), nullable=True),
        sa.Column('rag_decision', sa.Boolean(), nullable=False),
        sa.Column('decision_reason', sa.Text(), nullable=True),
        sa.Column('mode', sa.String(length=16), nullable=False),
        sa.Column('filters', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('index_version', sa.String(length=64), nullable=True),
        sa.Column('embedding_model', sa.String(length=128), nullable=True),
        sa.Column('reranker_model', sa.String(length=128), nullable=True),
        sa.Column('fallback_reason', sa.Text(), nullable=True),
        sa.Column('latency_ms', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_retrieval_traces_workspace_id', 'retrieval_traces', ['workspace_id'], unique=False)
    op.create_index('ix_retrieval_traces_owner_id', 'retrieval_traces', ['owner_id'], unique=False)
    op.create_index('ix_retrieval_traces_ai_operation_id', 'retrieval_traces', ['ai_operation_id'], unique=False)

    # 创建 retrieval_hits
    op.create_table(
        'retrieval_hits',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('trace_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('chunk_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('retrieval_source', sa.String(length=32), nullable=False),
        sa.Column('rank', sa.Integer(), nullable=False),
        sa.Column('bm25_score', sa.Float(), nullable=True),
        sa.Column('vector_score', sa.Float(), nullable=True),
        sa.Column('rrf_score', sa.Float(), nullable=True),
        sa.Column('rerank_score', sa.Float(), nullable=True),
        sa.Column('included_in_context', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('citation_label', sa.String(length=16), nullable=True),
        sa.Column('context_snapshot', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.ForeignKeyConstraint(['trace_id'], ['retrieval_traces.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_retrieval_hits_trace_id', 'retrieval_hits', ['trace_id'], unique=False)
    op.create_index('ix_retrieval_hits_chunk_id', 'retrieval_hits', ['chunk_id'], unique=False)


def downgrade() -> None:
    op.drop_table('retrieval_hits')
    op.drop_table('retrieval_traces')
    op.execute("DROP INDEX IF EXISTS knowledge_chunks_bm25_idx;")
    op.execute("DROP INDEX IF EXISTS knowledge_chunks_vector_hnsw_idx;")
    op.drop_table('knowledge_chunks')
    op.drop_table('knowledge_documents')
