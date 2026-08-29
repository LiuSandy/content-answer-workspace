"""Reusable adapter for providers exposing OpenAI-compatible chat completions."""
from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from langchain_openai import ChatOpenAI
from openai import AsyncOpenAI

from app.contracts.dto import LLMMessage, LLMRequest, LLMResponse, LLMStreamEvent


class OpenAICompatibleProvider:
    """Implement the project LLM contract for an OpenAI-compatible endpoint."""

    structured_methods: list[str] = ["generic_parse"]

    def __init__(
        self,
        *,
        key: str,
        api_key: str,
        base_url: str,
        model: str,
    ) -> None:
        self.key = key
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._sdk: AsyncOpenAI | None = None
        self._langchain_model: ChatOpenAI | None = None

    @property
    def default_model(self) -> str:
        return self._model

    def model_for(self, purpose: str | None = None) -> str:
        return self._model

    def _get_sdk(self) -> AsyncOpenAI:
        if self._sdk is None:
            self._sdk = AsyncOpenAI(api_key=self._api_key, base_url=self._base_url)
        return self._sdk

    def _get_langchain_chat_model(self) -> ChatOpenAI:
        if self._langchain_model is None:
            self._langchain_model = ChatOpenAI(
                api_key=self._api_key,
                base_url=self._base_url,
                model=self._model,
                streaming=True,
            )
        return self._langchain_model

    async def ainvoke(
        self,
        messages: list[Any],
        tools: list[Any],
    ) -> Any:
        """Generate one LangChain message with provider-owned tool binding."""
        model = self._get_langchain_chat_model().bind_tools(tools)
        return await model.ainvoke(messages)

    @staticmethod
    def _messages(messages: list[LLMMessage]) -> list[dict[str, Any]]:
        return [{"role": message.role, "content": message.content} for message in messages]

    def _request_params(self, request: LLMRequest, *, stream: bool) -> dict[str, Any]:
        params = dict(request.extra or {})
        params.update(
            model=request.model,
            messages=self._messages(request.messages),
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            stream=stream,
        )
        if not stream and request.response_format is not None:
            params["response_format"] = request.response_format
        return params

    async def generate(self, request: LLMRequest) -> LLMResponse:
        response = await self._get_sdk().chat.completions.create(
            **self._request_params(request, stream=False)
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
        stream = await self._get_sdk().chat.completions.create(
            **self._request_params(request, stream=True)
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
