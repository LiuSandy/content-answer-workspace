"""R4：ContextComposer 预算测试。

覆盖 40 轮 CJK、超长 RAG、超长当前指令、最近两轮保留和输出 token 预留。
"""
from __future__ import annotations

import pytest

from app.services.context.composer import (
    ContextComposer,
    SimpleContextProfile,
    estimate_tokens,
)


def _turns(n: int, content: str) -> list[dict[str, str]]:
    msgs: list[dict[str, str]] = []
    for i in range(n):
        msgs.append({"role": "user", "content": content})
        msgs.append({"role": "assistant", "content": content + "（回答）"})
    return msgs


def test_cjk_token_estimate_is_deterministic():
    """CJK 字符按 1 token 估算，确定可复现。"""
    assert estimate_tokens("你好世界") == 4
    assert estimate_tokens("") == 0
    assert estimate_tokens("abc") >= 1


def test_forty_rounds_stay_within_budget():
    """40 轮长中文对话触发裁剪，总输入仍不超预算。"""
    profile = SimpleContextProfile(context_window=64000, output_reserve_tokens=4096)
    composer = ContextComposer(profile)
    content = "这是一段用于测试预算裁剪的较长的对话消息内容。" * 60
    messages = _turns(40, content)
    result = composer.assemble(messages, system_prompt="你是内容创作助手。")

    assert result.total_tokens() + 4096 <= 64000
    assert result.dropped > 0  # 40 轮必然触发裁剪


def test_long_rag_context_reduces_message_budget():
    """超长 RAG 上下文占用预算，保留更少的历史消息，最近两轮不受影响。"""
    profile = SimpleContextProfile(context_window=8000, output_reserve_tokens=1024)
    composer = ContextComposer(profile)
    messages = _turns(20, "短文内容用于测试上下文预算。" * 10)

    without_rag = composer.assemble(messages, system_prompt="s", current_instruction="q")
    with_rag = composer.assemble(
        messages,
        system_prompt="s",
        current_instruction="q",
        rag_context="【私有资料】" * 500,
    )
    assert with_rag.dropped > without_rag.dropped
    assert len(with_rag.messages) < len(without_rag.messages)
    assert with_rag.messages[-4:] == messages[-4:]  # 最近两轮仍完整保留


def test_long_current_instruction_never_trimmed():
    """超长当前指令不因预算被裁剪，且总输入仍受预算约束。"""
    profile = SimpleContextProfile(context_window=12000, output_reserve_tokens=2000)
    composer = ContextComposer(profile)
    messages = _turns(10, "普通历史消息。")
    long_instruction = "请按照以下要求创作：" + "非常详细的要求。" * 500

    result = composer.assemble(messages, system_prompt="s", current_instruction=long_instruction)
    assert result.total_tokens() <= 12000
    assert any(m["content"] == long_instruction for m in result.messages) or long_instruction in str(result.current_instruction)


def test_recent_two_turns_always_kept():
    """最近两轮（最后一轮 user/assistant）必须完整保留，即使历史被裁剪。"""
    profile = SimpleContextProfile(context_window=6000, output_reserve_tokens=1000)
    composer = ContextComposer(profile)
    messages = _turns(30, "每轮内容大约二三十个字。" * 100)
    result = composer.assemble(messages, system_prompt="s")

    assert result.dropped > 0
    recent = messages[-4:]  # 最近两轮 = 4 条消息
    recent_contents = {m["content"] for m in recent}
    kept_contents = {m["content"] for m in result.messages}
    assert recent_contents <= kept_contents


def test_output_reserve_respected():
    """输出预留：即使窗口很小，也保证 reserve 的 token 不被消息占满。"""
    profile = SimpleContextProfile(context_window=3000, output_reserve_tokens=1500)
    composer = ContextComposer(profile)
    messages = _turns(10, "消息内容" * 20)
    result = composer.assemble(messages, system_prompt="s")

    assert result.total_tokens() <= 3000 - 1500


def test_short_conversation_unchanged():
    """短对话无需裁剪，消息完整保留。"""
    profile = SimpleContextProfile(context_window=64000, output_reserve_tokens=4096)
    composer = ContextComposer(profile)
    messages = _turns(2, "你好，帮我分析一下。")
    result = composer.assemble(messages, system_prompt="s")
    assert result.dropped == 0
    assert len(result.messages) == len(messages)


def test_summary_injected_and_counted():
    """摘要注入后参与预算计算。"""
    profile = SimpleContextProfile(context_window=8000, output_reserve_tokens=1000)
    composer = ContextComposer(profile)
    messages = _turns(15, "历史消息。")
    with_summary = composer.assemble(
        messages,
        system_prompt="s",
        summary="【此前对话摘要】" + "用户偏好简洁风格。" * 50,
    )
    assert with_summary.summary is not None
    assert with_summary.total_tokens() <= 8000
