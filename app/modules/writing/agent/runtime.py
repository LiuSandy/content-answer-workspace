"""Writer Graph 的应用层运行入口。"""

from app.modules.writing.agent.graph import writer_graph
from app.modules.writing.agent.state import MultiAgentState


async def run_writer_plan(goal: str, workspace_id: str = "default") -> MultiAgentState:
    result = await writer_graph.ainvoke(
        {
            "operation": "compose",
            "goal": goal,
            "workspace_id": workspace_id,
            "owner_id": "default",
            "sub_agent_states": {},
            "interrupted": False,
        }
    )
    if result.get("guard_blocked"):
        raise ValueError(result.get("guard_reason") or "request_blocked")
    return MultiAgentState(
        plan=result["plan"],
        sub_agent_states=result.get("sub_agent_states") or {},
        research_report=result.get("research_report"),
        draft=result.get("draft"),
        final_output=result.get("final_output"),
        quality_score=result.get("quality_score"),
        interrupted=result.get("interrupted", False),
        interrupt_reason=result.get("interrupt_reason"),
    )


__all__ = ["run_writer_plan"]
