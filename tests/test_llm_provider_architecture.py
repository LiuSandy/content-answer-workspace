"""Architecture constraints for the v3 provider plugin boundary."""

from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from app.bootstrap.container import build_llm_gateway
from app.plugins.llm.providers.deepseek.provider import DeepSeekProvider
from app.shared.llm.config import LLMProviderConfig
from app.shared.llm.dto import ProviderLLMRequest


class _StructuredValue(BaseModel):
    answer: str


def test_deepseek_declares_only_supported_structured_methods() -> None:
    provider = DeepSeekProvider(
        LLMProviderConfig(
            api_key="test",
            base_url="https://example.test/v1",
            default_model="deepseek-test",
        )
    )
    assert provider.key == "deepseek"
    assert provider.capabilities.structured_methods == ("json_mode", "function_calling")


def test_bootstrap_registry_contains_final_provider_set() -> None:
    gateway = build_llm_gateway()
    assert gateway._resolver._registry.keys() == ("deepseek", "kimi", "minimax", "glm")


@pytest.mark.asyncio
async def test_provider_uses_chat_openai_structured_output(monkeypatch) -> None:
    provider = DeepSeekProvider(
        LLMProviderConfig(
            api_key="test",
            base_url="https://example.test/v1",
            default_model="deepseek-test",
        )
    )
    captured = {}

    class _Runnable:
        async def ainvoke(self, messages):
            captured["messages"] = messages
            return {
                "raw": object(),
                "parsed": _StructuredValue(answer="validated"),
                "parsing_error": None,
            }

    class _Model:
        def bind(self, **kwargs):
            captured["bind"] = kwargs
            return self

        def with_structured_output(self, schema, *, method, include_raw, **kwargs):
            captured["schema"] = schema
            captured["method"] = method
            captured["include_raw"] = include_raw
            captured["structured_kwargs"] = kwargs
            return _Runnable()

    monkeypatch.setattr(provider, "_get_model", lambda model: _Model())
    value = await provider.invoke_structured(
        ProviderLLMRequest(
            messages=[{"role": "user", "content": "return a value"}],
            model="deepseek-test",
        ),
        schema=_StructuredValue,
        method="json_mode",
    )

    assert value == _StructuredValue(answer="validated")
    assert captured["schema"] is _StructuredValue
    assert captured["method"] == "json_mode"
    assert captured["include_raw"] is True


@pytest.mark.asyncio
async def test_provider_uses_chat_openai_for_generate_and_stream(monkeypatch) -> None:
    provider = DeepSeekProvider(
        LLMProviderConfig(
            api_key="test",
            base_url="https://example.test/v1",
            default_model="deepseek-test",
        )
    )

    class _Model:
        def bind(self, **kwargs):
            return self

        async def ainvoke(self, messages):
            return SimpleNamespace(
                content="complete",
                usage_metadata={"input_tokens": 3, "output_tokens": 2},
                response_metadata={
                    "model_name": "deepseek-test",
                    "finish_reason": "stop",
                },
            )

        async def astream(self, messages):
            yield SimpleNamespace(
                content="chunk",
                usage_metadata={"input_tokens": 3, "output_tokens": 1},
                response_metadata={"finish_reason": "stop"},
            )

    monkeypatch.setattr(provider, "_get_model", lambda model: _Model())
    request = ProviderLLMRequest(
        messages=[{"role": "user", "content": "hello"}],
        model="deepseek-test",
    )

    response = await provider.generate(request)
    chunks = [chunk async for chunk in provider.stream(request)]

    assert response.content == "complete"
    assert response.input_tokens == 3
    assert response.output_tokens == 2
    assert response.finish_reason == "stop"
    assert chunks[0].delta == "chunk"
    assert chunks[0].input_tokens == 3


def test_llm_provider_has_no_direct_openai_sdk_path() -> None:
    source = (
        Path(__file__).resolve().parent.parent
        / "app"
        / "plugins"
        / "llm"
        / "common"
        / "openai_compatible.py"
    ).read_text(encoding="utf-8")

    assert "from langchain_openai import ChatOpenAI" in source
    assert "from openai import" not in source
    assert "AsyncOpenAI" not in source
    assert ".chat.completions" not in source


def test_backend_has_no_async_openai_client() -> None:
    app_root = Path(__file__).resolve().parent.parent / "app"
    violations = []
    for path in app_root.rglob("*.py"):
        if "AsyncOpenAI" in path.read_text(encoding="utf-8"):
            violations.append(path.relative_to(app_root).as_posix())
    assert violations == []


def test_provider_configuration_does_not_leak_into_business_modules() -> None:
    app_root = Path(__file__).resolve().parent.parent / "app"
    violations = []
    for path in (app_root / "modules").rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        if any(name in source for name in ("DEEPSEEK_", "KIMI_", "MINIMAX_", "GLM_")):
            violations.append(path.relative_to(app_root).as_posix())
    assert violations == []


def test_application_layers_do_not_import_provider_internals() -> None:
    app_root = Path(__file__).resolve().parent.parent / "app"
    forbidden = ("LLMResolver", "LLMProviderRegistry", "AsyncOpenAI", "ChatOpenAI")
    violations = []
    for path in (app_root / "modules").glob("*/application/*.py"):
        source = path.read_text(encoding="utf-8")
        if any(name in source for name in forbidden):
            violations.append(path.relative_to(app_root).as_posix())
    assert violations == []


def test_business_modules_do_not_import_llm_plugins_or_legacy_llm_ports() -> None:
    app_root = Path(__file__).resolve().parent.parent / "app"
    violations = []
    forbidden = (
        "from app.plugins.llm",
        "import app.plugins.llm",
        "from app.shared.ports import LLMProvider",
        "StructuredGenerationPort",
    )
    for path in (app_root / "modules").rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        if any(marker in source for marker in forbidden):
            violations.append(path.relative_to(app_root).as_posix())
    assert violations == []
