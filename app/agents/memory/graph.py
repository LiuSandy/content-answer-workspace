"""Memory Agent 的长期记忆沉淀流程。"""
from __future__ import annotations

import asyncio

from app.agents.orchestrator.state import MultiAgentState, SubAgentState
from app.services.memory import service as memory_service


async def memory_agent_node(state: MultiAgentState) -> dict:
    """从本次创作目标与结果中提取长期记忆。"""
    sub = SubAgentState(name="memory", status="running")
    state.sub_agent_states["memory"] = sub
    sub.started_at = asyncio.get_event_loop().time()

    try:
        messages = [
            {"role": "user", "content": state.plan.goal},
            {"role": "assistant", "content": state.final_output or ""},
        ]
        saved = await memory_service.extract_memories(messages, session_id=state.plan.plan_id)
        sub.result = {"memories_saved": len(saved)}
        sub.status = "done"
    except Exception as error:
        sub.status = "failed"
        sub.error = str(error)
    finally:
        sub.completed_at = asyncio.get_event_loop().time()

    return {"sub_agent_states": state.sub_agent_states}
