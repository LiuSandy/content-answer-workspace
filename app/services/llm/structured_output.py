"""Provider-agnostic structured-output generation and validation."""
from __future__ import annotations

import json
import logging
import re
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from app.contracts.dto import LLMRequest, StructuredResult
from app.contracts.ports import LLMProvider

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)

_METHOD_PRIORITY = ("json_schema", "json_mode", "generic_parse")
_DEFAULT_METHODS = ["json_mode", "generic_parse"]


def _response_format(method: str, schema: type[T]) -> dict[str, Any] | None:
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


def _with_response_format(request: LLMRequest, method: str, schema: type[T]) -> LLMRequest:
    fmt = _response_format(method, schema)
    if isinstance(request, LLMRequest):
        extra = dict(request.extra or {})
        extra.pop("response_format", None)
        return request.model_copy(update={"response_format": fmt, "extra": extra})
    request.response_format = fmt  # type: ignore[attr-defined]
    return request


def _extract_json(content: str) -> Any:
    text = content.strip()
    text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", text)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            return None
    return None


def _validate_content(content: str, schema: type[T]) -> T:
    payload = _extract_json(content)
    if payload is None:
        raise ValueError("LLM 输出中未找到可解析的 JSON")
    if not isinstance(payload, (dict, list)):
        raise ValueError("LLM 输出 JSON 不是对象或数组")
    try:
        return schema.model_validate(payload)
    except ValidationError as error:
        raise ValueError(f"schema 校验失败: {error}") from error


def _ordered_methods(structured_methods: Any) -> list[str]:
    if not isinstance(structured_methods, (list, tuple, set)) or not structured_methods:
        return list(_DEFAULT_METHODS)
    return (
        [method for method in _METHOD_PRIORITY if method in set(structured_methods)]
        or list(_DEFAULT_METHODS)
    )


async def generate_structured(
    provider: LLMProvider,
    request: LLMRequest,
    schema: type[T],
    structured_methods: list[str] | None = None,
    retries: int = 1,
) -> StructuredResult[T]:
    """Generate, parse, and validate structured output with declared fallbacks."""
    methods = _ordered_methods(structured_methods)
    reasons: list[str] = []
    attempts = 0

    for method in methods:
        for _ in range(retries + 1):
            attempts += 1
            req = _with_response_format(request, method, schema)
            try:
                response = await provider.generate(req)
                content = (getattr(response, "content", "") or "").strip()
                value = _validate_content(content, schema)
            except Exception as error:  # noqa: BLE001 - each failure degrades
                logger.warning(
                    "Structured generation %s attempt %d failed: %s",
                    method,
                    attempts,
                    error,
                )
                reasons.append(f"{method}: {error}")
                continue
            return StructuredResult(
                value=value,
                method_used=method,
                attempts=attempts,
                degradation_reason="; ".join(reasons) or None,
            )

    return StructuredResult(
        value=None,
        method_used=methods[-1],
        attempts=attempts,
        degradation_reason="; ".join(reasons) or "all structured methods exhausted",
    )
