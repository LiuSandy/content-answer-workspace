"""意图识别评测：规则层全量回归 + route_intent 三层集成。

规则层用例（rule_only=True）不依赖 LLM，必须确定性通过。
LLM 用例用 mock LLM 验证路由正确性。
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.modules.conversation.agent.nodes.intent_rules import detect_intent_by_rules
from app.modules.conversation.agent.nodes.route_intent import route_intent_node
from tests.llm_fakes import structured_gateway
from tests.intent_eval_cases import INTENT_EVAL_CASES


# ── 规则层全量回归 ───────────────────────────────────────────────────────

def test_rule_layer_all_rule_only_cases():
    """所有 rule_only 用例必须被规则层确定性命中。"""
    for case in INTENT_EVAL_CASES:
        if not case.get("rule_only"):
            continue
        r = detect_intent_by_rules(case["input"])
        assert r is not None, f"规则层未命中: {case['input']}"
        assert r["intent"] == case["intent"], (
            f"intent 不符: {case['input']} → {r['intent']}, 期望 {case['intent']}"
        )
        if case.get("platform"):
            assert r.get("platform") == case["platform"], (
                f"platform 不符: {case['input']} → {r.get('platform')}, 期望 {case['platform']}"
            )
        if case.get("knowledge_mode"):
            assert r["knowledge_mode"] == case["knowledge_mode"], (
                f"knowledge_mode 不符: {case['input']} → {r['knowledge_mode']}"
            )


def test_rule_layer_llm_only_cases_not_shortcircuited():
    """非 rule_only 用例不应被规则层确定性命中（留给 LLM）。"""
    for case in INTENT_EVAL_CASES:
        if case.get("rule_only"):
            continue
        r = detect_intent_by_rules(case["input"])
        assert r is None or r["confidence"] < 1.0, (
            f"本应交 LLM 却被规则确定性命中: {case['input']}"
        )


# ── route_intent 三层集成（mock LLM） ────────────────────────────────────

def _make_llm_mock(monkeypatch, content: str):
    fake_rendered = MagicMock()
    fake_rendered.to_llm_request.return_value = MagicMock()
    fake_prompt_registry = MagicMock()
    fake_prompt_registry.render.return_value = fake_rendered
    gateway = structured_gateway(content)
    monkeypatch.setattr(
        "app.modules.conversation.agent.nodes.route_intent._get_intent_gateway",
        lambda: gateway,
    )
    monkeypatch.setattr(
        "app.modules.conversation.agent.nodes.route_intent.prompt_registry", fake_prompt_registry
    )
    return gateway


def _state(message: str) -> dict:
    return {"user_message": message, "extracted_urls": []}


@pytest.mark.asyncio
async def test_route_rule_layer_shortcircuits_llm(monkeypatch):
    """规则命中时 LLM 不应被调用。"""
    provider = _make_llm_mock(monkeypatch, '{"intent": "chat", "confidence": 1.0}')
    out = await route_intent_node(_state("写一篇关于 RAG 的回答"))
    assert out["intent"] == "task_plan"
    provider.generate.assert_not_called()


@pytest.mark.asyncio
async def test_route_llm_used_when_rule_misses(monkeypatch):
    """规则未命中时调用 LLM。"""
    provider = _make_llm_mock(
        monkeypatch,
        '{"intent": "chat", "knowledge_mode": "normal", "confidence": 0.9, "reason": "qa"}',
    )
    out = await route_intent_node(_state("为什么天空是蓝色的"))
    assert out["intent"] == "chat"
    provider.generate_structured.assert_awaited_once()


@pytest.mark.asyncio
async def test_route_low_confidence_falls_back_to_chat(monkeypatch):
    """LLM 低置信度 → 降级 chat。"""
    _make_llm_mock(
        monkeypatch,
        '{"intent": "multi_agent", "knowledge_mode": "normal", "confidence": 0.3, "reason": "uncertain"}',
    )
    out = await route_intent_node(_state("这个有点难判断"))
    assert out["intent"] == "chat"
    assert out["intent_confidence"] == 0.0


@pytest.mark.asyncio
async def test_route_invalid_intent_normalized(monkeypatch):
    """LLM 返回非法 intent → 归一化为 chat。"""
    _make_llm_mock(
        monkeypatch,
        '{"intent": "whatever", "knowledge_mode": "normal", "confidence": 0.9}',
    )
    out = await route_intent_node(_state("测试"))
    assert out["intent"] == "chat"


@pytest.mark.asyncio
async def test_route_llm_platform_query_captured(monkeypatch):
    """LLM 层返回的平台搜索结构被完整捕获到 state。"""
    _make_llm_mock(
        monkeypatch,
        '{"intent": "collect", "knowledge_mode": "normal", "platform": "zhihu", '
        '"query": "AI 副业", "limit": 5, "sort": "hot", '
        '"confidence": 0.9, "reason": "search"}',
    )
    out = await route_intent_node(_state("帮我找找 AI 副业的东西"))
    assert out["intent"] == "collect"
    assert out["intent_platform"] == "zhihu"
    assert out["intent_query"] == "AI 副业"
    assert out["intent_limit"] == 5
    assert out["intent_sort"] == "hot"


@pytest.mark.asyncio
async def test_route_llm_bad_json_falls_back(monkeypatch):
    """LLM 返回坏 JSON → 保守 chat（无法解析时按默认 chat）。"""
    _make_llm_mock(monkeypatch, "完全不是 JSON")
    out = await route_intent_node(_state("测试"))
    assert out["intent"] == "chat"


@pytest.mark.asyncio
async def test_route_does_not_inherit_previous_strict(monkeypatch):
    """上一轮的 strict 不得覆盖本轮识别结果。"""
    _make_llm_mock(monkeypatch, '{"intent": "chat", "knowledge_mode": "normal", "confidence": 0.9}')
    state = _state("解释下 RAG")
    state["knowledge_mode"] = "strict"
    out = await route_intent_node(state)
    assert out["knowledge_mode"] == "normal"
