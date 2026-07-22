import uuid
import pytest
from app.persistence.models.knowledge import (
    KnowledgeDocumentModel,
    KnowledgeChunkModel,
    RetrievalTraceModel,
    RetrievalHitModel,
)

def test_knowledge_models_instantiation():
    doc = KnowledgeDocumentModel(
        workspace_id="default",
        owner_id="default",
        source_type="pdf",
        title="Test PDF",
        status="awaiting_confirmation",
    )
    assert doc.title == "Test PDF"
    assert doc.status == "awaiting_confirmation"

    chunk = KnowledgeChunkModel(
        document_id=uuid.uuid4(),
        workspace_id="default",
        owner_id="default",
        chunk_type="child",
        chunk_index=0,
        content="Test chunk",
        token_count=10,
        index_version="v1",
    )
    assert chunk.content == "Test chunk"
