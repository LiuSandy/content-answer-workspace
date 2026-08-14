"""结构化输出公共底座；json_schema → json_mode → 通用解析三级降级。

设计约定（roadmap R1 接口决定）：
  - 底层不直接写 DB；StructuredResult 的降级元数据由业务调用方审计，
    写入各自 AIOperation.model_parameters。
  - provider profile 明确声明 structured_methods；不支持原生 json_schema 的
    兼容端点直接从 json_mode 开始，不做异常探测。
"""
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

# 三级降级的优先级顺序（从高到低）
_METHOD_PRIORITY = ("json_schema", "json_mode", "generic_parse")
# 未声明 structured_methods 时使用的保守默认（不假定原生 json_schema）
_DEFAULT_METHODS = ["json_mode", "generic_parse"]


def _response_format(method: str, schema: type[T]) -> dict[str, Any] | None:
    """按方法构造 OpenAI 兼容 response_format。"""
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
    """返回携带指定 response_format 的请求副本；避免污染调用方对象。"""
    fmt = _response_format(method, schema)
    if isinstance(request, LLMRequest):
        extra = dict(request.extra or {})
        extra.pop("response_format", None)
        return request.model_copy(update={"response_format": fmt, "extra": extra})
    # 测试/兼容路径：非 Pydantic 请求对象直接设置属性
    request.response_format = fmt  # type: ignore[attr-defined]
    return request


def _extract_json(content: str) -> Any:
    """从 LLM 文本中提取 JSON 值；支持 markdown 代码块与前后杂质文本。"""
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
    """解析并校验 LLM 输出；失败抛 ValueError 供上层降级。"""
    payload = _extract_json(content)
    if payload is None:
        raise ValueError("LLM 输出中未找到可解析的 JSON")
    if not isinstance(payload, (dict, list)):
        raise ValueError("LLM 输出 JSON 不是对象或数组")
    try:
        return schema.model_validate(payload)
    except ValidationError as e:
        raise ValueError(f"schema 校验失败: {e}") from e


def _ordered_methods(structured_methods: Any) -> list[str]:
    """按优先级过滤 profile 声明的方法；非法输入回退保守默认。"""
    if not isinstance(structured_methods, (list, tuple, set)) or not structured_methods:
        return list(_DEFAULT_METHODS)
    return (
        [m for m in _METHOD_PRIORITY if m in set(structured_methods)]
        or list(_DEFAULT_METHODS)
    )


async def generate_structured(
    provider: LLMProvider,
    request: LLMRequest,
    schema: type[T],
    structured_methods: list[str] | None = None,
    retries: int = 1,
) -> StructuredResult[T]:
    """按 profile 能力生成结构化输出；三级降级 + 每个方法内重试。

    - 选择 profile 声明的最高优先级方法（json_schema > json_mode > generic_parse）。
    - 每个方法内最多 (retries+1) 次尝试；解析/校验失败后降级到下一方法。
    - 全部失败返回 value=None 的 StructuredResult，不抛异常；degradation_reason
      记录每一级的失败原因，供调用方审计到 AIOperation.model_parameters。
    """
    methods = _ordered_methods(structured_methods)
    reasons: list[str] = []
    attempts = 0

    for method in methods:
        for _ in range(retries + 1):
            attempts += 1
            req = _with_response_format(request, method, schema)
            try:
                resp = await provider.generate(req)
                content = (getattr(resp, "content", "") or "").strip()
                value = _validate_content(content, schema)
            except Exception as e:  # noqa: BLE001 单次调用/校验失败均降级
                logger.warning(
                    "Structured generation %s attempt %d failed: %s",
                    method,
                    attempts,
                    e,
                )
                reasons.append(f"{method}: {e}")
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
