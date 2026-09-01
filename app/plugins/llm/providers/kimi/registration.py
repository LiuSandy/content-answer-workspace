from app.shared.llm.config import LLMProviderConfig

from ...registry import LLMProviderRegistry
from .provider import KimiProvider


def register_kimi(registry: LLMProviderRegistry, config: LLMProviderConfig) -> None:
    registry.register(KimiProvider(config))
