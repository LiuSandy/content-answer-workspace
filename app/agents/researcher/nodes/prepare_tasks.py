from __future__ import annotations

import time

from app.agents.orchestrator.state import SubAgentState
from app.agents.researcher.state import ResearcherState


def prepare_tasks_node(state: ResearcherState) -> dict:
    """筛选研究任务并初始化 Researcher 运行状态。"""
    sub_agent_states = dict(state.get("sub_agent_states") or {})
    sub = SubAgentState(name="research", status="running")
    sub.started_at = time.monotonic()
    sub_agent_states["research"] = sub
    research_tasks = [
        task for task in state["plan"].tasks if task.type in ("search", "analyze")
    ]
    return {
        "research_tasks": research_tasks,
        "task_results": {},
        "research_error": None,
        "sub_agent_states": sub_agent_states,
    }


def route_after_prepare(state: ResearcherState) -> str:
    return "execute_tasks" if state.get("research_tasks") else "build_report"
