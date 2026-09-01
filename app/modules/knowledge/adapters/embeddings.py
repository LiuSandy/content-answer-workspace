"""Knowledge-owned adapter for the configured embedding provider."""

from __future__ import annotations

from typing import Any

from app.modules.knowledge.ports import EmbeddingPort
from app.plugins.embeddings.provider import validate_embeddings


class KnowledgeEmbeddingAdapter:
    """Expose the plugin provider through Knowledge's embedding port."""

    def __init__(self, provider: Any) -> None:
        self._provider = provider

    async def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = await self._provider.embed(texts)
        dimensions = getattr(self._provider, "dimensions", None)
        if dimensions is not None:
            validate_embeddings(texts, vectors, dimensions)
        return [list(vector) for vector in vectors]


def get_embedding_adapter() -> EmbeddingPort:
    """Build the Knowledge embedding adapter from the configured plugin."""

    from app.plugins.embeddings import get_embedding_provider

    return KnowledgeEmbeddingAdapter(get_embedding_provider())
