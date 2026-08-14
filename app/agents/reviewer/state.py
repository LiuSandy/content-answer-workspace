"""Reviewer Agent 私有状态类型。"""

from typing import Any

from app.agents.orchestrator.state import MultiAgentGraphState


class ReviewerState(MultiAgentGraphState, total=False):
    review_context: Any
    review_outcome: Any
    review_error: str | None
