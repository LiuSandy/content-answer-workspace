from __future__ import annotations

import json

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.modules.conversation.api.router import _current_turn_platform_tool_result


def _tool_message(topic: str, title: str, call_id: str) -> ToolMessage:
    return ToolMessage(
        content=json.dumps(
            {
                "platform": "zhihu",
                "topic": topic,
                "items": [{"title": title}],
            },
            ensure_ascii=False,
        ),
        name="zhihu_search",
        tool_call_id=call_id,
    )


def test_historical_platform_tool_result_is_not_attached_to_current_turn():
    messages = [
        HumanMessage(content="搜索 SSE"),
        _tool_message("SSE", "WebSocket 和 SSE 有什么区别？", "old-call"),
        AIMessage(content="历史回答"),
        HumanMessage(content="什么是同余定理？"),
        AIMessage(content="当前回答"),
    ]

    items, platform, tool_name = _current_turn_platform_tool_result(messages)

    assert items == []
    assert platform is None
    assert tool_name is None


def test_current_turn_platform_tool_result_can_be_attached():
    messages = [
        HumanMessage(content="历史问题"),
        _tool_message("历史主题", "历史结果", "old-call"),
        AIMessage(content="历史回答"),
        HumanMessage(content="搜索同余定理"),
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "zhihu_search",
                    "args": {},
                    "id": "current-call",
                    "type": "tool_call",
                }
            ],
        ),
        _tool_message("同余定理", "当前结果", "current-call"),
        AIMessage(content="当前回答"),
    ]

    items, platform, tool_name = _current_turn_platform_tool_result(messages)

    assert items == [{"title": "当前结果"}]
    assert platform == "zhihu"
    assert tool_name == "zhihu_search"
