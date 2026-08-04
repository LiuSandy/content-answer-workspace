"""预处理节点：确定性检测 URL、清理输入、建立请求上下文。"""
from __future__ import annotations

import re
from ..state import ChatAgentState

URL_PATTERN = re.compile(r'https?://[^\s<>"]+', re.IGNORECASE)


async def preprocess_node(state: ChatAgentState) -> dict:
    text = state.get("user_message", "").strip()
    urls = URL_PATTERN.findall(text)
    return {
        "extracted_urls": urls,
        "intent": None,
        "tool_result": None,
        "error": None,
        "response_payload": None,
        "collection_request": None,
        # Human-in-the-loop：每轮重置，避免上一轮的选择请求状态残留
        "hitl_pending": False,
        "hitl_choice": None,
        "hitl_selection": None,
    }
