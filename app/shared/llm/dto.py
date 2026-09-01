"""Provider-neutral request and response objects for LLM use cases."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T", bound=BaseModel)
StructuredMethod = Literal["json_schema", "json_mode", "function_calling"]


class LLMMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str


class LLMRequest(BaseModel):
    """Application-facing request with an optional route selected by its Prompt."""

    messages: list[LLMMessage]
    provider: str | None = None
    model: str | None = None
    temperature: float = 0.7
    max_tokens: int = Field(default=4096, gt=0)
    extra: dict[str, Any] = Field(default_factory=dict)


class ProviderLLMRequest(LLMRequest):
    """Plugin-internal request after purpose resolution."""

    model: str


class LLMResponse(BaseModel):
    content: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    model: str | None = None
    finish_reason: str | None = None


class LLMStreamEvent(BaseModel):
    delta: str = ""
    finish_reason: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None


class LLMToolCall(BaseModel):
    id: str | None = None
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AgentLLMRequest:
    """Tool-capable request; framework objects remain inside the agent adapter."""

    messages: Sequence[Any]
    tools: Sequence[Any]
    provider: str | None = None
    model: str | None = None
    temperature: float = 0.7
    max_tokens: int = 4096


@dataclass(frozen=True, slots=True)
class ProviderAgentLLMRequest(AgentLLMRequest):
    model: str = ""


class AgentLLMResponse(BaseModel):
    content: str = ""
    tool_calls: list[LLMToolCall] = Field(default_factory=list)


@dataclass(frozen=True, slots=True)
class StructuredLLMRequest(Generic[T]):
    messages: Sequence[LLMMessage]
    schema: type[T]
    provider: str | None = None
    model: str | None = None
    temperature: float = 0.1
    max_tokens: int = 4096
    retries: int = 1
    structured_methods: tuple[StructuredMethod, ...] | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class StructuredLLMResponse(Generic[T]):
    value: T | None
    method_used: StructuredMethod | None
    attempts: int
    degradation_reason: str | None = None
