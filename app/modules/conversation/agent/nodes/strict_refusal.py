"""严格知识库模式下，无证据时的拒答节点。"""

from langchain_core.messages import AIMessage

from app.modules.conversation.agent.state import ChatAgentState


async def strict_refusal_node(_state: ChatAgentState) -> dict:
    return {
        "messages": [
            AIMessage(
                content=(
                    "私有资料库中没有足够的相关证据，在严格知识库模式下无法回答该问题。"
                    "请切换至普通模式或补充相关资料后重试。"
                )
            )
        ]
    }


__all__ = ["strict_refusal_node"]
