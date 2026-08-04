"""Phase 1.5 · Task 1：RAG 检索接入对话主链路端到端验证。

跑编译后的 conversation graph，mock 所有外部依赖（LLM、检索服务、Trace 服务），
断言四条路径的图路由、节点执行与 state 更新都符合 spec 11.2 与 1.5 前置条件：

  路径 #1 normal + 证据充分 → retrieve_knowledge 执行、Trace 落库、chat_node 收到
           grounded context 并带 [Sx] 引用指令，state.trace_id 非 None
  路径 #2 normal + 证据不足 → state.fallback_reason 非 None，chat_node system 含
           「私有资料库中没有找到足够的相关证据」降级提示
  路径 #3 strict + 证据不足 → 路由到 strict_refusal，chat LLM 不被调用，返回固定拒答
  路径 #4 off → knowledge_decision 返回 False，retrieve_knowledge 节点不执行
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from langgraph.checkpoint.memory import MemorySaver

from app.application.agent.graphs.conversation import build_chat_agent_graph
from app.application.agent.state import ChatAgentState
from app.application.knowledge.retrieval_service import RetrievalResult


# ── 公共夹具：构造一个编译后的图，所有外部依赖被 mock ────────────────────────

@pytest.fixture
def compiled_graph(monkeypatch):
    """编译图并 mock route_intent / retrieve_knowledge / chat_node 的外部依赖。

    route_intent 默认 mock 为返回 intent=chat，避免触发真实 LLM。
    各测试可按需覆盖 mock 行为。
    """
    # 1) route_intent：mock prompt_registry + llm_provider_registry，强制返回 chat
    fake_rendered = MagicMock()
    fake_rendered.to_llm_request.return_value = MagicMock()
    fake_provider = MagicMock()
    fake_provider.generate = AsyncMock(return_value=MagicMock(content='{"intent": "chat"}'))
    fake_registry = MagicMock()
    fake_registry.get.return_value = fake_provider
    fake_prompt_registry = MagicMock()
    fake_prompt_registry.render.return_value = fake_rendered
    monkeypatch.setattr(
        "app.application.agent.nodes.route_intent.llm_provider_registry", fake_registry
    )
    monkeypatch.setattr(
        "app.application.agent.nodes.route_intent.prompt_registry", fake_prompt_registry
    )

    # 2) retrieve_knowledge：mock get_session_factory、KnowledgeRetrievalService、TraceService
    #    这些是在节点函数内 import 的，因此 patch 源模块属性即可生效
    fake_session = AsyncMock()
    fake_factory = MagicMock()
    fake_factory.return_value.__aenter__ = AsyncMock(return_value=fake_session)
    fake_factory.return_value.__aexit__ = AsyncMock(return_value=None)
    monkeypatch.setattr("app.persistence.session.get_session_factory", lambda: fake_factory)

    # 3) chat_node：mock _get_chat_llm 返回可捕获 messages 的 LLM
    captured_messages = []

    class FakeLLM:
        def bind_tools(self, _tools):
            return self

        async def ainvoke(self, messages):
            captured_messages.append(list(messages))
            from langchain_core.messages import AIMessage
            return AIMessage(content="mocked grounded answer")

    fake_llm = FakeLLM()
    monkeypatch.setattr(
        "app.application.agent.nodes.chat_node._get_chat_llm", lambda: fake_llm
    )
    monkeypatch.setattr("app.application.agent.nodes.chat_node._llm", fake_llm, raising=False)

    graph = build_chat_agent_graph(MemorySaver())
    return graph, captured_messages


def _base_state(message: str, mode: str) -> ChatAgentState:
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
        "knowledge_mode": mode,
        "rag_decision": None,
        "decision_reason": None,
        "retrieval_result": None,
        "trace_id": None,
        "fallback_reason": None,
    }


def _install_retriever(monkeypatch, result: RetrievalResult | None):
    """注入 mock 的 KnowledgeRetrievalService.retrieve 返回指定 result。"""
    fake_svc = MagicMock()
    fake_svc.retrieve = AsyncMock(return_value=result)
    monkeypatch.setattr(
        "app.application.knowledge.retrieval_service.KnowledgeRetrievalService",
        lambda session: fake_svc,
    )


def _install_trace(monkeypatch):
    """注入 mock 的 TraceService 记录调用。"""
    calls = {"create": 0, "record_hits": 0, "finalize": 0, "trace_id": None}

    class FakeTrace:
        async def create_trace(self, **kwargs):
            calls["create"] += 1
            from app.persistence.models.knowledge import RetrievalTraceModel
            import uuid
            t = RetrievalTraceModel(
                id=uuid.uuid4(), workspace_id=kwargs.get("workspace_id", "default"),
                owner_id=kwargs.get("owner_id", "default"),
                original_query=kwargs.get("original_query", ""),
                rag_decision=True, decision_reason="", mode=kwargs.get("mode", "normal"),
            )
            calls["trace_id"] = str(t.id)
            return t

        async def record_hits(self, trace_id, hits):
            calls["record_hits"] += 1

        async def finalize_trace(self, trace_id, **kwargs):
            calls["finalize"] += 1

    monkeypatch.setattr(
        "app.application.knowledge.trace_service.TraceService", lambda session: FakeTrace()
    )
    return calls


# ── 路径 #1：normal + 证据充分 ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_path1_normal_with_evidence_grounds_chat_and_records_trace(
    compiled_graph, monkeypatch
):
    graph, captured = compiled_graph

    result = RetrievalResult(
        has_evidence=True,
        context_text="[S1] 私有资料证据片段",
        sources=[{"label": "[S1]", "title": "doc"}],
        trace_hits=[{"chunk_id": "c1", "retrieval_source": "hybrid", "rank": 0}],
        rewritten_query="test query rewritten",
    )
    _install_retriever(monkeypatch, result)
    trace_calls = _install_trace(monkeypatch)

    config = {"configurable": {"thread_id": "path1"}}
    final_state: ChatAgentState = await graph.ainvoke(
        _base_state("帮我解释下 RAG 是什么", "normal"), config
    )

    # 检索执行 + Trace 落库三段式
    assert trace_calls["create"] == 1
    assert trace_calls["record_hits"] == 1
    assert trace_calls["finalize"] == 1
    # state 透传 trace_id
    assert final_state.get("trace_id") is not None
    # chat_node 被调用且 system_message 含 grounded context 与 [Sx] 引用指令
    assert len(captured) == 1
    system_msg = captured[0][0]
    assert "私有资料上下文" in system_msg.content
    assert "[S1]" in system_msg.content
    # 无 fallback
    assert final_state.get("fallback_reason") is None


# ── 路径 #2：normal + 证据不足 ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_path2_normal_insufficient_evidence_falls_back_with_notice(
    compiled_graph, monkeypatch
):
    graph, captured = compiled_graph

    result = RetrievalResult(
        has_evidence=False,
        context_text="",
        sources=[],
        trace_hits=[],
        rewritten_query="q",
        fallback_reason="No evidence above threshold",
    )
    _install_retriever(monkeypatch, result)
    trace_calls = _install_trace(monkeypatch)

    config = {"configurable": {"thread_id": "path2"}}
    final_state: ChatAgentState = await graph.ainvoke(
        _base_state("帮我解释下 RAG 是什么", "normal"), config
    )

    # 仍然检索 + Trace 落库
    assert trace_calls["create"] == 1
    # fallback 原因进入 state
    assert final_state.get("fallback_reason") is not None
    # chat_node system_message 含降级提示
    assert len(captured) == 1
    assert "私有资料库中没有找到足够的相关证据" in captured[0][0].content


# ── 路径 #3：strict + 证据不足 ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_path3_strict_insufficient_evidence_refuses_without_chat_llm(
    compiled_graph, monkeypatch
):
    graph, captured = compiled_graph

    result = RetrievalResult(
        has_evidence=False,
        context_text="",
        sources=[],
        trace_hits=[],
        rewritten_query="q",
        fallback_reason="No evidence above threshold in strict mode",
    )
    _install_retriever(monkeypatch, result)
    _install_trace(monkeypatch)

    config = {"configurable": {"thread_id": "path3"}}
    final_state: ChatAgentState = await graph.ainvoke(
        _base_state("帮我解释下 RAG 是什么", "strict"), config
    )

    # chat LLM 不被调用
    assert len(captured) == 0
    # 最后一Message 是固定拒答文本
    last_msg = final_state["messages"][-1]
    assert "严格知识库模式下无法回答" in last_msg.content


# ── 路径 #4：off ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_path4_off_mode_skips_retrieval(compiled_graph, monkeypatch):
    graph, captured = compiled_graph

    # 即便装了 retriever，off 模式也不应被调用
    retriever_called = {"n": 0}
    fake_svc = MagicMock()
    async def _retrieve(_):
        retriever_called["n"] += 1
        return None
    fake_svc.retrieve = _retrieve
    monkeypatch.setattr(
        "app.application.knowledge.retrieval_service.KnowledgeRetrievalService",
        lambda session: fake_svc,
    )

    config = {"configurable": {"thread_id": "path4"}}
    final_state: ChatAgentState = await graph.ainvoke(
        _base_state("帮我解释下 RAG 是什么", "off"), config
    )

    # off 模式：rag_decision=False，retriever 未被调用
    assert final_state.get("rag_decision") is False
    assert retriever_called["n"] == 0
    # trace_id 应为 None（没检索就没 Trace）
    assert final_state.get("trace_id") is None
    # chat LLM 被调用（直接进 chat 节点）
    assert len(captured) == 1