import uuid
import pytest
from app.persistence.models.knowledge import (
    KnowledgeDocumentModel,
    KnowledgeChunkModel,
    RetrievalTraceModel,
    RetrievalHitModel,
    KnowledgeSourceFileModel,
    KnowledgeIngestionJobModel,
    KnowledgeIngestionPageModel,
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

    source = KnowledgeSourceFileModel(
        workspace_id="default",
        owner_id="default",
        ingest_source="directory_scan",
        original_filename="example.pdf",
        original_relative_path="技术/example.pdf",
        current_relative_path="processing/技术/example.pdf",
        extension="pdf",
        size_bytes=42,
        status="processing",
    )
    job = KnowledgeIngestionJobModel(
        source_file_id=uuid.uuid4(),
        status="queued",
        stage="discovered",
    )
    assert source.status == "processing"
    assert job.stage == "discovered"

    page = KnowledgeIngestionPageModel(
        job_id=uuid.uuid4(), page_number=1, status="pending"
    )
    assert page.page_number == 1
