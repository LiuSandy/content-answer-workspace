"""Resolve a business purpose to one registered provider and model."""

from __future__ import annotations

from dataclasses import dataclass

from app.shared.llm.config import LLMBinding, LLMRuntimeConfig
from app.shared.llm.errors import LLMConfigurationError

from .provider import LLMProvider
from .registry import LLMProviderRegistry


@dataclass(frozen=True, slots=True)
class ResolvedLLM:
    provider: LLMProvider
    model: str


class LLMResolver:
    def __init__(
        self, *, config: LLMRuntimeConfig, registry: LLMProviderRegistry
    ) -> None:
        self._config = config
        self._registry = registry

    def resolve(
        self,
        purpose: str,
        *,
        provider: str | None = None,
        model: str | None = None,
    ) -> ResolvedLLM:
        configured = self._config.default
        binding = LLMBinding(
            provider=(provider or configured.provider).strip(),
            model=model if model is not None else configured.model,
        )
        if binding.provider not in self._config.providers:
            raise LLMConfigurationError(
                f"No connection configuration for provider '{binding.provider}'"
            )
        provider = self._registry.get(binding.provider)
        model = self._resolve_model(binding)
        return ResolvedLLM(provider=provider, model=model)

    def _resolve_model(self, binding: LLMBinding) -> str:
        if binding.model and binding.model.strip():
            return binding.model.strip()
        provider_config = self._config.providers[binding.provider]
        if provider_config.default_model.strip():
            return provider_config.default_model.strip()
        raise LLMConfigurationError(
            f"No model configured for provider '{binding.provider}'"
        )
