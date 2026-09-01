"""GLM provider plugin using its OpenAI-compatible endpoint."""

from app.shared.llm.config import LLMProviderConfig

from ...capabilities import LLMCapabilities
from ...common.openai_compatible import OpenAICompatibleProvider


class GLMProvider(OpenAICompatibleProvider):
    def __init__(self, config: LLMProviderConfig) -> None:
        super().__init__(
            key="glm",
            config=config,
            capabilities=LLMCapabilities(structured_methods=("function_calling",)),
        )
