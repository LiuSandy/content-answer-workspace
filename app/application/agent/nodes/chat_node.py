"""普通对话节点：进行普通多轮对话。"""
from __future__ import annotations

import os
from langchain_core.messages import SystemMessage
from langchain_openai import ChatOpenAI

from ....prompts.registry import prompt_registry
from ..state import ConversationState


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


async def chat_node(state: ConversationState) -> dict:
    global _llm
    if _llm is None:
        _llm = _get_chat_llm()

    # 从 Prompt Registry 加载系统 Prompt
    try:
        rendered = prompt_registry.render("chat.system")
        system_content = rendered.messages[0].content
    except Exception:
        system_content = "你是一个内容创作助手，帮助用户从平台发现优质帖子，并为其创作高质量回答。"

    messages = [SystemMessage(content=system_content)] + list(state.get("messages", []))
    response = await _llm.ainvoke(messages)
    return {"messages": [response]}
