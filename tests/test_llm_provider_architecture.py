from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.contracts.dto import LLMMessage, LLMRequest
from app.infrastructure.llm.providers.deepseek import DeepSeekProvider
from app.infrastructure.llm.registry import LLMProviderRegistry


@pytest.mark.asyncio
async def test_deepseek_provider_delegates_transport_to_client() -> None:
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content="answer"),
                finish_reason="stop",
            )
        ],
        usage=SimpleNamespace(prompt_tokens=3, completion_tokens=5),
        model="deepseek-test",
    )
    client = SimpleNamespace(create_chat_completion=AsyncMock(return_value=response))
    provider = DeepSeekProvider(client=client)

    result = await provider.generate(
        LLMRequest(
            messages=[LLMMessage(role="user", content="question")],
            model="deepseek-test",
        )
    )

    assert result.content == "answer"
    assert result.input_tokens == 3
    assert result.output_tokens == 5
    client.create_chat_completion.assert_awaited_once()


def test_registry_selects_default_provider_from_environment(monkeypatch) -> None:
    deepseek = SimpleNamespace(key="deepseek")
    alternate = SimpleNamespace(key="alternate")
    registry = LLMProviderRegistry()
    registry.register(deepseek)
    registry.register(alternate)

    monkeypatch.setenv("LLM_PROVIDER", "alternate")

    assert registry.get_default() is alternate
