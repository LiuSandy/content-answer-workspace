"""Gateway-owned structured generation strategy and audit metadata."""

from __future__ import annotations

from typing import TypeVar

from pydantic import BaseModel

from app.shared.llm.dto import (
    ProviderLLMRequest,
    StructuredLLMRequest,
    StructuredLLMResponse,
)
from app.shared.llm.errors import LLMConfigurationError

from .provider import LLMProvider

T = TypeVar("T", bound=BaseModel)


async def generate_structured(
    *,
    provider: LLMProvider,
    model: str,
    request: StructuredLLMRequest[T],
) -> StructuredLLMResponse[T]:
    provider_methods = provider.capabilities.structured_methods
    requested_methods = request.structured_methods
    if requested_methods is not None:
        unsupported = [
            method for method in requested_methods if method not in provider_methods
        ]
        if unsupported:
            raise LLMConfigurationError(
                f"Provider '{provider.key}' does not support structured methods: "
                + ", ".join(unsupported)
            )
        methods = requested_methods
    else:
        methods = provider_methods

    if not methods:
        raise LLMConfigurationError(
            f"Provider '{provider.key}' declares no structured output method"
        )

    reasons: list[str] = []
    attempts = 0
    provider_request = ProviderLLMRequest(
        messages=list(request.messages),
        model=model,
        temperature=request.temperature,
        max_tokens=request.max_tokens,
        extra=request.extra,
    )

    for method in methods:
        for _ in range(request.retries + 1):
            attempts += 1
            try:
                value = await provider.invoke_structured(
                    provider_request,
                    schema=request.schema,
                    method=method,
                )
                value = request.schema.model_validate(value)
            except Exception as error:  # each failure advances the declared strategy
                reasons.append(f"{method}: {error}")
                continue
            return StructuredLLMResponse(
                value=value,
                method_used=method,
                attempts=attempts,
                degradation_reason="; ".join(reasons) or None,
            )

    return StructuredLLMResponse(
        value=None,
        method_used=methods[-1],
        attempts=attempts,
        degradation_reason="; ".join(reasons) or "all structured methods exhausted",
    )
