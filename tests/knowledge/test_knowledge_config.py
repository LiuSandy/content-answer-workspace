import pytest
from app.core.config import KnowledgeSettings, get_knowledge_settings


def test_knowledge_settings_defaults():
    settings = get_knowledge_settings()
    assert str(settings.sources_dir).endswith("output/knowledge/sources")
    assert str(settings.documents_dir).endswith("output/knowledge/documents")
    assert settings.embedding_dimensions == 1536
    assert settings.rrf_k == 60
    assert settings.evidence_threshold == 0.55
    assert settings.parent_chunk_max_tokens == 1200
    assert settings.child_chunk_max_tokens == 350
    assert settings.context_token_budget == 6000
