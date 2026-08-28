from __future__ import annotations

import time

from app.agents.writer.state import SubAgentState, WriterState


def prepare_prompt_node(state: WriterState) -> dict:
    """按现有格式准备写作 Prompt 并初始化 Writer 状态。"""
    sub_agent_states = dict(state.get("sub_agent_states") or {})
    sub = SubAgentState(name="writing", status="running")
    sub.started_at = time.monotonic()
    sub_agent_states["writing"] = sub
    memories = state.get("applied_memories") or []
    memory_context = ""
    if memories:
        memory_context = "\n\n用户长期创作偏好：\n" + "\n".join(
            f"- [{memory.get('memory_scope', 'general')}] {memory.get('content', '')}"
            for memory in memories
        )
    prompt = (
        "你是一位内容写作专家。请基于研究报告生成结构化的初稿。\n\n"
        f"创作目标：{state['plan'].goal}\n\n"
        f"研究报告：\n{state.get('research_report') or '（无研究报告）'}\n\n"
        f"{memory_context}\n\n"
        "请输出完整的 Markdown 正文。"
    )
    return {
        "writing_prompt": prompt,
        "writing_error": None,
        "draft_metadata": {},
        "sub_agent_states": sub_agent_states,
    }
