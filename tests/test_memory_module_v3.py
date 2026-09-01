from __future__ import annotations

import pytest

from app.modules.memory.application import MemoryExtractionUseCase
from app.modules.memory.domain import ExtractedMemory, MemoryExtractionBatch
from app.modules.memory.ports import MemoryExtractionPrompt, MemorySaveResult
from app.shared.llm.dto import (
    LLMMessage,
    StructuredLLMResponse,
)


class _Gateway:
    async def generate_structured(self, *, purpose, request):
        assert purpose == "memory.extraction"
        assert request.schema is MemoryExtractionBatch
        return StructuredLLMResponse(
            value=MemoryExtractionBatch(
                [
                    ExtractedMemory(
                        memory_type="explicit",
                        memory_scope="writing_style",
                        content="用户偏好简洁表达",
                        confidence=0.9,
                    )
                ]
            ),
            method_used="json_mode",
            attempts=1,
        )


class _InvalidGateway:
    async def generate_structured(self, *, purpose, request):
        return StructuredLLMResponse(
            value=None,
            method_used="function_calling",
            attempts=2,
            degradation_reason="schema validation failed",
        )


class _Prompts:
    def render(self, conversation):
        assert conversation[0]["content"] == "请简洁一些"
        return MemoryExtractionPrompt(
            messages=[LLMMessage(role="user", content="extract")],
            temperature=0.2,
            max_tokens=1000,
        )


class _Embeddings:
    async def embed(self, texts):
        assert texts == ["用户偏好简洁表达"]
        return [[0.1, 0.2]]


class _Repository:
    def __init__(self) -> None:
        self.saved = []

    async def save_extracted(self, **values):
        self.saved.append(values)
        return MemorySaveResult(saved=len(values["memories"]))


@pytest.mark.asyncio
async def test_memory_extraction_application_depends_only_on_ports() -> None:
    repository = _Repository()
    use_case = MemoryExtractionUseCase(
        llm=_Gateway(),
        prompts=_Prompts(),
        embeddings=_Embeddings(),
        repository=repository,
    )

    outcome = await use_case.execute(
        conversation=[{"role": "user", "content": "请简洁一些"}],
        idempotency_key="run-1",
    )

    assert outcome.extracted == 1
    assert outcome.saved == 1
    assert repository.saved[0]["source"] == "run:run-1"
    assert repository.saved[0]["embeddings"] == [[0.1, 0.2]]


@pytest.mark.asyncio
async def test_invalid_memory_extraction_is_never_persisted() -> None:
    repository = _Repository()
    use_case = MemoryExtractionUseCase(
        llm=_InvalidGateway(),
        prompts=_Prompts(),
        embeddings=_Embeddings(),
        repository=repository,
    )

    outcome = await use_case.execute(
        conversation=[{"role": "user", "content": "请简洁一些"}],
        idempotency_key="run-invalid",
    )

    assert outcome.saved == 0
    assert repository.saved == []
