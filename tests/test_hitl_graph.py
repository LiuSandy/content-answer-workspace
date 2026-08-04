"""Human-in-the-loop 图路由测试：工具结果带冲突时终止并请求用户，否则回到 chat。"""
from __future__ import annotations

import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage, ToolMessage

from langgraph.checkpoint.memory import MemorySaver

from app.application.agent.graphs.conversation import build_chat_agent_graph


def _tool_msg(content: str) -> ToolMessage:
    return ToolMessage(content=content, tool_call_id=str(uuid.uuid4()))


@pytest.fixture
def graph(monkeypatch):
    fake_rendered = MagicMock()
    fake_rendered.to_llm_request.return_value = MagicMock()
    fake_provider = MagicMock()
    fake_provider.generate = AsyncMock(
        return_value=MagicMock(content='{"intent": "chat", "knowledge_mode": "normal"}')
    )
    fake_registry = MagicMock()
    fake_registry.get.return_value = fake_provider
    monkeypatch.setattr(
        "app.application.agent.nodes.route_intent.llm_provider_registry", fake_registry
    )
    monkeypatch.setattr(
        "app.application.agent.nodes.route_intent.prompt_registry",
        MagicMock(render=MagicMock(return_value=fake_rendered)),
    )
    monkeypatch.setattr(
        "app.application.memory_service.retrieve_memories", AsyncMock(return_value=[])
    )
    return build_chat_agent_graph(MemorySaver())


def _base_state(message: str) -> dict:
    return {
        "chat_id": "00000000-0000-0000-0000-000000000001",
        "user_message_id": "msg-1",
        "user_message": message,
        "messages": [],
        "intent": None,
        "extracted_urls": [],
        "collection_request": None,
        "tool_result": None,
        "response_payload": None,
        "error": None,
        "workspace_id": "default",
        "owner_id": "default",
        "knowledge_mode": "normal",
        "rag_decision": None,
        "decision_reason": None,
        "retrieval_result": None,
        "trace_id": None,
        "fallback_reason": None,
        "applied_memories": None,
        "task_plan_result": None,
        "multi_agent_result": None,
        "hitl_pending": False,
        "hitl_choice": None,
        "hitl_selection": None,
    }


@pytest.mark.asyncio
async def test_graph_hitl_pending_ends_on_conflict(graph, monkeypatch):
    """chat LLM 调用工具返回带 conflict 的结果后，图终止并置 hitl_pending。"""
    # mock chat LLM：第一轮调工具，第二轮不调工具
    calls = {"n": 0}

    class FakeLLM:
        def bind_tools(self, _tools):
            return self

        async def ainvoke(self, messages):
            calls["n"] += 1
            if calls["n"] == 1:
                # 第一次调用：请求调用 xiaohongshu_search
                return AIMessage(
                    content="",
                    tool_calls=[{
                        "name": "xiaohongshu_search",
                        "args": {"query": "历史播客", "limit": 5},
                        "id": "call-1",
                        "type": "tool_call",
                    }],
                )
            # 第二次调用：直接回复
            return AIMessage(content="done")

    from app.application.agent.nodes import chat_node as chat_mod
    monkeypatch.setattr(chat_mod, "_get_chat_llm", lambda: FakeLLM())
    monkeypatch.setattr(chat_mod, "_llm", FakeLLM(), raising=False)

    # mock 工具底层 _run 返回 YAML list（仅 1 条，触发 requested=5 但 total=1 的冲突）
    yaml_payload = "- rank: 1\n  author: 张三\n  likes: '150'\n  title: 唯一结果\n  url: https://xhs.com/n/1\n  published_at: '2026-07-25'\n"
    monkeypatch.setattr(
        "app.application.agent.tools.xiaohongshu_tool._run",
        lambda _args: yaml_payload,
    )

    base = _base_state("搜小红书历史播客帖子，点赞大于100，只要5条")
    final = await graph.ainvoke(base, {"configurable": {"thread_id": "hitl1"}})
    assert final.get("hitl_pending") is True
    assert final.get("hitl_choice") is not None
    # 生成了 choice_request 消息
    last_msg = final["messages"][-1]
    assert last_msg.type == "ai"
    assert json.loads(last_msg.content)["type"] == "choice_request"


@pytest.mark.asyncio
async def test_graph_normal_chat_no_hitl(graph, monkeypatch):
    """正常对话（无工具冲突）不触发 HITL。"""
    calls = {"n": 0}

    class FakeLLM:
        def bind_tools(self, _tools):
            return self

        async def ainvoke(self, messages):
            calls["n"] += 1
            return AIMessage(content="普通回答")

    from app.application.agent.nodes import chat_node as chat_mod
    monkeypatch.setattr(chat_mod, "_get_chat_llm", lambda: FakeLLM())
    monkeypatch.setattr(chat_mod, "_llm", FakeLLM(), raising=False)

    base = _base_state("你好")
    final = await graph.ainvoke(base, {"configurable": {"thread_id": "hitl2"}})
    assert final.get("hitl_pending") in (None, False)
    assert final.get("hitl_choice") is None
