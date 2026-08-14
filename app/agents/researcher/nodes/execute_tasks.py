from __future__ import annotations

import logging

from app.agents.researcher.state import ResearcherState
from app.services import planning_service

logger = logging.getLogger(__name__)


async def execute_tasks_node(state: ResearcherState) -> dict:
    """按现有拓扑调度规则执行 Researcher 的搜索与分析任务。"""
    partial_plan = planning_service.TaskPlan(
        plan_id=state["plan"].plan_id,
        goal=state["plan"].goal,
        tasks=list(state.get("research_tasks") or []),
    )
    try:
        results = await planning_service.execute_task_plan(partial_plan)
        return {"task_results": results, "research_error": None}
    except Exception as error:
        logger.error("ResearchAgent failed: %s", error)
        return {"task_results": {}, "research_error": str(error)}
