"""DeepSeek implementation of the project-wide LLMProvider contract."""
from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from app.contracts.dto import LLMMessage, LLMRequest, LLMResponse, LLMStreamEvent

from .client import DeepSeekClient
from .settings import DeepSeekSettings, load_deepseek_settings


class DeepSeekProvider:
    """Translate project DTOs to and from the DeepSeek-compatible API."""

    key: str = "deepseek"
    structured_methods: list[str] = ["json_mode", "generic_parse"]

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        client: DeepSeekClient | None = None,
        settings: DeepSeekSettings | None = None,
    ) -> None:
        self._settings = settings or load_deepseek_settings()
        self._client = client or DeepSeekClient(
            api_key=api_key,
            base_url=base_url,
            settings=self._settings,
        )

    @property
    def default_model(self) -> str:
        return self._settings.model

    def model_for(self, purpose: str | None = None) -> str:
        if purpose == "topic_expansion":
            return self._settings.topic_expansion_model
        return self._settings.model

    def get_langchain_chat_model(self) -> Any:
        """Return the reusable unbound LangChain model."""
        return self._client.get_langchain_chat_model()

    def _to_openai_messages(self, messages: list[LLMMessage]) -> list[dict[str, Any]]:
        return [{"role": message.role, "content": message.content} for message in messages]

    async def generate(self, request: LLMRequest) -> LLMResponse:
        """Generate one complete response and normalize vendor metadata."""
        params = dict(request.extra or {})
        if request.response_format is not None:
            params["response_format"] = request.response_format
        response = await self._client.create_chat_completion(
            model=request.model,
            messages=self._to_openai_messages(request.messages),
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            stream=False,
            **params,
        )
        choice = response.choices[0]
        return LLMResponse(
            content=choice.message.content or "",
            input_tokens=response.usage.prompt_tokens if response.usage else None,
            output_tokens=response.usage.completion_tokens if response.usage else None,
            model=response.model,
            finish_reason=choice.finish_reason,
        )

    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMStreamEvent]:
        """Stream normalized text deltas and final token usage."""
        stream = await self._client.create_chat_completion(
            model=request.model,
            messages=self._to_openai_messages(request.messages),
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            stream=True,
            **(request.extra or {}),
        )
        async for chunk in stream:
            choice = chunk.choices[0] if chunk.choices else None
            delta = choice.delta.content if choice and choice.delta else ""
            usage = getattr(chunk, "usage", None)
            yield LLMStreamEvent(
                delta=delta or "",
                finish_reason=choice.finish_reason if choice else None,
                input_tokens=usage.prompt_tokens if usage else None,
                output_tokens=usage.completion_tokens if usage else None,
            )
