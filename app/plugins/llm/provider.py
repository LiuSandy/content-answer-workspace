"""Internal contract implemented by concrete vendor plugins."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol, TypeVar

from pydantic import BaseModel

from app.shared.llm.dto import (
    AgentLLMResponse,
    LLMResponse,
    LLMStreamEvent,
    ProviderAgentLLMRequest,
    ProviderLLMRequest,
    StructuredMethod,
)

from .capabilities import LLMCapabilities

T = TypeVar("T", bound=BaseModel)


class LLMProvider(Protocol):
    key: str

    @property
    def capabilities(self) -> LLMCapabilities: ...

    async def generate(self, request: ProviderLLMRequest) -> LLMResponse: ...

    async def invoke_structured(
        self,
        request: ProviderLLMRequest,
        *,
        schema: type[T],
        method: StructuredMethod,
    ) -> T: ...

    def stream(self, request: ProviderLLMRequest) -> AsyncIterator[LLMStreamEvent]: ...

    async def invoke_with_tools(
        self, request: ProviderAgentLLMRequest
    ) -> AgentLLMResponse: ...
