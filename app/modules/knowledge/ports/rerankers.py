"""Reranking boundary owned by Knowledge."""

from typing import Protocol


class RerankerPort(Protocol):
    async def rerank(self, query: str, documents: list[str]) -> list[float]: ...
