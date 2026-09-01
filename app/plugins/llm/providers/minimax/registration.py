from app.shared.llm.config import LLMProviderConfig

from ...registry import LLMProviderRegistry
from .provider import MiniMaxProvider


def register_minimax(
    registry: LLMProviderRegistry, config: LLMProviderConfig
) -> None:
    registry.register(MiniMaxProvider(config))
