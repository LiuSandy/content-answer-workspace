from __future__ import annotations

import time

from app.agents.reviewer.state import ReviewerState


def finalize_review_node(state: ReviewerState) -> dict:
    """写回成功审核结果。"""
    outcome = state["review_outcome"]
    quality_score = (
        outcome.final_report.overall_score if outcome.final_report else None
    )
    sub_agent_states = dict(state.get("sub_agent_states") or {})
    sub = sub_agent_states["review"]
    sub.result = {
        "iterations": outcome.iterations,
        "passed": outcome.passed,
        "review_failed": outcome.review_failed,
        "quality_score": quality_score,
    }
    sub.status = "done"
    sub.completed_at = time.monotonic()
    return {
        "final_output": outcome.final_content,
        "quality_score": quality_score,
        "sub_agent_states": sub_agent_states,
    }
