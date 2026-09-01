"""Internal contract implemented by concrete vendor plugins."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol

from app.shared.llm.dto import (
    AgentLLMResponse,
    LLMResponse,
    LLMStreamEvent,
    ProviderAgentLLMRequest,
    ProviderLLMRequest,
)

from .capabilities import LLMCapabilities


class LLMProvider(Protocol):
    key: str

    @property
    def capabilities(self) -> LLMCapabilities: ...

    async def generate(self, request: ProviderLLMRequest) -> LLMResponse: ...

    def stream(self, request: ProviderLLMRequest) -> AsyncIterator[LLMStreamEvent]: ...

    async def invoke_with_tools(
        self, request: ProviderAgentLLMRequest
    ) -> AgentLLMResponse: ...
