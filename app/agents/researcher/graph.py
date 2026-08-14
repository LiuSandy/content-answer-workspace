"""Researcher Agent 的资料采集与分析流程。"""
from __future__ import annotations

import asyncio
import logging

from app.agents.orchestrator.state import MultiAgentState, SubAgentState
from app.services.planning_service import TaskPlan, execute_task_plan, topological_order

logger = logging.getLogger(__name__)


async def research_agent_node(state: MultiAgentState) -> dict:
    """并行执行计划中的搜索与分析任务。"""
    sub = SubAgentState(name="research", status="running")
    state.sub_agent_states["research"] = sub
    sub.started_at = asyncio.get_event_loop().time()

    try:
        research_tasks = [t for t in state.plan.tasks if t.type in ("search", "analyze")]
        if not research_tasks:
            state.research_report = ""
            sub.status = "done"
            sub.completed_at = asyncio.get_event_loop().time()
            return {"research_report": state.research_report, "sub_agent_states": state.sub_agent_states}

        partial_plan = TaskPlan(
            plan_id=state.plan.plan_id,
            goal=state.plan.goal,
            tasks=research_tasks,
        )
        results = await execute_task_plan(partial_plan)
        state.research_report = "\n\n".join(f"## {tid}\n{result}" for tid, result in results.items())
        sub.tool_calls = [
            {"task_id": task.task_id, "type": task.type, "status": "done" if task.task_id in results else "failed"}
            for task in research_tasks
        ]
        concurrent = max(len(layer) for layer in topological_order(partial_plan))
        sub.result = {"concurrent_calls": concurrent, "completed": len(results)}
        sub.status = "done"
    except Exception as error:
        sub.status = "failed"
        sub.error = str(error)
        logger.error("ResearchAgent failed: %s", error)
    finally:
        sub.completed_at = asyncio.get_event_loop().time()

    return {"research_report": state.research_report, "sub_agent_states": state.sub_agent_states}
