"""State owned by the single Writer graph."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, TypedDict

from app.contracts.dto import QualityReport
from app.services.planning_service import TaskPlan

SubAgentName = Literal["orchestrator", "research", "writing", "review", "memory"]


@dataclass
class SubAgentState:
    """Compatibility status exposed by the existing multi-agent API."""

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
    """Writer Graph 面向现有协作 API 返回的结构化结果。"""

    plan: TaskPlan
    sub_agent_states: dict[SubAgentName, SubAgentState] = field(default_factory=dict)
    research_report: str | None = None
    draft: str | None = None
    final_output: str | None = None
    quality_score: float | None = None
    interrupted: bool = False
    interrupt_reason: str | None = None


class WriterState(TypedDict, total=False):
    operation: Literal["compose", "generate", "inline_refine", "full_rewrite"]
    goal: str
    workspace_id: str
    owner_id: str
    guard_blocked: bool
    guard_reason: str | None
    plan: TaskPlan
    sub_agent_states: dict[str, SubAgentState]
    interrupted: bool
    interrupt_reason: str | None
    applied_memories: list[dict] | None
    research_tasks: list[Any]
    task_results: dict[str, str]
    research_error: str | None
    research_report: str | None
    writing_prompt: str
    writing_error: str | None
    draft_metadata: dict[str, Any]
    draft: str | None
    review_context: Any
    review_outcome: Any
    review_error: str | None
    review_report: QualityReport | None
    quality_score: float | None
    final_output: str | None
    # Direct document operations (Writer graph is intentionally not checkpointed,
    # so request-scoped service/session objects may be injected here).
    session: Any
    source_item_id: Any
    document_id: Any
    platform: str | None
    title: str
    content: str | None
    instruction: str | None
    style_rules: str | None
    word_count: int
    expected_lock_version: int
    selection: Any
    outline: list[dict] | None
    outline_operation_id: Any
    generate_workflow: Any
    refine_workflow: Any
    rewrite_workflow: Any
    evaluate_content: Any
    persist_creation_review: Any
    rewrite_content: Any
    document_state: dict[str, Any]
    direct_stream: bool


__all__ = ["MultiAgentState", "SubAgentName", "SubAgentState", "WriterState"]
