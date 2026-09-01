"""Shared adapter for vendor endpoints implementing the OpenAI chat API."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, TypeVar

from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from app.shared.llm.config import LLMProviderConfig
from app.shared.llm.dto import (
    AgentLLMResponse,
    LLMResponse,
    LLMStreamEvent,
    LLMToolCall,
    ProviderAgentLLMRequest,
    ProviderLLMRequest,
    StructuredMethod,
)
from app.shared.llm.errors import LLMProviderError

from ..capabilities import LLMCapabilities

T = TypeVar("T", bound=BaseModel)


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
        self._models: dict[str, ChatOpenAI] = {}

    @property
    def capabilities(self) -> LLMCapabilities:
        return self._capabilities

    def _get_model(self, model: str) -> ChatOpenAI:
        if model not in self._models:
            self._models[model] = ChatOpenAI(
                api_key=self._config.api_key,
                base_url=self._config.base_url,
                model=model,
                timeout=self._config.timeout_seconds,
                stream_usage=True,
            )
        return self._models[model]

    @staticmethod
    def _content(value: Any) -> str:
        content = getattr(value, "content", "")
        if isinstance(content, str):
            return content
        text = getattr(value, "text", None)
        return text if isinstance(text, str) else str(content)

    @staticmethod
    def _usage(value: Any) -> tuple[int | None, int | None]:
        usage = getattr(value, "usage_metadata", None) or {}
        return usage.get("input_tokens"), usage.get("output_tokens")

    @staticmethod
    def _response_metadata(value: Any) -> tuple[str | None, str | None]:
        metadata = getattr(value, "response_metadata", None) or {}
        return metadata.get("model_name") or metadata.get("model"), metadata.get(
            "finish_reason"
        )

    @staticmethod
    def _messages(request: ProviderLLMRequest) -> list[dict[str, Any]]:
        return [message.model_dump() for message in request.messages]

    def _configured_model(self, request: ProviderLLMRequest):
        return self._get_model(request.model).bind(
            temperature=request.temperature,
            max_completion_tokens=request.max_tokens,
            **request.extra,
        )

    async def generate(self, request: ProviderLLMRequest) -> LLMResponse:
        try:
            message = await self._configured_model(request).ainvoke(
                self._messages(request)
            )
        except Exception as error:
            raise LLMProviderError(f"{self.key} generation failed: {error}") from error
        input_tokens, output_tokens = self._usage(message)
        model, finish_reason = self._response_metadata(message)
        return LLMResponse(
            content=self._content(message),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model=model or request.model,
            finish_reason=finish_reason,
        )

    async def invoke_structured(
        self,
        request: ProviderLLMRequest,
        *,
        schema: type[T],
        method: StructuredMethod,
    ) -> T:
        """Use LangChain's provider-aware structured-output adapter.

        ``include_raw`` preserves the parsing error reported by LangChain while
        the returned value is validated once more against our application
        schema before it crosses the plugin boundary.
        """

        try:
            structured = self._get_model(request.model).with_structured_output(
                schema,
                method=method,
                include_raw=True,
                temperature=request.temperature,
                max_completion_tokens=request.max_tokens,
                **request.extra,
            )
            result = await structured.ainvoke(self._messages(request))
            parsing_error = result.get("parsing_error")
            if parsing_error is not None:
                raise ValueError(str(parsing_error)) from parsing_error
            parsed = result.get("parsed")
            if parsed is None:
                raise ValueError("structured model returned no parsed value")
            return (
                parsed
                if isinstance(parsed, schema)
                else schema.model_validate(parsed)
            )
        except Exception as error:
            raise LLMProviderError(
                f"{self.key} structured generation ({method}) failed: {error}"
            ) from error

    async def stream(
        self, request: ProviderLLMRequest
    ) -> AsyncIterator[LLMStreamEvent]:
        try:
            async for chunk in self._configured_model(request).astream(
                self._messages(request)
            ):
                input_tokens, output_tokens = self._usage(chunk)
                _, finish_reason = self._response_metadata(chunk)
                yield LLMStreamEvent(
                    delta=self._content(chunk),
                    finish_reason=finish_reason,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                )
        except Exception as error:
            raise LLMProviderError(f"{self.key} stream failed: {error}") from error

    async def invoke_with_tools(
        self, request: ProviderAgentLLMRequest
    ) -> AgentLLMResponse:
        try:
            bound = self._get_model(request.model).bind_tools(
                list(request.tools),
                temperature=request.temperature,
                max_completion_tokens=request.max_tokens,
            )
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
