from __future__ import annotations

import time

from app.agents.reviewer.state import ReviewerState


def preserve_draft_node(state: ReviewerState) -> dict:
    """审核失败时保留初稿并记录隔离错误。"""
    sub_agent_states = dict(state.get("sub_agent_states") or {})
    sub = sub_agent_states["review"]
    sub.status = "failed"
    sub.error = state.get("review_error")
    sub.completed_at = time.monotonic()
    return {
        "final_output": state.get("draft"),
        "sub_agent_states": sub_agent_states,
    }
