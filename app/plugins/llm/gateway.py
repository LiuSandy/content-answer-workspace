"""Concrete LLM gateway hidden behind the shared application port."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TypeVar

from pydantic import BaseModel

from app.shared.llm.dto import (
    AgentLLMRequest,
    AgentLLMResponse,
    LLMRequest,
    LLMResponse,
    LLMStreamEvent,
    ProviderAgentLLMRequest,
    ProviderLLMRequest,
    StructuredLLMRequest,
    StructuredLLMResponse,
)

from .resolver import LLMResolver
from .structured import generate_structured

T = TypeVar("T", bound=BaseModel)


class PluginLLMGateway:
    def __init__(self, *, resolver: LLMResolver) -> None:
        self._resolver = resolver

    async def generate(self, *, purpose: str, request: LLMRequest) -> LLMResponse:
        resolved = self._resolver.resolve(
            purpose, provider=request.provider, model=request.model
        )
        return await resolved.provider.generate(
            ProviderLLMRequest(
                **request.model_dump(exclude={"provider", "model"}),
                model=resolved.model,
            )
        )

    async def stream(
        self, *, purpose: str, request: LLMRequest
    ) -> AsyncIterator[LLMStreamEvent]:
        resolved = self._resolver.resolve(
            purpose, provider=request.provider, model=request.model
        )
        provider_request = ProviderLLMRequest(
            **request.model_dump(exclude={"provider", "model"}),
            model=resolved.model,
        )
        async for event in resolved.provider.stream(provider_request):
            yield event

    async def invoke_with_tools(
        self, *, purpose: str, request: AgentLLMRequest
    ) -> AgentLLMResponse:
        resolved = self._resolver.resolve(
            purpose, provider=request.provider, model=request.model
        )
        provider_request = ProviderAgentLLMRequest(
            messages=request.messages,
            tools=request.tools,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            model=resolved.model,
        )
        return await resolved.provider.invoke_with_tools(provider_request)

    async def generate_structured(
        self, *, purpose: str, request: StructuredLLMRequest[T]
    ) -> StructuredLLMResponse[T]:
        resolved = self._resolver.resolve(
            purpose, provider=request.provider, model=request.model
        )
        return await generate_structured(
            provider=resolved.provider,
            model=resolved.model,
            request=request,
        )
