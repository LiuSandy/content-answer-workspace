from __future__ import annotations

from ....core.prompts import CONVERSATION_SYSTEM_PROMPT
from ....infrastructure.llm.deepseek_client import DeepSeekAnswerGenerator
from ..state import ConversationState

_generator = DeepSeekAnswerGenerator()

_ROLE_MAP = {"human": "user", "ai": "assistant", "system": "system"}


async def chat_node(state: ConversationState) -> dict:
    """把完整对话历史交给 LLM 做多轮对话；不调用任何业务工具，只返回新的一条助手消息。"""

    history = [{"role": "system", "content": CONVERSATION_SYSTEM_PROMPT}]
    for message in state["messages"]:
        history.append({"role": _ROLE_MAP.get(message.type, "user"), "content": message.content})

    reply = await _generator.chat(history)
    return {"messages": [{"role": "assistant", "content": reply}]}
