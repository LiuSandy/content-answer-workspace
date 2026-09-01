"""Memory prompt adapter backed by the existing prompt platform."""

from __future__ import annotations

import json

from app.platform.prompts.registry import PromptRegistry
from app.shared.llm.dto import LLMMessage

from ..ports.extraction import MemoryExtractionPrompt


class PromptRegistryMemoryExtractionPrompt:
    def __init__(self, registry: PromptRegistry) -> None:
        self._registry = registry

    def render(self, conversation: list[dict[str, str]]) -> MemoryExtractionPrompt:
        rendered = self._registry.render(
            "memory.extract",
            conversation=json.dumps(conversation, ensure_ascii=False),
        )
        return MemoryExtractionPrompt(
            messages=[LLMMessage.model_validate(message.model_dump()) for message in rendered.messages],
            provider=rendered.provider,
            model=rendered.model,
            temperature=rendered.temperature,
            max_tokens=rendered.max_tokens,
        )
