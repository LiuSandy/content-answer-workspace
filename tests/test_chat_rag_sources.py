"""Chat SSE 流中 RAG 参考来源事件（rag.sources / rag.fallback）构建逻辑测试。"""
from __future__ import annotations

from types import SimpleNamespace

from app.api.routes.chats import _build_rag_payload


def _fake_retrieval(has_evidence: bool, sources: list, fallback_reason: str | None = None):
    return SimpleNamespace(
        has_evidence=has_evidence,
        sources=sources,
        fallback_reason=fallback_reason,
    )


def test_build_rag_payload_with_evidence():
    node_state = {
        "retrieval_result": _fake_retrieval(
            has_evidence=True,
            sources=[
                {
                    "label": "[S1]",
                    "title": "文件安全与权限",
                    "sourceUrl": "http://example.com/a",
                    "text": "设置文件权限位可防止未授权访问…",
                },
                {
                    "label": "[S2]",
                    "title": "chmod 命令详解",
                    "text": "chmod 可改变文件权限…",
                },
            ],
        ),
        "trace_id": "trace-123",
    }
    payload = _build_rag_payload(node_state)
    assert payload is not None
    assert len(payload["sources"]) == 2
    assert payload["sources"][0]["label"] == "[S1]"
    assert payload["sources"][0]["title"] == "文件安全与权限"
    assert payload["sources"][0]["sourceType"] == "私有资料"
    assert payload["sources"][0]["contentSnippet"].startswith("设置文件权限位")
    assert payload["fallbackNotice"] is None
    assert payload["traceId"] == "trace-123"


def test_build_rag_payload_no_evidence_returns_fallback():
    node_state = {
        "retrieval_result": _fake_retrieval(
            has_evidence=False,
            sources=[],
            fallback_reason="阈值未达标：证据不足",
        ),
        "trace_id": "trace-456",
    }
    payload = _build_rag_payload(node_state)
    assert payload is not None
    assert payload["sources"] == []
    assert payload["fallbackNotice"] == "阈值未达标：证据不足"
    assert payload["traceId"] == "trace-456"


def test_build_rag_payload_no_evidence_default_notice():
    node_state = {
        "retrieval_result": _fake_retrieval(
            has_evidence=False,
            sources=[],
            fallback_reason=None,
        ),
    }
    payload = _build_rag_payload(node_state)
    assert payload is not None
    assert payload["sources"] == []
    assert payload["fallbackNotice"] == "私有资料证据不足，使用了其他知识来源"


def test_build_rag_payload_no_retrieval_returns_none():
    assert _build_rag_payload({}) is None
    assert _build_rag_payload({"retrieval_result": None, "trace_id": "x"}) is None


def test_build_rag_payload_skips_sources_without_label():
    node_state = {
        "retrieval_result": _fake_retrieval(
            has_evidence=True,
            sources=[
                {"label": "[S1]", "title": "命中", "text": "内容"},
                {"label": None, "title": "未纳入上下文", "text": "跳过"},
            ],
        ),
    }
    payload = _build_rag_payload(node_state)
    assert payload is not None
    assert len(payload["sources"]) == 1
    assert payload["sources"][0]["label"] == "[S1]"
