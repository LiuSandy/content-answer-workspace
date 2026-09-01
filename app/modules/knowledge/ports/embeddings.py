"""Embedding boundary owned by Knowledge."""

from typing import Protocol


class EmbeddingPort(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...
