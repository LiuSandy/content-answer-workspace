from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.contracts.dto import LLMMessage, LLMRequest
from app.infrastructure.llm.providers.deepseek import DeepSeekProvider
from app.infrastructure.llm.providers.deepseek.settings import load_deepseek_settings
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


def test_deepseek_settings_are_loaded_in_provider_package(monkeypatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://example.test/v1/")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-test")

    settings = load_deepseek_settings()

    assert settings.api_key == "test-key"
    assert settings.base_url == "https://example.test/v1"
    assert settings.model == "deepseek-test"


def test_deepseek_configuration_and_registration_do_not_leak() -> None:
    app_root = Path(__file__).resolve().parent.parent / "app"
    provider_root = app_root / "infrastructure" / "llm" / "providers" / "deepseek"
    violations: list[str] = []

    for path in app_root.rglob("*.py"):
        if path.is_relative_to(provider_root):
            continue
        source = path.read_text(encoding="utf-8")
        if "DEEPSEEK_" in source or "ChatOpenAI(" in source:
            violations.append(str(path.relative_to(app_root)))

    assert violations == []

    registration_hits = [
        path
        for path in app_root.rglob("*.py")
        if "register(DeepSeekProvider())" in path.read_text(encoding="utf-8")
    ]
    assert registration_hits == [provider_root / "registration.py"]
