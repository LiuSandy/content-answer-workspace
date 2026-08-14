from __future__ import annotations

import time

from app.agents.orchestrator.state import (
    MultiAgentGraphState,
    SubAgentState,
)


def assign_tasks_node(state: MultiAgentGraphState) -> dict:
    """验证计划并记录 Orchestrator 的任务分配结果。"""
    sub_agent_states = dict(state.get("sub_agent_states") or {})
    sub = SubAgentState(name="orchestrator", status="running")
    sub.started_at = time.monotonic()
    sub_agent_states["orchestrator"] = sub
    try:
        plan = state["plan"]
        if not plan.tasks:
            raise ValueError("空 TaskPlan")
        sub.result = {
            "total_tasks": len(plan.tasks),
            "task_ids": [task.task_id for task in plan.tasks],
        }
        sub.status = "done"
    except Exception as error:
        sub.status = "failed"
        sub.error = str(error)
    finally:
        sub.completed_at = time.monotonic()
    return {"sub_agent_states": sub_agent_states}


def route_after_assignment(state: MultiAgentGraphState) -> str:
    sub = state["sub_agent_states"]["orchestrator"]
    return "end" if sub.status == "failed" else "researcher"
