"""LLM Provider registration and default-provider wiring."""
from __future__ import annotations

import logging
import os

from app.contracts.ports import LLMProvider

logger = logging.getLogger(__name__)


class LLMProviderRegistry:
    """维护已注册的 LLM Provider，按 key 路由调用。"""

    def __init__(self) -> None:
        self._providers: dict[str, LLMProvider] = {}

    def register(self, provider: LLMProvider) -> None:
        self._providers[provider.key] = provider
        logger.info("Registered LLM provider: %s", provider.key)

    def get(self, key: str) -> LLMProvider:
        if key not in self._providers:
            raise KeyError(
                f"LLM provider '{key}' not registered. Available: {list(self._providers)}"
            )
        return self._providers[key]

    def get_default(self) -> LLMProvider:
        """Return the provider selected at the application wiring boundary."""
        key = os.getenv("LLM_PROVIDER", "deepseek").strip() or "deepseek"
        return self.get(key)

    def get_default_model(self, purpose: str | None = None) -> str:
        """Resolve model names through the active provider's configuration."""
        provider = self.get_default()
        resolver = getattr(provider, "model_for", None)
        if callable(resolver):
            return str(resolver(purpose))
        model = getattr(provider, "default_model", None)
        if not model:
            raise RuntimeError(
                f"LLM provider '{provider.key}' does not declare a default model"
            )
        return str(model)

    def get_langchain_chat_model(self) -> object:
        """Request a LangChain-compatible model from the active provider."""
        provider = self.get_default()
        factory = getattr(provider, "get_langchain_chat_model", None)
        if not callable(factory):
            raise RuntimeError(
                f"LLM provider '{provider.key}' does not support LangChain chat models"
            )
        return factory()

    def get_structured_methods(self, key: str) -> list[str]:
        """返回 provider 声明的结构化输出能力（roadmap R1）。"""
        provider = self.get(key)
        return list(
            getattr(provider, "structured_methods", ["json_mode", "generic_parse"])
        )

    def list_keys(self) -> list[str]:
        return list(self._providers.keys())


def build_default_registry() -> LLMProviderRegistry:
    """Build the registry through the configured provider registration boundary."""
    from .providers.deepseek.registration import build_deepseek_registry

    return build_deepseek_registry(LLMProviderRegistry)


# 全局单例
llm_provider_registry = build_default_registry()
