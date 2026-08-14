"""Researcher Agent 私有状态类型。"""

from app.agents.orchestrator.state import MultiAgentGraphState
from app.services.planning_service import SubTask


class ResearcherState(MultiAgentGraphState, total=False):
    research_tasks: list[SubTask]
    task_results: dict[str, str]
    research_error: str | None
