"""MiniMax provider plugin."""

from app.shared.llm.config import LLMProviderConfig

from ...capabilities import LLMCapabilities
from ...common.openai_compatible import OpenAICompatibleProvider


class MiniMaxProvider(OpenAICompatibleProvider):
    def __init__(self, config: LLMProviderConfig) -> None:
        super().__init__(
            key="minimax",
            config=config,
            capabilities=LLMCapabilities(structured_methods=("function_calling",)),
        )
