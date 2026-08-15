"""DeepSeek OpenAI-compatible SDK and LangChain clients."""
from __future__ import annotations

from typing import Any

from langchain_openai import ChatOpenAI
from openai import AsyncOpenAI

from .settings import DeepSeekSettings, load_deepseek_settings


class DeepSeekClient:
    """Owns DeepSeek connection configuration and reusable client variants."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        settings: DeepSeekSettings | None = None,
    ) -> None:
        resolved = settings or load_deepseek_settings()
        self._api_key = api_key or resolved.api_key
        self._base_url = (base_url or resolved.base_url).strip().rstrip("/")
        self._model = resolved.model
        self._sdk: AsyncOpenAI | None = None
        self._langchain_model: ChatOpenAI | None = None

    def get_sdk(self) -> AsyncOpenAI:
        """Create the asynchronous SDK client lazily and reuse it."""
        if self._sdk is None:
            self._sdk = AsyncOpenAI(api_key=self._api_key, base_url=self._base_url)
        return self._sdk

    async def create_chat_completion(self, **params: Any) -> Any:
        """Forward one chat-completion request to the vendor SDK."""
        return await self.get_sdk().chat.completions.create(**params)

    def get_langchain_chat_model(self) -> ChatOpenAI:
        """Create the unbound LangChain model lazily and reuse it."""
        if self._langchain_model is None:
            self._langchain_model = ChatOpenAI(
                api_key=self._api_key,
                base_url=self._base_url,
                model=self._model,
                streaming=True,
            )
        return self._langchain_model
