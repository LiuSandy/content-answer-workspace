"""Orchestrator Agent 私有状态与协作状态。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, TypedDict

from app.services.planning_service import TaskPlan

SubAgentName = Literal["orchestrator", "research", "writing", "review", "memory"]


@dataclass
class SubAgentState:
    """单个协作 Agent 的隔离状态。"""

    name: SubAgentName
    status: Literal["pending", "running", "done", "failed"] = "pending"
    messages: list[dict[str, str]] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    result: Any = None
    error: str | None = None
    started_at: float | None = None
    completed_at: float | None = None


@dataclass
class MultiAgentState:
    """多 Agent 协作共享状态。"""

    plan: TaskPlan
    sub_agent_states: dict[SubAgentName, SubAgentState] = field(default_factory=dict)
    research_report: str | None = None
    draft: str | None = None
    final_output: str | None = None
    quality_score: float | None = None
    interrupted: bool = False
    interrupt_reason: str | None = None


class MultiAgentGraphState(TypedDict, total=False):
    """父图与子图之间共享的协作状态。"""

    goal: str
    workspace_id: str
    plan: TaskPlan
    sub_agent_states: dict[SubAgentName, SubAgentState]
    research_report: str | None
    draft: str | None
    final_output: str | None
    quality_score: float | None
    interrupted: bool
    interrupt_reason: str | None
