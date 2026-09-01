from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.modules.conversation.agent.graph import (
    _route_after_intent,
    _route_after_knowledge_decision,
    _route_after_retrieval,
)
from app.modules.conversation.agent.nodes.memory_retriever import (
    answer_preference_memory_retriever_node,
    chat_memory_retriever_node,
)
from app.modules.writing.agent.nodes.memory_retriever import writer_memory_retriever_node


def test_chat_intents_route_before_any_memory_lookup(monkeypatch):
    monkeypatch.setattr(
        "app.modules.conversation.agent.graph.has_platform_search_route",
        lambda state: bool(state.get("intent_platform")),
    )
    assert _route_after_intent({"intent": "parse_url"}) == "parse_url"
    assert _route_after_intent({"intent": "collect"}) == "knowledge_decision"
    assert _route_after_intent({"intent": "task_plan"}) == "writer"
    assert _route_after_intent({"intent": "multi_agent"}) == "writer"
    assert _route_after_intent({"intent": "chat", "intent_platform": "zhihu"}) == "platform_collect"
    assert _route_after_intent({"intent": "chat"}) == "knowledge_decision"


def test_knowledge_routes_choose_memory_policy_after_retrieval():
    assert _route_after_knowledge_decision({"rag_decision": False}) == "chat_memory"
    assert _route_after_knowledge_decision({"rag_decision": True}) == "retrieve_knowledge"
    assert _route_after_retrieval(
        {"knowledge_mode": "strict", "retrieval_result": SimpleNamespace(has_evidence=True)}
    ) == "answer_preference_memory"
    assert _route_after_retrieval(
        {"knowledge_mode": "strict", "retrieval_result": SimpleNamespace(has_evidence=False)}
    ) == "strict_refusal"
    assert _route_after_retrieval(
        {"knowledge_mode": "normal", "retrieval_result": SimpleNamespace(has_evidence=False)}
    ) == "chat_memory"


@pytest.mark.asyncio
async def test_chat_and_knowledge_use_different_memory_scopes(monkeypatch):
    retrieve = AsyncMock(return_value=[])
    monkeypatch.setattr("app.modules.memory.application.manage_memory.retrieve_memories", retrieve)
    state = {"user_message": "如何写得更清楚", "workspace_id": "default"}

    await chat_memory_retriever_node(state)
    chat_scopes = retrieve.await_args.kwargs["scopes"]
    assert "general" in chat_scopes
    assert retrieve.await_args.kwargs["top_k"] == 3

    await answer_preference_memory_retriever_node(state)
    answer_scopes = retrieve.await_args.kwargs["scopes"]
    assert answer_scopes == {"answer_format", "writing_style", "audience"}
    assert "general" not in answer_scopes
    assert retrieve.await_args.kwargs["top_k"] == 2


@pytest.mark.asyncio
async def test_writer_owns_writing_memory_retrieval(monkeypatch):
    retrieve = AsyncMock(return_value=[])
    monkeypatch.setattr("app.modules.memory.application.manage_memory.retrieve_memories", retrieve)

    await writer_memory_retriever_node(
        {
            "operation": "compose",
            "goal": "写一篇产品分析",
            "workspace_id": "default",
        }
    )

    assert retrieve.await_args.kwargs["query"] == "写一篇产品分析"
    assert "writing_style" in retrieve.await_args.kwargs["scopes"]
    assert "workflow" in retrieve.await_args.kwargs["scopes"]
