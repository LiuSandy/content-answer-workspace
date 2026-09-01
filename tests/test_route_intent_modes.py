"""意图路由自动判定执行模式与知识模式测试。

验证：不再需要用户在前端选择模式，route_intent_node 通过 LLM 一次判定
intent（chat/parse_url/collect/task_plan/multi_agent）与 knowledge_mode（off/normal/strict）。
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.modules.conversation.agent.nodes.route_intent import route_intent_node
from tests.llm_fakes import structured_gateway


def _make_mock_deps(monkeypatch, llm_content: str):
    """mock prompt_registry 与 llm_provider_registry，让 LLM 返回指定 JSON。"""
    fake_rendered = MagicMock()
    fake_rendered.structured_methods = ["json_mode", "function_calling"]
    fake_rendered.to_llm_request.return_value = MagicMock()
    fake_prompt_registry = MagicMock()
    fake_prompt_registry.render.return_value = fake_rendered
    monkeypatch.setattr(
        "app.modules.conversation.agent.nodes.route_intent._get_intent_gateway",
        lambda: structured_gateway(llm_content),
    )
    monkeypatch.setattr(
        "app.modules.conversation.agent.nodes.route_intent.prompt_registry", fake_prompt_registry
    )


def _state(message: str) -> dict:
    return {
        "user_message": message,
        "extracted_urls": [],
    }


@pytest.mark.asyncio
async def test_route_identifies_task_plan(monkeypatch):
    _make_mock_deps(monkeypatch, '{"intent": "task_plan", "knowledge_mode": "normal"}')
    out = await route_intent_node(_state("写一篇关于 RAG 的回答"))
    assert out["intent"] == "task_plan"
    assert out["knowledge_mode"] == "normal"


@pytest.mark.asyncio
async def test_route_identifies_multi_agent(monkeypatch):
    _make_mock_deps(monkeypatch, '{"intent": "multi_agent", "knowledge_mode": "normal"}')
    out = await route_intent_node(_state("调研并输出一份 AI Agent 行业现状分析报告"))
    assert out["intent"] == "multi_agent"


@pytest.mark.asyncio
async def test_route_identifies_platform_collection():
    out = await route_intent_node(_state("帮我搜搜知乎上关于副业的热门讨论"))
    assert out["intent"] == "collect"
    assert out["intent_platform"] == "zhihu"
    assert out["intent_query"] == "副业"


@pytest.mark.asyncio
async def test_route_identifies_strict_knowledge(monkeypatch):
    _make_mock_deps(monkeypatch, '{"intent": "chat", "knowledge_mode": "strict"}')
    out = await route_intent_node(_state("只能根据我上传的文件回答，为什么 chmod 能防未授权"))
    assert out["intent"] == "chat"
    assert out["knowledge_mode"] == "strict"


@pytest.mark.asyncio
async def test_route_identifies_chat_with_off_knowledge(monkeypatch):
    _make_mock_deps(monkeypatch, '{"intent": "chat", "knowledge_mode": "off"}')
    out = await route_intent_node(_state("你好"))
    assert out["intent"] == "chat"
    assert out["knowledge_mode"] == "off"


@pytest.mark.asyncio
async def test_route_defaults_chat_on_bad_llm_output(monkeypatch):
    _make_mock_deps(monkeypatch, "不是JSON")
    out = await route_intent_node(_state("随便聊聊"))
    assert out["intent"] == "chat"
    assert out["knowledge_mode"] == "normal"


@pytest.mark.asyncio
async def test_route_ignores_previous_turn_knowledge_mode(monkeypatch):
    """上一轮的知识模式不能覆盖本轮意图识别结果。"""
    _make_mock_deps(monkeypatch, '{"intent": "chat", "knowledge_mode": "normal"}')
    state = _state("解释下 RAG")
    state["knowledge_mode"] = "strict"
    out = await route_intent_node(state)
    assert out["knowledge_mode"] == "normal"


@pytest.mark.asyncio
async def test_route_parse_url_rule_ignores_previous_mode(monkeypatch):
    """URL 规则分支也必须重新判定本轮知识模式。"""
    state = _state("解析这个网页 https://zhuanlan.zhihu.com/p/123")
    state["knowledge_mode"] = "strict"
    state["extracted_urls"] = ["https://zhuanlan.zhihu.com/p/123"]
    out = await route_intent_node(state)
    assert out["intent"] == "parse_url"
    assert out["knowledge_mode"] == "normal"


@pytest.mark.asyncio
async def test_route_clears_previous_turn_rag_state(monkeypatch):
    _make_mock_deps(monkeypatch, '{"intent": "chat", "knowledge_mode": "normal"}')
    state = _state("什么是同余定理")
    state.update(
        {
            "rag_decision": False,
            "decision_reason": "previous turn",
            "retrieval_result": object(),
            "trace_id": "old-trace",
            "fallback_reason": "old-fallback",
        }
    )

    out = await route_intent_node(state)

    assert out["rag_decision"] is None
    assert out["decision_reason"] is None
    assert out["retrieval_result"] is None
    assert out["trace_id"] is None
    assert out["fallback_reason"] is None
