"""LLM Provider Registry；根据 model_profiles 配置选择 Provider 实例。"""
from __future__ import annotations

import logging

from ...domain.ports import LLMProvider
from .providers.deepseek import DeepSeekProvider

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

    def list_keys(self) -> list[str]:
        return list(self._providers.keys())


def build_default_registry() -> LLMProviderRegistry:
    """构建包含默认 Provider 的 Registry；服务启动时调用。"""
    registry = LLMProviderRegistry()
    registry.register(DeepSeekProvider())
    return registry


# 全局单例
llm_provider_registry = build_default_registry()
