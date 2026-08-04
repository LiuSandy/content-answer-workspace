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
        "tool_result": None,
        "error": None,
        "response_payload": None,
        "collection_request": None,
        # Human-in-the-loop：每轮重置，避免上一轮的选择请求状态残留
        "hitl_pending": False,
        "hitl_choice": None,
        "hitl_selection": None,
    }
