"""意图路由节点：三层意图识别（规则 → LLM → 校验兜底）。

设计理念：
  - L0 规则层：确定性关键词/正则，命中即返回（可复现、零 LLM 成本、优先）
  - L1 LLM 层：规则未命中/模糊时调用，一次判定 intent/knowledge_mode/platform/query，
    并输出 confidence；使用公共 generate_structured(IntentRoute)，无手写 JSON 解析
  - L2 校验层：Pydantic 校验 + 低置信度降级 + 规则与 LLM 冲突时规则优先

用户只需自然对话，Agent 自动决定普通回答、查私有资料、单篇创作、
多阶段协作、平台采集。意图识别不依赖前端任何模式选择。
"""
from __future__ import annotations

import logging

from app.contracts.dto import IntentRoute
from ....infrastructure.llm.registry import llm_provider_registry
from app.services.llm.structured_output import generate_structured
from ....prompts.registry import prompt_registry
from .intent_rules import detect_intent_by_rules, extract_urls
from app.state import ChatAgentState

logger = logging.getLogger(__name__)

_VALID_INTENTS = {"chat", "parse_url", "task_plan", "multi_agent"}
_VALID_MODES = {"off", "normal", "strict"}
# 置信度低于该值视为不可靠，降级为 chat（宁可走保守路线）
_MIN_CONFIDENCE = 0.6


def _preprocess_intent_input(state: ChatAgentState) -> dict:
    """在意图识别入口统一清理本轮状态并提取确定性信号。"""
    message = state.get("user_message", "").strip()
    return {
        "extracted_urls": extract_urls(message),
        "intent": None,
        "intent_confidence": None,
        "intent_reason": None,
        "intent_platform": None,
        "intent_query": None,
        "intent_limit": None,
        "intent_sort": None,
        "platform_collect_result": None,
        "rag_decision": None,
        "decision_reason": None,
        "retrieval_result": None,
        "trace_id": None,
        "fallback_reason": None,
        "tool_result": None,
        "error": None,
        "response_payload": None,
        "collection_request": None,
        "applied_memories": [],
        "hitl_pending": False,
        "hitl_choice": None,
        "hitl_selection": state.get("hitl_selection"),
    }


def _default_result(message: str, existing_mode: str | None) -> dict:
    """保守兜底：默认普通对话。"""
    mode = existing_mode if existing_mode in _VALID_MODES else "normal"
    return {
        "intent": "chat",
        "knowledge_mode": mode,
        "intent_confidence": 0.0,
        "intent_reason": "fallback: default chat",
        "intent_platform": None,
        "intent_query": None,
        "intent_limit": None,
        "intent_sort": None,
    }


async def _detect_intent(state: ChatAgentState) -> dict:
    message = state.get("user_message", "")
    existing_mode = state.get("knowledge_mode")
    if existing_mode not in _VALID_MODES:
        existing_mode = "normal"

    # ── L0 规则层 ──────────────────────────────────────────────────────────
    rule_result = detect_intent_by_rules(message)
    if rule_result is not None and rule_result.get("confidence", 1.0) >= 1.0:
        rule_result.pop("_limit_explicit", None)
        rule_result.pop("_sort_explicit", None)
        rule_result.setdefault("intent_confidence", 1.0)
        rule_result.setdefault("intent_reason", "rule")
        rule_result.setdefault("intent_platform", rule_result.get("platform"))
        rule_result.setdefault("intent_query", rule_result.get("query"))
        rule_result.setdefault("intent_limit", rule_result.get("limit", 10))
        rule_result.setdefault("intent_sort", rule_result.get("sort", "relevance"))
        # 显式 strict/off 优先保留（测试/内部直连兼容）
        if existing_mode in ("strict", "off"):
            rule_result["knowledge_mode"] = existing_mode
        return rule_result

    # ── L1 LLM 层（规则未命中） ────────────────────────────────────────────
    try:
        urls = state.get("extracted_urls") or []
        rendered = prompt_registry.render(
            "chat.intent_router",
            user_message=message,
            extracted_urls=str(urls),
        )
        provider = llm_provider_registry.get_default()
        structured = await generate_structured(
            provider=provider,
            request=rendered.to_llm_request(),
            schema=IntentRoute,
            structured_methods=getattr(rendered, "structured_methods", None),
        )
        route = structured.value
        if route is None:
            # 公共接口已降级到极限仍不可解析：保守走 chat，不抛异常
            logger.info(
                "Intent LLM output unparseable (%s), defaulting to chat",
                structured.degradation_reason,
            )
            result = _default_result(message, existing_mode)
            result["intent_reason"] = f"llm unparseable: {structured.method_used}"
            return result

        # ── L2 校验层 ────────────────────────────────────────────────────────
        intent = route.intent if route.intent in _VALID_INTENTS else "chat"
        knowledge_mode = (
            route.knowledge_mode if route.knowledge_mode in _VALID_MODES else "normal"
        )
        try:
            confidence = float(route.confidence)
        except (TypeError, ValueError):
            confidence = 0.9
        confidence = max(0.0, min(1.0, confidence))

        # 显式 strict/off 优先保留
        if existing_mode in ("strict", "off"):
            knowledge_mode = existing_mode

        # 低置信度降级：宁可 chat 也不要冒险进错模式
        if confidence < _MIN_CONFIDENCE:
            logger.info("Intent low confidence (%.2f) for %r, defaulting to chat", confidence, message[:50])
            result = _default_result(message, existing_mode)
            result["intent_reason"] = f"llm low confidence {confidence:.2f}"
            return result

        # 规则层已有低置信结果（如 generic collection）：用 LLM 精修其 platform/query
        if rule_result is not None:
            limit_explicit = bool(rule_result.pop("_limit_explicit", False))
            sort_explicit = bool(rule_result.pop("_sort_explicit", False))
            rule_result.update({
                "intent_confidence": confidence,
                "intent_reason": route.reason or "rule+llm",
                "intent_platform": route.platform or rule_result.get("platform"),
                "intent_query": route.query or rule_result.get("query"),
                "intent_limit": rule_result.get("limit", 10) if limit_explicit else route.limit,
                "intent_sort": rule_result.get("sort", "relevance") if sort_explicit else route.sort,
            })
            return rule_result

        return {
            "intent": intent,
            "knowledge_mode": knowledge_mode,
            "intent_confidence": confidence,
            "intent_reason": route.reason or "llm",
            "intent_platform": route.platform,
            "intent_query": route.query,
            "intent_limit": route.limit,
            "intent_sort": route.sort,
        }
    except Exception as e:
        logger.warning("Intent routing failed, defaulting to chat: %s", e)
        return _default_result(message, existing_mode)


async def route_intent_node(state: ChatAgentState) -> dict:
    """完成输入预处理并识别意图，作为 Chat Graph 的单一意图入口。"""
    preprocessed = _preprocess_intent_input(state)
    routed = await _detect_intent({**state, **preprocessed})
    return {**preprocessed, **routed}


__all__ = ["route_intent_node"]
