from __future__ import annotations

from app.modules.conversation.agent.state import AgentState
from app.shared.agent_ports import SessionServicePort


async def save_answer_node(state: AgentState, *, session_svc: SessionServicePort) -> dict:
    """将修改后的回答持久化到 session adapter。唯一有副作用的节点。"""
    await session_svc.update_answer(
        state["session_id"],
        state["question_id"] or "",
        state["updated_answer"] or "",
    )
    return {}
