import pytest
from pathlib import Path
from app.core.config import get_knowledge_settings, KnowledgeSettings

def test_knowledge_config_defaults():
    settings = get_knowledge_settings()
    assert isinstance(settings, KnowledgeSettings)
    assert settings.embedding_dimensions == 1536
    assert settings.rrf_k == 60
    assert settings.evidence_threshold == 0.55
    assert settings.parent_chunk_max_tokens == 1200
    assert settings.child_chunk_max_tokens == 350
    assert settings.context_token_budget == 6000
    assert settings.sources_dir.name == "sources"
    assert settings.documents_dir.name == "documents"
