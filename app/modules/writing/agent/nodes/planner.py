"""Planning and assignment nodes for the Writer graph."""
from __future__ import annotations

import time

from app.modules.writing.agent.state import SubAgentState, WriterState
from app.modules.writing.application.planning import generate_plan


async def plan_node(state: WriterState) -> dict:
    return {"plan": await generate_plan(state["goal"])}


def assign_node(state: WriterState) -> dict:
    states = dict(state.get("sub_agent_states") or {})
    sub = SubAgentState(name="orchestrator", status="running", started_at=time.monotonic())
    states["orchestrator"] = sub
    try:
        plan = state["plan"]
        if not plan.tasks:
            raise ValueError("空 TaskPlan")
        sub.result = {
            "total_tasks": len(plan.tasks),
            "task_ids": [task.task_id for task in plan.tasks],
        }
        sub.status = "done"
    except Exception as exc:
        sub.status = "failed"
        sub.error = str(exc)
    finally:
        sub.completed_at = time.monotonic()
    return {"sub_agent_states": states}


def route_after_assignment(state: WriterState) -> str:
    return "end" if state["sub_agent_states"]["orchestrator"].status == "failed" else "research"


__all__ = ["assign_node", "plan_node", "route_after_assignment"]
