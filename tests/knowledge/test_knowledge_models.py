from uuid import uuid4
import pytest
from app.domain.knowledge import KnowledgeDocumentStatus, SourceType, ChunkType
from app.persistence.models.knowledge import KnowledgeDocumentModel, KnowledgeChunkModel, RetrievalTraceModel, RetrievalHitModel


def test_knowledge_domain_enums():
    assert KnowledgeDocumentStatus.PENDING == "pending"
    assert KnowledgeDocumentStatus.AWAITING_CONFIRMATION == "awaiting_confirmation"
    assert KnowledgeDocumentStatus.INDEXING == "indexing"
    assert KnowledgeDocumentStatus.AVAILABLE == "available"
    assert KnowledgeDocumentStatus.FAILED == "failed"
    assert KnowledgeDocumentStatus.DELETED == "deleted"

    assert SourceType.PDF == "pdf"
    assert SourceType.MARKDOWN == "markdown"
    assert SourceType.TEXT == "text"
    assert SourceType.IMAGE == "image"
    assert SourceType.URL == "url"
    assert SourceType.HISTORY == "history"

    assert ChunkType.PARENT == "parent"
    assert ChunkType.CHILD == "child"


def test_knowledge_models_init():
    doc_id = uuid4()
    doc = KnowledgeDocumentModel(
        id=doc_id,
        workspace_id="default",
        owner_id="default",
        source_type=SourceType.PDF.value,
        title="Test PDF",
        source_path="/tmp/test.pdf",
        status=KnowledgeDocumentStatus.AWAITING_CONFIRMATION.value,
    )
    assert doc.id == doc_id
    assert doc.status == "awaiting_confirmation"

    parent_chunk_id = uuid4()
    child_chunk = KnowledgeChunkModel(
        document_id=doc_id,
        parent_chunk_id=parent_chunk_id,
        chunk_type=ChunkType.CHILD.value,
        chunk_index=0,
        content="Child content",
        token_count=10,
    )
    assert child_chunk.parent_chunk_id == parent_chunk_id
