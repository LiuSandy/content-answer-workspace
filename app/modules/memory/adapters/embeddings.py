"""Compatibility adapter around the current embedding provider."""

from __future__ import annotations

from typing import Any


class ExistingEmbeddingAdapter:
    def __init__(self, provider: Any) -> None:
        self._provider = provider

    async def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = await self._provider.embed(texts)
        from app.plugins.embeddings.provider import validate_embeddings

        validate_embeddings(texts, vectors, self._provider.dimensions)
        return [list(vector) for vector in vectors]
