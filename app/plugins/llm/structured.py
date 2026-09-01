"""Gateway-owned structured generation with validation and fallback."""

from __future__ import annotations

import json
import re
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from app.shared.llm.dto import (
    LLMMessage,
    ProviderLLMRequest,
    StructuredLLMRequest,
    StructuredLLMResponse,
)

from .capabilities import StructuredMethod
from .provider import LLMProvider

T = TypeVar("T", bound=BaseModel)


def _response_format(method: StructuredMethod, schema: type[T]) -> dict[str, Any] | None:
    if method == "json_schema":
        return {
            "type": "json_schema",
            "json_schema": {
                "name": schema.__name__,
                "strict": True,
                "schema": schema.model_json_schema(),
            },
        }
    if method == "json_mode":
        return {"type": "json_object"}
    return None


def _extract_json(content: str) -> Any:
    text = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", content.strip())
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", text)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                return None
    return None


def _validate(content: str, schema: type[T]) -> T:
    payload = _extract_json(content)
    if payload is None:
        raise ValueError("LLM output contains no parseable JSON")
    try:
        return schema.model_validate(payload)
    except ValidationError as error:
        raise ValueError(f"structured output schema validation failed: {error}") from error


async def generate_structured(
    *,
    provider: LLMProvider,
    model: str,
    request: StructuredLLMRequest[T],
) -> StructuredLLMResponse[T]:
    methods = provider.capabilities.structured_methods or ("generic_parse",)
    reasons: list[str] = []
    attempts = 0
    messages = [LLMMessage.model_validate(message) for message in request.messages]

    for method in methods:
        for _ in range(request.retries + 1):
            attempts += 1
            provider_request = ProviderLLMRequest(
                messages=messages,
                model=model,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                response_format=_response_format(method, request.schema),
                extra=request.extra,
            )
            try:
                response = await provider.generate(provider_request)
                value = _validate(response.content, request.schema)
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
