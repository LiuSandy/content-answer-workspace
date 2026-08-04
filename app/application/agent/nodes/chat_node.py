"""普通对话节点：进行普通多轮对话。"""
from __future__ import annotations

import os
from langchain_core.messages import SystemMessage
from langchain_openai import ChatOpenAI

from ....prompts.registry import prompt_registry
from ..state import ChatAgentState


from ..tools import ALL_TOOLS


def _get_chat_llm() -> ChatOpenAI:
    llm = ChatOpenAI(
        api_key=os.getenv("DEEPSEEK_API_KEY", ""),
        base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").strip().rstrip("/"),
        model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
        streaming=True,
    )
    # 绑定对话中支持的工具
    return llm.bind_tools(ALL_TOOLS)



_llm: ChatOpenAI | None = None


async def chat_node(state: ChatAgentState) -> dict:
    global _llm
    if _llm is None:
        _llm = _get_chat_llm()

    # 从 Prompt Registry 加载系统 Prompt
    try:
        rendered = prompt_registry.render("chat.system")
        system_content = rendered.messages[0].content
    except Exception:
        system_content = "你是一个内容创作助手，帮助用户从平台发现优质帖子，并为其创作高质量回答。"

    retrieval_result = state.get("retrieval_result")
    if retrieval_result and getattr(retrieval_result, "has_evidence", False):
        grounded_context = f"\n\n【私有资料上下文】\n{getattr(retrieval_result, 'context_text', '')}\n\n请在回答中使用 [S1]、[S2] 等标签引用对应资料，且只能引用上述资料中实际存在的内容。"
        system_content = system_content + grounded_context
    elif retrieval_result and not getattr(retrieval_result, "has_evidence", False):
        fallback_notice = "\n\n【提示】私有资料库中没有找到足够的相关证据，本回答将基于通用知识作答。"
        system_content = system_content + fallback_notice

    # Phase 4 长期记忆注入：spec 3.3 让 Agent 体现用户偏好
    applied = state.get("applied_memories") or []
    if applied:
        memories_block = "\n\n【用户长期偏好（已应用 {} 条记忆）】\n".format(len(applied))
        for i, m in enumerate(applied, 1):
            memories_block += f"[M{i}] ({m.get('memory_type')}) {m.get('content')}\n"
        memories_block += "\n请在回答中体现上述偏好；不要直接引用 [Mx] 标签。"
        system_content = system_content + memories_block

    messages = [SystemMessage(content=system_content)] + list(state.get("messages", []))
    response = await _llm.ainvoke(messages)
    return {"messages": [response]}
