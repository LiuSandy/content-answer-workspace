"""预处理节点：确定性检测 URL、清理输入、建立请求上下文。"""
from __future__ import annotations

from ..state import ChatAgentState
from .intent_rules import extract_urls


async def preprocess_node(state: ChatAgentState) -> dict:
    text = state.get("user_message", "").strip()
    urls = extract_urls(text)
    return {
        "extracted_urls": urls,
        "intent": None,
        "intent_confidence": None,
        "intent_reason": None,
        "intent_platform": None,
        "intent_query": None,
        "intent_limit": None,
        "intent_sort": None,
        "platform_collect_result": None,
        "tool_result": None,
        "error": None,
        "response_payload": None,
        "collection_request": None,
        # Human-in-the-loop：每轮重置本轮的选择请求状态，避免上一轮残留；
        # 但保留 hitl_selection（续跑轮由 POST /choices 带入，透传给后续工具调用）
        "hitl_pending": False,
        "hitl_choice": None,
        "hitl_selection": state.get("hitl_selection"),
    }
