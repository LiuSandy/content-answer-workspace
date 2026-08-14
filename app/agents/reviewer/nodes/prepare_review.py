from __future__ import annotations

import time

from app.agents.orchestrator.state import SubAgentState
from app.agents.reviewer.state import ReviewerState
from app.services.quality_service import ReviewContext


def prepare_review_node(state: ReviewerState) -> dict:
    """建立审核上下文并初始化 Reviewer 状态。"""
    sub_agent_states = dict(state.get("sub_agent_states") or {})
    sub = SubAgentState(name="review", status="running")
    sub.started_at = time.monotonic()
    sub_agent_states["review"] = sub
    return {
        "review_context": ReviewContext(
            question=state["plan"].goal,
            style_rules=None,
            target_word_count=1000,
            iteration=1,
        ),
        "review_outcome": None,
        "review_error": None,
        "sub_agent_states": sub_agent_states,
    }
