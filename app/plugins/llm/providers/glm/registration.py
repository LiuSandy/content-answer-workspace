from app.shared.llm.config import LLMProviderConfig

from ...registry import LLMProviderRegistry
from .provider import GLMProvider


def register_glm(registry: LLMProviderRegistry, config: LLMProviderConfig) -> None:
    registry.register(GLMProvider(config))
