"""The sole LLM dependency exposed to business application code."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol, TypeVar

from pydantic import BaseModel

from .dto import (
    AgentLLMRequest,
    AgentLLMResponse,
    LLMRequest,
    LLMResponse,
    LLMStreamEvent,
    StructuredLLMRequest,
    StructuredLLMResponse,
)

T = TypeVar("T", bound=BaseModel)


class LLMGatewayPort(Protocol):
    async def generate(self, *, purpose: str, request: LLMRequest) -> LLMResponse: ...

    def stream(
        self, *, purpose: str, request: LLMRequest
    ) -> AsyncIterator[LLMStreamEvent]: ...

    async def invoke_with_tools(
        self, *, purpose: str, request: AgentLLMRequest
    ) -> AgentLLMResponse: ...

    async def generate_structured(
        self, *, purpose: str, request: StructuredLLMRequest[T]
    ) -> StructuredLLMResponse[T]: ...
