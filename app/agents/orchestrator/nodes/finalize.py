from __future__ import annotations

from app.agents.orchestrator.state import MultiAgentGraphState


def finalize_node(state: MultiAgentGraphState) -> dict:
    """显式结束协作流程并保留共享输出。"""
    return {"sub_agent_states": state.get("sub_agent_states") or {}}
