from __future__ import annotations

import time

from app.agents.researcher.state import ResearcherState
from app.services.planning_service import TaskPlan, topological_order


def build_report_node(state: ResearcherState) -> dict:
    """汇总研究结果并完成 Researcher 状态。"""
    tasks = list(state.get("research_tasks") or [])
    results = dict(state.get("task_results") or {})
    sub_agent_states = dict(state.get("sub_agent_states") or {})
    sub = sub_agent_states["research"]

    sub.tool_calls = [
        {
            "task_id": task.task_id,
            "type": task.type,
            "status": "done" if task.task_id in results else "failed",
        }
        for task in tasks
    ]
    if state.get("research_error"):
        sub.status = "failed"
        sub.error = state["research_error"]
    elif tasks:
        partial_plan = TaskPlan(
            plan_id=state["plan"].plan_id,
            goal=state["plan"].goal,
            tasks=tasks,
        )
        concurrent = max(len(layer) for layer in topological_order(partial_plan))
        sub.result = {"concurrent_calls": concurrent, "completed": len(results)}
        sub.status = "done"
    else:
        sub.status = "done"
    sub.completed_at = time.monotonic()

    if state.get("research_error") and not results:
        report = state.get("research_report")
    else:
        report = "\n\n".join(
            f"## {task_id}\n{result}" for task_id, result in results.items()
        )
    return {
        "research_report": report,
        "sub_agent_states": sub_agent_states,
    }
