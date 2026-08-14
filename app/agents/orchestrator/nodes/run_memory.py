from __future__ import annotations

from app.agents.memory.graph import memory_agent_node
from app.agents.orchestrator.state import MultiAgentGraphState, MultiAgentState


async def run_memory_node(state: MultiAgentGraphState) -> dict:
    """适配父图状态并调用保持不变的 Memory Agent 函数。"""
    compatibility_state = MultiAgentState(
        plan=state["plan"],
        sub_agent_states=state.get("sub_agent_states") or {},
        research_report=state.get("research_report"),
        draft=state.get("draft"),
        final_output=state.get("final_output"),
        quality_score=state.get("quality_score"),
        interrupted=state.get("interrupted", False),
        interrupt_reason=state.get("interrupt_reason"),
    )
    result = await memory_agent_node(compatibility_state)
    return {"sub_agent_states": result["sub_agent_states"]}
