"""Agent 循环上限测试：recursion_limit 常量集中配置并生效。"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage

from app.core.config import AGENT_MAX_RECURSION


def test_recursion_limit_constant_is_20():
    assert AGENT_MAX_RECURSION == 20


def test_chat_route_config_includes_recursion_limit():
    """chats.py 的 LangGraph config 携带集中配置的 recursion_limit。"""
    import inspect
    import app.api.routes.chats as chats_mod

    source = inspect.getsource(chats_mod)
    assert "recursion_limit" in source
    assert "AGENT_MAX_RECURSION" in source


def test_run_service_config_includes_recursion_limit():
    import inspect
    import app.application.chat_conversation_run_service as svc

    source = inspect.getsource(svc)
    assert "recursion_limit" in source
    assert "AGENT_MAX_RECURSION" in source


@pytest.mark.asyncio
async def test_graph_recursion_error_caught_on_runaway_loop(monkeypatch):
    """ReAct 环死循环（LLM 永远返回 tool_calls）时，图在 recursion_limit 处被截断。"""
    from langgraph.checkpoint.memory import MemorySaver
    from app.application.agent.graphs.conversation import build_chat_agent_graph

    # LLM 永远要调工具，制造死循环
    class RunawayLLM:
        def bind_tools(self, _tools):
            return self

        async def ainvoke(self, messages):
            return AIMessage(
                content="",
                tool_calls=[{
                    "name": "get_current_datetime",
                    "args": {},
                    "id": "loop-call",
                    "type": "tool_call",
                }],
            )

    from app.application.agent.nodes import route_intent as ri
    from app.application.agent.nodes import chat_node as chat_mod
    import app.application.memory_service as msvc

    fr = MagicMock(); fr.to_llm_request.return_value = MagicMock()
    fp = MagicMock()
    fp.generate = AsyncMock(return_value=MagicMock(content='{"intent":"chat","knowledge_mode":"normal"}'))
    frg = MagicMock(); frg.get.return_value = fp
    ri.llm_provider_registry = frg
    ri.prompt_registry = MagicMock(render=MagicMock(return_value=fr))
    msvc.retrieve_memories = AsyncMock(return_value=[])
    chat_mod._get_chat_llm = lambda: RunawayLLM()
    chat_mod._llm = RunawayLLM()

    graph = build_chat_agent_graph(MemorySaver())
    base = {
        "chat_id": "0" * 36, "user_message_id": "m", "user_message": "循环测试",
        "messages": [], "intent": None, "extracted_urls": [],
        "collection_request": None, "tool_result": None, "response_payload": None, "error": None,
        "workspace_id": "default", "owner_id": "default", "knowledge_mode": "normal",
        "rag_decision": None, "decision_reason": None, "retrieval_result": None,
        "trace_id": None, "fallback_reason": None, "applied_memories": None,
        "task_plan_result": None, "multi_agent_result": None,
        "hitl_pending": False, "hitl_choice": None, "hitl_selection": None,
    }
    config = {
        "configurable": {"thread_id": "loop-test"},
        "recursion_limit": AGENT_MAX_RECURSION,
    }

    from langgraph.errors import GraphRecursionError

    with pytest.raises(GraphRecursionError):
        await graph.ainvoke(base, config)
