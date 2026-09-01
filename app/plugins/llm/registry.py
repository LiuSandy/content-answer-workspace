"""Registry for concrete LLM provider plugins."""

from __future__ import annotations

from app.shared.llm.errors import LLMProviderNotFoundError

from .provider import LLMProvider


class LLMProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, LLMProvider] = {}

    def register(self, provider: LLMProvider) -> None:
        if provider.key in self._providers:
            raise ValueError(f"LLM provider already registered: {provider.key}")
        self._providers[provider.key] = provider

    def get(self, key: str) -> LLMProvider:
        try:
            return self._providers[key]
        except KeyError as error:
            raise LLMProviderNotFoundError(
                f"LLM provider '{key}' is not registered; "
                f"available={sorted(self._providers)}"
            ) from error

    def keys(self) -> tuple[str, ...]:
        return tuple(self._providers)
