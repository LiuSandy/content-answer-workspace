"""MiniMax implementation using its OpenAI-compatible endpoint."""
from __future__ import annotations

from ..openai_compatible import OpenAICompatibleProvider
from .settings import MiniMaxSettings


class MiniMaxProvider(OpenAICompatibleProvider):
    key = "minimax"
    structured_methods = ["generic_parse"]

    def __init__(self, settings: MiniMaxSettings | None = None) -> None:
        resolved = settings or MiniMaxSettings.from_env()
        super().__init__(
            key=self.key,
            api_key=resolved.api_key,
            base_url=resolved.base_url,
            model=resolved.model,
        )
