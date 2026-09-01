from app.shared.llm.config import LLMProviderConfig

from ...registry import LLMProviderRegistry
from .provider import DeepSeekProvider


def register_deepseek(
    registry: LLMProviderRegistry, config: LLMProviderConfig
) -> None:
    registry.register(DeepSeekProvider(config))
