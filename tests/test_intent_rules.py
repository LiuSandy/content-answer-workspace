"""意图规则层测试：确定性关键词判定不依赖 LLM。"""
from __future__ import annotations

from app.application.agent.nodes.intent_rules import (
    detect_intent_by_rules,
    detect_knowledge_mode,
    extract_urls,
)


# ── URL ─────────────────────────────────────────────────────────────────

def test_extract_urls():
    assert extract_urls("看这个 https://zhuanlan.zhihu.com/p/123") == [
        "https://zhuanlan.zhihu.com/p/123"
    ]


def test_rule_url_parse_intent():
    r = detect_intent_by_rules("解析一下 https://www.xiaohongshu.com/note/abc")
    assert r["intent"] == "parse_url"
    assert r["confidence"] == 1.0


# ── 寒暄 ────────────────────────────────────────────────────────────────

def test_rule_chitchat():
    for msg in ("你好", "在吗", "谢谢", "hello", "bye", "嗯嗯"):
        r = detect_intent_by_rules(msg)
        assert r is not None
        assert r["intent"] == "chat"
        assert r["knowledge_mode"] == "off"


# ── 严格知识模式 ────────────────────────────────────────────────────────

def test_rule_strict_knowledge_mode():
    r = detect_intent_by_rules("只能根据我上传的文件回答，为什么 chmod 能防未授权")
    assert r is not None
    assert r["knowledge_mode"] == "strict"
    assert r["intent"] == "chat"


def test_detect_knowledge_mode_plain():
    assert detect_knowledge_mode("帮我写一篇关于 RAG 的回答") == "normal"


# ── 平台采集 ────────────────────────────────────────────────────────────

def test_rule_xiaohongshu_collection():
    r = detect_intent_by_rules("请您检索一下小红书关于历史播客的帖子，只要五个")
    assert r["intent"] == "chat"
    assert r["platform"] == "xiaohongshu"
    assert r["knowledge_mode"] == "normal"
    assert "历史播客" in (r["query"] or "")


def test_rule_zhihu_search():
    r = detect_intent_by_rules("帮我搜搜知乎上关于副业的热门讨论")
    assert r["intent"] == "chat"
    assert r["platform"] == "zhihu"


def test_zhihu_collection_removes_polite_words_from_query():
    r = detect_intent_by_rules("帮忙检索一下知乎的热门问题")

    assert r is not None
    assert r["platform"] == "zhihu"
    assert r["query"] == "热门"


def test_rule_bilibili_collection():
    r = detect_intent_by_rules("采集 B站 上关于 AI 的视频")
    assert r["intent"] == "chat"
    assert r["platform"] == "bilibili"


def test_rule_generic_collection_low_confidence():
    """有采集动作但无平台名 → 规则给低置信度，交 LLM 精修。"""
    r = detect_intent_by_rules("帮我找找有哪些做副业的内容")
    assert r is not None
    assert r["intent"] == "chat"
    assert r["confidence"] < 1.0


# ── 创作 ────────────────────────────────────────────────────────────────

def test_rule_task_plan():
    r = detect_intent_by_rules("写一篇关于 RAG 的回答")
    assert r["intent"] == "task_plan"
    assert r["confidence"] == 1.0


def test_rule_task_plan_short():
    r = detect_intent_by_rules("写个小红书种草笔记")
    assert r["intent"] == "task_plan"


def test_rule_multi_agent():
    r = detect_intent_by_rules("调研并输出一份 AI Agent 行业现状的完整分析报告")
    assert r["intent"] == "multi_agent"
    assert r["confidence"] == 1.0


def test_rule_multi_agent_wins_over_task_plan():
    """含"调研并写一篇" → 多阶段优先。"""
    r = detect_intent_by_rules("帮我调研一下并写一篇完整的技术报告")
    assert r["intent"] == "multi_agent"


# ── 未命中 → 交 LLM ─────────────────────────────────────────────────────

def test_rule_miss_falls_through_to_llm():
    r = detect_intent_by_rules("你觉得人工智能未来的发展趋势如何")
    assert r is None


def test_rule_qa_question_is_miss():
    """一般问答不属于任何规则意图。"""
    r = detect_intent_by_rules("为什么天空是蓝色的")
    assert r is None
