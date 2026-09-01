"""Shared adapter for vendor endpoints implementing the OpenAI chat API."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from langchain_openai import ChatOpenAI
from openai import AsyncOpenAI

from app.shared.llm.config import LLMProviderConfig
from app.shared.llm.dto import (
    AgentLLMResponse,
    LLMResponse,
    LLMStreamEvent,
    LLMToolCall,
    ProviderAgentLLMRequest,
    ProviderLLMRequest,
)
from app.shared.llm.errors import LLMProviderError

from ..capabilities import LLMCapabilities


class OpenAICompatibleProvider:
    """Translate project DTOs at the plugin boundary without exposing SDK responses."""

    key: str

    def __init__(
        self,
        *,
        key: str,
        config: LLMProviderConfig,
        capabilities: LLMCapabilities,
    ) -> None:
        self.key = key
        self._config = config
        self._capabilities = capabilities
        self._sdk: AsyncOpenAI | None = None
        self._tool_models: dict[str, ChatOpenAI] = {}

    @property
    def capabilities(self) -> LLMCapabilities:
        return self._capabilities

    def _get_sdk(self) -> AsyncOpenAI:
        if self._sdk is None:
            self._sdk = AsyncOpenAI(
                api_key=self._config.api_key,
                base_url=self._config.base_url,
                timeout=self._config.timeout_seconds,
            )
        return self._sdk

    def _get_tool_model(self, model: str) -> ChatOpenAI:
        if model not in self._tool_models:
            self._tool_models[model] = ChatOpenAI(
                api_key=self._config.api_key,
                base_url=self._config.base_url,
                model=model,
                timeout=self._config.timeout_seconds,
                streaming=True,
            )
        return self._tool_models[model]

    @staticmethod
    def _messages(request: ProviderLLMRequest) -> list[dict[str, Any]]:
        return [message.model_dump() for message in request.messages]

    def _params(self, request: ProviderLLMRequest, *, stream: bool) -> dict[str, Any]:
        params = dict(request.extra)
        params.update(
            model=request.model,
            messages=self._messages(request),
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            stream=stream,
        )
        if not stream and request.response_format is not None:
            params["response_format"] = request.response_format
        return params

    async def generate(self, request: ProviderLLMRequest) -> LLMResponse:
        try:
            response = await self._get_sdk().chat.completions.create(
                **self._params(request, stream=False)
            )
        except Exception as error:
            raise LLMProviderError(f"{self.key} generation failed: {error}") from error
        choice = response.choices[0]
        return LLMResponse(
            content=choice.message.content or "",
            input_tokens=response.usage.prompt_tokens if response.usage else None,
            output_tokens=response.usage.completion_tokens if response.usage else None,
            model=response.model,
            finish_reason=choice.finish_reason,
        )

    async def stream(
        self, request: ProviderLLMRequest
    ) -> AsyncIterator[LLMStreamEvent]:
        try:
            stream = await self._get_sdk().chat.completions.create(
                **self._params(request, stream=True)
            )
            async for chunk in stream:
                choice = chunk.choices[0] if chunk.choices else None
                usage = getattr(chunk, "usage", None)
                yield LLMStreamEvent(
                    delta=(choice.delta.content or "") if choice and choice.delta else "",
                    finish_reason=choice.finish_reason if choice else None,
                    input_tokens=usage.prompt_tokens if usage else None,
                    output_tokens=usage.completion_tokens if usage else None,
                )
        except Exception as error:
            raise LLMProviderError(f"{self.key} stream failed: {error}") from error

    async def invoke_with_tools(
        self, request: ProviderAgentLLMRequest
    ) -> AgentLLMResponse:
        try:
            bound = self._get_tool_model(request.model).bind_tools(list(request.tools))
            message = await bound.ainvoke(list(request.messages))
        except Exception as error:
            raise LLMProviderError(f"{self.key} tool call failed: {error}") from error

        tool_calls = [
            LLMToolCall(
                id=call.get("id"),
                name=str(call.get("name", "")),
                arguments=dict(call.get("args") or {}),
            )
            for call in (getattr(message, "tool_calls", None) or [])
        ]
        content = getattr(message, "content", "")
        return AgentLLMResponse(
            content=content if isinstance(content, str) else str(content),
            tool_calls=tool_calls,
        )
