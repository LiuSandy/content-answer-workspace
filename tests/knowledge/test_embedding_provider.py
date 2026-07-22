import pytest
from app.infrastructure.knowledge.embedding import MockEmbeddingProvider


@pytest.mark.asyncio
async def test_mock_embedding_provider():
    provider = MockEmbeddingProvider(dimensions=1536)
    embeddings = await provider.embed(["hello world", "knowledge base"])
    assert len(embeddings) == 2
    assert len(embeddings[0]) == 1536
