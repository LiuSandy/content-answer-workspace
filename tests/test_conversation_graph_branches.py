"""对话图意图分支测试：意图识别为 task_plan / multi_agent 时自动路由到对应执行节点。"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from langgraph.checkpoint.memory import MemorySaver

from app.agents.chat.graph import build_chat_agent_graph


def test_route_after_intent_selects_platform_collect_for_explicit_zhihu_search(monkeypatch):
    from app.agents.chat import graph as conversation

    monkeypatch.setattr(conversation, "has_platform_search_route", lambda state: True)

    assert conversation._route_after_intent({
        "intent": "chat",
        "intent_platform": "zhihu",
        "intent_query": "热门",
    }) == "platform_collect"


@pytest.fixture
def graph(monkeypatch):
    """编译图；mock route_intent 的 LLM 依赖与 memory retriever，避免真实调用。"""
    fake_rendered = MagicMock()
    fake_rendered.to_llm_request.return_value = MagicMock()
    fake_provider = MagicMock()
    fake_provider.generate = AsyncMock(
        return_value=MagicMock(content='{"intent": "chat", "knowledge_mode": "normal"}')
    )
    fake_registry = MagicMock()
    fake_registry.get.return_value = fake_provider
    monkeypatch.setattr(
        "app.agents.chat.nodes.route_intent.llm_provider_registry", fake_registry
    )
    monkeypatch.setattr(
        "app.agents.chat.nodes.route_intent.prompt_registry",
        MagicMock(render=MagicMock(return_value=fake_rendered)),
    )
    monkeypatch.setattr(
        "app.services.memory.service.retrieve_memories", AsyncMock(return_value=[])
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
    }


@pytest.mark.asyncio
async def test_graph_routes_task_plan_intent(graph, monkeypatch):
    """route_intent 判定 task_plan 时，自动路由到 task_plan 节点执行。"""
    from app.agents.orchestrator.nodes.task_plan import task_plan_node
    from app.services.planning_service import TaskPlan, SubTask

    # mock route_intent LLM 返回 task_plan
    from app.agents.chat.nodes import route_intent as ri_mod
    fake_rendered = MagicMock()
    fake_rendered.to_llm_request.return_value = MagicMock()
    fake_provider = MagicMock()
    fake_provider.generate = AsyncMock(
        return_value=MagicMock(content='{"intent": "task_plan", "knowledge_mode": "normal"}')
    )
    fake_registry = MagicMock()
    fake_registry.get.return_value = fake_provider
    monkeypatch.setattr(ri_mod, "llm_provider_registry", fake_registry)

    async def fake_gen(goal):
        return TaskPlan(plan_id="p1", goal=goal, tasks=[SubTask("s1", "write", "w", [])])

    async def fake_exec(plan):
        return {"s1": "最终成稿"}

    monkeypatch.setattr(
        "app.agents.orchestrator.nodes.task_plan.generate_plan", fake_gen
    )
    monkeypatch.setattr(
        "app.agents.orchestrator.nodes.task_plan.execute_task_plan", fake_exec
    )

    final = await graph.ainvoke(
        _base_state("写一篇关于 RAG 的回答"),
        {"configurable": {"thread_id": "tplan"}},
    )
    assert final.get("intent") == "task_plan"
    assert final.get("task_plan_result", {}).get("status") == "done"
    assert "已完成复合创作任务" in final["messages"][-1].content


@pytest.mark.asyncio
async def test_graph_routes_multi_agent_intent(graph, monkeypatch):
    """route_intent 判定 multi_agent 时，自动路由到 multi_agent 节点执行。"""
    from app.agents.chat.nodes import route_intent as ri_mod
    fake_rendered = MagicMock()
    fake_rendered.to_llm_request.return_value = MagicMock()
    fake_provider = MagicMock()
    fake_provider.generate = AsyncMock(
        return_value=MagicMock(content='{"intent": "multi_agent", "knowledge_mode": "normal"}')
    )
    fake_registry = MagicMock()
    fake_registry.get.return_value = fake_provider
    monkeypatch.setattr(ri_mod, "llm_provider_registry", fake_registry)

    class FakeMultiResult:
        final_output = "多Agent最终成稿"
        draft = None
        sub_agent_states = {
            name: SimpleNamespace(status="done", error=None, result="ok")
            for name in ("orchestrator", "research", "writing", "review", "memory")
        }

    monkeypatch.setattr(
        "app.agents.orchestrator.graph_exec.run_multi_agent_plan",
        AsyncMock(return_value=FakeMultiResult()),
    )

    final = await graph.ainvoke(
        _base_state("调研并输出一份 AI Agent 行业分析报告"),
        {"configurable": {"thread_id": "magent"}},
    )
    assert final.get("intent") == "multi_agent"
    ma = final.get("multi_agent_result") or {}
    assert ma.get("status") == "done"
    assert ma.get("finalContent") == "多Agent最终成稿"
    assert len(ma.get("agents", [])) == 5
    assert "多 Agent 协作已完成" in final["messages"][-1].content
