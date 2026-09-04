"""Writer graph guard shared by chat-dispatched and direct writing runs."""
from __future__ import annotations

import logging

from app.shared.agent.injection import detect_input_injection, validate_scope
from app.modules.writing.agent.state import SubAgentState, WriterState
from app.shared.errors import ValidationError
from app.modules.writing.agent.progress import emit_progress

logger = logging.getLogger(__name__)


async def writer_guard_node(state: WriterState) -> dict:
    emit_progress(state, "guard")
    blocked, reason = detect_input_injection(state.get("goal", ""))
    if not blocked:
        for field in ("workspace_id", "owner_id"):
            valid, scope_reason = validate_scope(state.get(field), field=field)
            if not valid:
                blocked, reason = True, scope_reason
                break

    if not blocked:
        emit_progress(state, "guard", "completed")
        return {"guard_blocked": False, "guard_reason": None}

    logger.warning("Writer guard blocked request: reason=%s", reason)
    emit_progress(state, "guard", "failed")
    if state.get("direct_stream"):
        raise ValidationError("该写作请求触发了安全策略，无法继续处理。")
    states = dict(state.get("sub_agent_states") or {})
    states["guard"] = SubAgentState(
        name="orchestrator",
        status="failed",
        error=f"request_blocked: {reason}",
    )
    return {
        "guard_blocked": True,
        "guard_reason": reason,
        "interrupt_reason": f"request_blocked: {reason}",
        "final_output": "该写作请求触发了安全策略，无法继续处理。",
        "sub_agent_states": states,
    }


def route_after_writer_guard(state: WriterState) -> str:
    return "blocked" if state.get("guard_blocked") else "continue"


__all__ = ["route_after_writer_guard", "writer_guard_node"]
