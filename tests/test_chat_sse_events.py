"""稳定 SSE 事件封装测试（roadmap R2 Step 3/4）。

覆盖：事件匹配不再依赖单一 langgraph_node 字符串（事件 name 与 metadata
二者其一即可命中）；RAG / task_plan / multi_agent 完成事件、message.delta、
节点开始状态事件均能稳定产出。
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from app.application.agent.scheduling import run_agent_stream

_RETRIEVAL_STATE = {
    "retrieval_result": SimpleNamespace(
        has_evidence=True,
        sources=[{"label": "[S1]", "title": "Doc A", "sourceType": "私有资料", "sourceUrl": None, "text": "正文"}],
        fallback_reason=None,
    ),
    "trace_id": "t1",
}


class _EmitGraph:
    def __init__(self, events) -> None:
        self.events = events

    async def astream_events(self, inputs, config, version="v2"):
        for e in self.events:
            yield e


def _on_node_start(name: str) -> dict:
    return {"event": "on_node_start", "name": name, "data": {}}


def _on_chain_end(name: str, output: dict, metadata: dict | None = None) -> dict:
    return {"event": "on_chain_end", "name": name, "data": {"output": output}, "metadata": metadata or {}}


def _on_chat_model_stream(delta: str) -> dict:
    return {"event": "on_chat_model_stream", "name": "ChatModel", "data": {"chunk": SimpleNamespace(content=delta)}}


def _collect(events) -> list[tuple[str, dict]]:
    async def _run():
        out = []
        async for ev in run_agent_stream(_EmitGraph(events), {}, {}, timeout_seconds=5):
            out.append(ev)
        return out

    return asyncio.run(_run())


def _find(events, name: str) -> dict | None:
    for n, data in events:
        if n == name:
            return data
    return None


def test_node_start_maps_to_stable_status_events():
    events = _collect([
        _on_node_start("route_intent"),
        _on_node_start("chat"),
        _on_node_start("parse_url"),
        _on_node_start("collect"),
    ])
    assert ("agent.status", {"status": "routing_intent"}) in events
    assert ("agent.status", {"status": "generating"}) in events
    assert ("tool.started", {"tool_type": "parse_url"}) in events
    assert ("tool.started", {"tool_type": "collect"}) in events


def test_rag_sources_event_matches_by_event_name_when_metadata_foreign():
    """metadata.langgraph_node 不属于稳定节点时，回退使用事件 name。"""
    events = _collect([
        _on_chain_end("retrieve_knowledge", _RETRIEVAL_STATE, metadata={"langgraph_node": "subgraph_internal"}),
    ])
    data = _find(events, "rag.sources")
    assert data is not None
    assert data["traceId"] == "t1"
    assert data["sources"][0]["label"] == "[S1]"


def test_rag_sources_event_matches_by_metadata_when_name_foreign():
    events = _collect([
        _on_chain_end("unknown", _RETRIEVAL_STATE, metadata={"langgraph_node": "retrieve_knowledge"}),
    ])
    assert _find(events, "rag.sources") is not None


def test_rag_fallback_event_when_no_evidence():
    state = {
        "retrieval_result": SimpleNamespace(
            has_evidence=False,
            sources=[],
            fallback_reason="证据不足",
        ),
        "trace_id": "t2",
    }
    events = _collect([_on_chain_end("retrieve_knowledge", state)])
    assert _find(events, "rag.fallback") is not None


def test_task_plan_event_when_metadata_matches():
    out = {"task_plan_result": {"planId": "p1", "goal": "目标", "status": "done", "preview": "预览"}}
    events = _collect([_on_chain_end("unknown", out, metadata={"langgraph_node": "task_plan"})])
    data = _find(events, "task_plan.created")
    assert data is not None
    assert data["planId"] == "p1"


def test_multi_agent_event_when_metadata_matches():
    out = {"multi_agent_result": {"status": "running", "agents": [{"name": "a1"}], "finalContent": None}}
    events = _collect([_on_chain_end("unknown", out, metadata={"langgraph_node": "multi_agent"})])
    data = _find(events, "multi_agent.status")
    assert data is not None
    assert data["status"] == "running"


def test_message_delta_event():
    events = _collect([_on_chat_model_stream("你好"), _on_chat_model_stream("世界")])
    deltas = [d["delta"] for n, d in events if n == "message.delta"]
    assert deltas == ["你好", "世界"]
