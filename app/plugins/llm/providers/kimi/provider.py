"""Kimi provider plugin."""

from app.shared.llm.config import LLMProviderConfig

from ...capabilities import LLMCapabilities
from ...common.openai_compatible import OpenAICompatibleProvider


class KimiProvider(OpenAICompatibleProvider):
    def __init__(self, config: LLMProviderConfig) -> None:
        super().__init__(
            key="kimi",
            config=config,
            capabilities=LLMCapabilities(structured_methods=("function_calling",)),
        )
