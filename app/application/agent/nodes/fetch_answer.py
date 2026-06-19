from __future__ import annotations

from ..state import AgentState
from ..ports import SessionServicePort


async def fetch_answer_node(state: AgentState, *, session_svc: SessionServicePort) -> dict:
    """从 Session 读取当前回答，写入 current_answer。不做任何业务判断。"""
    answer = await session_svc.get_answer(state["session_id"], state["question_id"] or "")
    return {"current_answer": answer}
