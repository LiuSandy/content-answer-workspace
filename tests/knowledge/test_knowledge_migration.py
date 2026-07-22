import pytest
from app.persistence.models.knowledge import KnowledgeDocumentModel, KnowledgeChunkModel, RetrievalTraceModel, RetrievalHitModel


def test_knowledge_models_schema():
    assert KnowledgeDocumentModel.__tablename__ == "knowledge_documents"
    assert KnowledgeChunkModel.__tablename__ == "knowledge_chunks"
    assert RetrievalTraceModel.__tablename__ == "retrieval_traces"
    assert RetrievalHitModel.__tablename__ == "retrieval_hits"
