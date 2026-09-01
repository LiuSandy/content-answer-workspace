from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from pydantic import BaseModel

from app.bootstrap.container import build_llm_gateway
from app.platform.config.llm import load_llm_runtime_config
from app.platform.config.loader import get_settings
from app.modules.settings.application.settings import SettingsService
from app.plugins.llm.capabilities import LLMCapabilities
from app.plugins.llm.gateway import PluginLLMGateway
from app.plugins.llm.registry import LLMProviderRegistry
from app.plugins.llm.resolver import LLMResolver
from app.shared.llm.config import LLMBinding, LLMProviderConfig, LLMRuntimeConfig
from app.shared.llm.dto import (
    AgentLLMResponse,
    LLMRequest,
    LLMResponse,
    LLMStreamEvent,
    ProviderAgentLLMRequest,
    ProviderLLMRequest,
    StructuredLLMRequest,
)


class _StructuredValue(BaseModel):
    answer: str


class _FakeProvider:
    key = "fake"

    def __init__(self, responses: list[str] | None = None) -> None:
        self.requests: list[ProviderLLMRequest] = []
        self.responses = list(responses or ["ok"])

    @property
    def capabilities(self) -> LLMCapabilities:
        return LLMCapabilities(structured_methods=("json_mode", "generic_parse"))

    async def generate(self, request: ProviderLLMRequest) -> LLMResponse:
        self.requests.append(request)
        return LLMResponse(content=self.responses.pop(0))

    async def stream(
        self, request: ProviderLLMRequest
    ) -> AsyncIterator[LLMStreamEvent]:
        self.requests.append(request)
        yield LLMStreamEvent(delta="chunk")

    async def invoke_with_tools(
        self, request: ProviderAgentLLMRequest
    ) -> AgentLLMResponse:
        return AgentLLMResponse(content=request.model)


def _gateway(provider: _FakeProvider) -> PluginLLMGateway:
    registry = LLMProviderRegistry()
    registry.register(provider)
    config = LLMRuntimeConfig(
        default=LLMBinding(provider="fake"),
        providers={
            "fake": LLMProviderConfig(
                base_url="https://example.test/v1",
                default_model="fallback-model",
            )
        },
    )
    return PluginLLMGateway(resolver=LLMResolver(config=config, registry=registry))


def test_runtime_config_uses_prompt_route_then_default_provider_model(tmp_path: Path) -> None:
    path = tmp_path / "llm.toml"
    path.write_text(
        """
[llm.default]
provider = "deepseek"

[llm.providers.deepseek]
base_url = "https://default.test"
default_model = "provider-model"
""",
        encoding="utf-8",
    )
    config = load_llm_runtime_config(
        path,
        environ={
            "DEEPSEEK_API_KEY": "secret",
            "DEEPSEEK_BASE_URL": "https://override.test/",
            "DEEPSEEK_MODEL": "must-not-be-read",
        },
    )
    registry = LLMProviderRegistry()
    provider = _FakeProvider()
    provider.key = "deepseek"
    registry.register(provider)
    resolver = LLMResolver(config=config, registry=registry)

    assert resolver.resolve(
        "memory.extraction", provider="deepseek", model="prompt-model"
    ).model == "prompt-model"
    assert resolver.resolve("unknown").model == "provider-model"
    assert config.providers["deepseek"].api_key == "secret"
    assert config.providers["deepseek"].base_url == "https://override.test"


@pytest.mark.asyncio
async def test_request_without_prompt_route_uses_default_model() -> None:
    provider = _FakeProvider()
    gateway = _gateway(provider)
    request = LLMRequest(messages=[{"role": "user", "content": "hello"}])

    await gateway.generate(purpose="test.purpose", request=request)

    assert "model" not in request.model_fields_set
    assert provider.requests[0].model == "fallback-model"


@pytest.mark.asyncio
async def test_prompt_route_overrides_default_model() -> None:
    provider = _FakeProvider()
    gateway = _gateway(provider)
    request = LLMRequest(
        messages=[{"role": "user", "content": "hello"}],
        provider="fake",
        model="prompt-model",
    )

    await gateway.generate(purpose="any.purpose", request=request)

    assert provider.requests[0].model == "prompt-model"


@pytest.mark.asyncio
async def test_prompt_route_can_select_another_provider() -> None:
    default_provider = _FakeProvider()
    alternate_provider = _FakeProvider()
    alternate_provider.key = "alternate"
    registry = LLMProviderRegistry()
    registry.register(default_provider)
    registry.register(alternate_provider)
    config = LLMRuntimeConfig(
        default=LLMBinding(provider="fake", model="default-model"),
        providers={
            "fake": LLMProviderConfig(
                base_url="https://default.test/v1", default_model="default-model"
            ),
            "alternate": LLMProviderConfig(
                base_url="https://alternate.test/v1", default_model="alternate-default"
            ),
        },
    )
    gateway = PluginLLMGateway(
        resolver=LLMResolver(config=config, registry=registry)
    )

    await gateway.generate(
        purpose="writing.generate",
        request=LLMRequest(
            messages=[{"role": "user", "content": "hello"}],
            provider="alternate",
            model="prompt-selected-model",
        ),
    )

    assert default_provider.requests == []
    assert alternate_provider.requests[0].model == "prompt-selected-model"


@pytest.mark.asyncio
async def test_structured_generation_is_owned_by_gateway() -> None:
    provider = _FakeProvider(["not json", "{\"answer\": \"validated\"}"])
    gateway = _gateway(provider)

    result = await gateway.generate_structured(
        purpose="test.purpose",
        request=StructuredLLMRequest(
            messages=[{"role": "user", "content": "return json"}],
            schema=_StructuredValue,
            retries=1,
        ),
    )

    assert result.value == _StructuredValue(answer="validated")
    assert result.method_used == "json_mode"
    assert result.attempts == 2
    assert provider.requests[0].response_format == {"type": "json_object"}


def test_bootstrap_registers_the_final_provider_set() -> None:
    gateway = build_llm_gateway()
    registry = gateway._resolver._registry

    assert registry.keys() == ("deepseek", "kimi", "minimax", "glm")


def test_default_runtime_has_no_purpose_model_routes() -> None:
    config_text = (
        Path(__file__).parents[1]
        / "app"
        / "platform"
        / "config"
        / "defaults"
        / "llm.toml"
    ).read_text(encoding="utf-8")
    assert "[llm.purposes" not in config_text
    assert not hasattr(load_llm_runtime_config(), "purposes")


def test_legacy_llm_defaults_are_removed_from_general_settings() -> None:
    assert not hasattr(get_settings(), "llm")

    visible = SettingsService().get_all()["llm"]
    runtime = load_llm_runtime_config()
    provider = runtime.providers[runtime.default.provider]

    assert visible["baseUrl"] == provider.base_url
    assert visible["model"] == (runtime.default.model or provider.default_model)
