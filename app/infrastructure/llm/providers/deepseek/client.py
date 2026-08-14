"""Low-level DeepSeek OpenAI-compatible SDK client."""
from __future__ import annotations

import os
from typing import Any

from openai import AsyncOpenAI


class DeepSeekClient:
    """Owns DeepSeek connection configuration and raw SDK calls only."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self._custom_api_key = api_key
        self._custom_base_url = base_url
        self._sdk: AsyncOpenAI | None = None

    def get_sdk(self) -> AsyncOpenAI:
        """Create the asynchronous SDK client lazily and reuse it."""
        if self._sdk is None:
            api_key = self._custom_api_key or os.getenv("DEEPSEEK_API_KEY", "")
            base_url = (
                self._custom_base_url
                or os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
            ).strip().rstrip("/")
            self._sdk = AsyncOpenAI(api_key=api_key, base_url=base_url)
        return self._sdk

    async def create_chat_completion(self, **params: Any) -> Any:
        """Forward one chat-completion request to the vendor SDK."""
        return await self.get_sdk().chat.completions.create(**params)
