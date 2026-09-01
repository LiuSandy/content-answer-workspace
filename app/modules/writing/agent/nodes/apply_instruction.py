from __future__ import annotations

from app.modules.conversation.agent.state import AgentState
from app.shared.agent_ports import LLMClientPort


async def apply_instruction_node(state: AgentState, *, llm: LLMClientPort) -> dict:
    """调用 LLM 按用户指令定向修改回答。不做持久化和路由判断。"""
    updated = await llm.refine(
        instruction=state["user_message"],
        current_answer=state["current_answer"] or "",
    )
    short = state["user_message"][:30]
    return {
        "updated_answer": updated,
        "reply": "已按您的要求完成修改。",
        "answer_updated": True,
        "operation_summary": f"修改：{short}",
    }
