"""Extract and persist validated memories without depending on concrete adapters."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.shared.llm.dto import StructuredLLMRequest
from app.shared.llm.port import LLMGatewayPort

from ..domain.extraction import MemoryExtractionBatch
from ..ports.extraction import (
    EmbeddingPort,
    MemoryExtractionPromptPort,
    MemoryRepositoryPort,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class MemoryExtractionOutcome:
    extracted: int = 0
    saved: int = 0
    skipped: bool = False


class MemoryExtractionUseCase:
    def __init__(
        self,
        *,
        llm: LLMGatewayPort,
        prompts: MemoryExtractionPromptPort,
        embeddings: EmbeddingPort,
        repository: MemoryRepositoryPort,
    ) -> None:
        self._llm = llm
        self._prompts = prompts
        self._embeddings = embeddings
        self._repository = repository
        self._running_keys: set[str] = set()

    async def execute(
        self,
        *,
        conversation: list[dict[str, str]],
        idempotency_key: str,
        workspace_id: str = "default",
    ) -> MemoryExtractionOutcome:
        if not idempotency_key or idempotency_key in self._running_keys:
            return MemoryExtractionOutcome(skipped=True)

        self._running_keys.add(idempotency_key)
        try:
            prompt = self._prompts.render(conversation)
            structured = await self._llm.generate_structured(
                purpose="memory.extraction",
                request=StructuredLLMRequest(
                    messages=prompt.messages,
                    schema=MemoryExtractionBatch,
                    provider=prompt.provider,
                    model=prompt.model,
                    temperature=prompt.temperature,
                    max_tokens=prompt.max_tokens,
                ),
            )
            if structured.value is None:
                logger.warning(
                    "Memory extraction produced no validated value: %s",
                    structured.degradation_reason,
                )
                return MemoryExtractionOutcome()

            memories = structured.value.root
            embeddings = await self._embed_or_empty(
                [memory.content for memory in memories]
            )
            saved = await self._repository.save_extracted(
                workspace_id=workspace_id,
                source=f"run:{idempotency_key}",
                memories=memories,
                embeddings=embeddings,
            )
            return MemoryExtractionOutcome(
                extracted=len(memories),
                saved=saved.saved,
                skipped=saved.skipped,
            )
        except Exception as error:  # memory persistence must not block chat
            logger.warning(
                "Memory extraction failed for run %s: %s", idempotency_key, error
            )
            return MemoryExtractionOutcome()
        finally:
            self._running_keys.discard(idempotency_key)

    async def _embed_or_empty(
        self, contents: list[str]
    ) -> list[list[float] | None]:
        if not contents:
            return []
        try:
            vectors = await self._embeddings.embed(contents)
            if len(vectors) != len(contents):
                raise ValueError("embedding count does not match memory count")
            return [list(vector) for vector in vectors]
        except Exception as error:
            logger.warning("Memory embedding failed; persisting text only: %s", error)
            return [None] * len(contents)
