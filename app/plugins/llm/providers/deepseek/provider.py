"""DeepSeek provider plugin."""

from app.shared.llm.config import LLMProviderConfig

from ...capabilities import LLMCapabilities
from ...common.openai_compatible import OpenAICompatibleProvider


class DeepSeekProvider(OpenAICompatibleProvider):
    def __init__(self, config: LLMProviderConfig) -> None:
        super().__init__(
            key="deepseek",
            config=config,
            capabilities=LLMCapabilities(
                structured_methods=("json_mode", "function_calling"),
            ),
        )
