"""Human-in-the-loop 决策测试。

验证通用 HITL 机制：工具结果带 conflict 时生成 choice_request 消息并置 hitl_pending，
无冲突时正常结束。以及图路由：chat_tools → hitl_decision → (chat | END)。
"""
from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage, SystemMessage, ToolMessage

from app.application.agent.nodes.hitl_decision import (
    _build_choice_message,
    _find_conflict,
    hitl_decision_node,
)


def _tool_msg(content: str) -> ToolMessage:
    return ToolMessage(content=content, tool_call_id=str(uuid.uuid4()))


def test_find_conflict_detects_conflict_in_tool_result():
    conflict_payload = json.dumps({
        "platform": "xiaohongshu",
        "topic": "历史播客",
        "items": [{"title": "a"}],
        "conflict": {"requested": 5, "total_found": 2, "filtered_out": 3},
    })
    messages = [_tool_msg(conflict_payload)]
    data = _find_conflict(messages)
    assert data is not None
    assert data["total_found"] == 2
    assert data["filtered_out"] == 3
    # topic 和 items 从顶层合并进来
    assert data["topic"] == "历史播客"
    assert len(data["items"]) == 1


def test_find_conflict_returns_none_without_conflict():
    normal_payload = json.dumps({"platform": "xiaohongshu", "items": [{"title": "a"}]})
    messages = [_tool_msg(normal_payload)]
    assert _find_conflict(messages) is None


def test_find_conflict_ignores_non_tool_messages():
    messages = [
        AIMessage(content="hello"),
        SystemMessage(content="system"),
    ]
    assert _find_conflict(messages) is None


def test_build_choice_message_has_three_options():
    conflict = {
        "requested": 5,
        "total_found": 2,
        "filtered_out": 3,
        "topic": "历史播客",
        "items": [{"title": "a"}, {"title": "b"}],
    }
    msg = _build_choice_message(conflict)
    payload = json.loads(msg.content)
    assert payload["type"] == "choice_request"
    assert len(payload["options"]) == 3
    assert payload["context"]["total_found"] == 2
    assert "2 条" in payload["question"]


@pytest.mark.asyncio
async def test_hitl_decision_node_sets_pending_on_conflict():
    conflict_payload = json.dumps({
        "platform": "xiaohongshu",
        "topic": "x",
        "items": [{"title": "a"}],
        "conflict": {"requested": 5, "total_found": 1, "filtered_out": 4, "topic": "x"},
    })
    state = {"messages": [_tool_msg(conflict_payload)]}
    out = await hitl_decision_node(state)
    assert out["hitl_pending"] is True
    assert out["hitl_choice"]["type"] == "choice_request"
    # 生成了一条 choice_request AIMessage
    assert len(out["messages"]) == 1


@pytest.mark.asyncio
async def test_hitl_decision_node_no_pending_without_conflict():
    normal_payload = json.dumps({"platform": "xiaohongshu", "items": []})
    state = {"messages": [_tool_msg(normal_payload)]}
    out = await hitl_decision_node(state)
    assert out["hitl_pending"] is False
    assert out["hitl_choice"] is None


@pytest.mark.asyncio
async def test_hitl_decision_node_empty_messages():
    out = await hitl_decision_node({"messages": []})
    assert out["hitl_pending"] is False
