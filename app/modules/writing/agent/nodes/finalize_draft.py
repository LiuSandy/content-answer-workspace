from __future__ import annotations

import time

from app.modules.writing.agent.state import WriterState


def finalize_draft_node(state: WriterState) -> dict:
    """完成 Writer 状态，保持原有成功与失败语义。"""
    sub_agent_states = dict(state.get("sub_agent_states") or {})
    sub = sub_agent_states["writing"]
    if state.get("writing_error"):
        sub.status = "failed"
        sub.error = state["writing_error"]
    else:
        sub.result = dict(state.get("draft_metadata") or {})
        sub.status = "done"
    sub.completed_at = time.monotonic()
    return {"sub_agent_states": sub_agent_states}
