import math
from unittest.mock import MagicMock

import pytest

from app.plugins.embeddings.provider import (
    EmbeddingNotConfiguredError,
    MockEmbeddingProvider,
    get_embedding_provider,
    validate_embeddings,
)


@pytest.mark.asyncio
async def test_mock_embedding_provider():
    provider = MockEmbeddingProvider(dimensions=1536)
    embeddings = await provider.embed(["hello world", "knowledge base"])
    assert len(embeddings) == 2
    assert len(embeddings[0]) == 1536


def test_validate_embeddings_rejects_invalid_provider_output():
    validate_embeddings(["a"], [[0.1, 0.2]], expected_dimensions=2)

    with pytest.raises(ValueError, match="Expected 2 embeddings"):
        validate_embeddings(["a", "b"], [[0.1, 0.2]], expected_dimensions=2)
    with pytest.raises(ValueError, match="Expected 2 dimensions"):
        validate_embeddings(["a"], [[0.1]], expected_dimensions=2)
    with pytest.raises(ValueError, match="finite"):
        validate_embeddings(["a"], [[math.nan, 0.2]], expected_dimensions=2)


def test_production_factory_rejects_missing_key(monkeypatch):
    settings = MagicMock(embedding_api_key="", embedding_dimensions=1536)
    monkeypatch.setattr(
        "app.plugins.embeddings.provider.get_knowledge_settings",
        lambda: settings,
    )
    with pytest.raises(EmbeddingNotConfiguredError):
        get_embedding_provider()


def test_production_factory_rejects_missing_model(monkeypatch):
    settings = MagicMock(
        embedding_api_key="secret",
        embedding_model="",
        embedding_dimensions=1536,
    )
    monkeypatch.setattr(
        "app.plugins.embeddings.provider.get_knowledge_settings",
        lambda: settings,
    )
    with pytest.raises(EmbeddingNotConfiguredError, match="EMBEDDING_MODEL"):
        get_embedding_provider()


def test_memory_service_uses_knowledge_embedding_factory(monkeypatch):
    provider = MagicMock(dimensions=1536)
    factory = MagicMock(return_value=provider)
    monkeypatch.setattr(
        "app.plugins.embeddings.provider.get_embedding_provider", factory
    )

    from app.modules.memory.application.manage_memory import _get_embedding_provider

    assert _get_embedding_provider() is provider
    factory.assert_called_once_with()
