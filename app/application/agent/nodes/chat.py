from __future__ import annotations

from langchain_core.messages import SystemMessage
from langchain_openai import ChatOpenAI

from ....core.config import get_required_env
from ....core.prompts import CONVERSATION_SYSTEM_PROMPT
from ..state import ConversationState
from ..tools import ALL_TOOLS

_llm_with_tools: ChatOpenAI | None = None


def _get_llm() -> ChatOpenAI:
    global _llm_with_tools
    if _llm_with_tools is None:
        llm = ChatOpenAI(
            api_key=get_required_env("DEEPSEEK_API_KEY"),
            base_url=get_required_env("DEEPSEEK_BASE_URL").strip().rstrip("/"),
            model=get_required_env("DEEPSEEK_MODEL"),
        )
        _llm_with_tools = llm.bind_tools(ALL_TOOLS)
    return _llm_with_tools


async def chat_node(state: ConversationState) -> dict:
    """ReAct 模型节点：LLM 携带工具，有工具调用时返回 tool_calls，否则直接返回文本回复。"""
    messages = [SystemMessage(content=CONVERSATION_SYSTEM_PROMPT)] + list(state["messages"])
    response = await _get_llm().ainvoke(messages)
    return {"messages": [response]}
