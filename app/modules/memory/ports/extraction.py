"""Outbound ports required by the memory extraction use case."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.shared.llm.dto import LLMMessage, StructuredMethod

from ..domain.extraction import ExtractedMemory


@dataclass(frozen=True, slots=True)
class MemoryExtractionPrompt:
    messages: list[LLMMessage]
    temperature: float
    max_tokens: int
    provider: str | None = None
    model: str | None = None
    structured_methods: tuple[StructuredMethod, ...] | None = None


class MemoryExtractionPromptPort(Protocol):
    def render(self, conversation: list[dict[str, str]]) -> MemoryExtractionPrompt: ...


class EmbeddingPort(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...


@dataclass(frozen=True, slots=True)
class MemorySaveResult:
    saved: int
    skipped: bool = False


class MemoryRepositoryPort(Protocol):
    async def save_extracted(
        self,
        *,
        workspace_id: str,
        source: str,
        memories: list[ExtractedMemory],
        embeddings: list[list[float] | None],
    ) -> MemorySaveResult: ...
