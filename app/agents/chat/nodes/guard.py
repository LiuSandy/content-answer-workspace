"""Chat graph guard: reject unsafe input before memory, routing, or tools."""
from __future__ import annotations

import logging

from langchain_core.messages import AIMessage

from app.agents._shared.injection import detect_input_injection, validate_scope
from app.contracts.dto import AgentError
from app.state import ChatAgentState

logger = logging.getLogger(__name__)

_BLOCK_MESSAGE = "该请求触发了安全策略，无法继续处理。请直接描述你的内容需求，不要要求覆盖系统规则或披露内部配置。"


async def guard_node(state: ChatAgentState) -> dict:
    """Perform deterministic injection and tenant-scope validation."""

    blocked, reason = detect_input_injection(state.get("user_message", ""))
    if not blocked:
        for field in ("workspace_id", "owner_id"):
            valid, scope_reason = validate_scope(state.get(field), field=field)
            if not valid:
                blocked, reason = True, scope_reason
                break

    if not blocked:
        return {
            "guard_blocked": False,
            "guard_reason": None,
        }

    logger.warning(
        "Chat guard blocked request: reason=%s chat_id=%s",
        reason,
        state.get("chat_id"),
    )
    return {
        "guard_blocked": True,
        "guard_reason": reason,
        "error": AgentError(error_code="request_blocked", message=_BLOCK_MESSAGE),
        "messages": [AIMessage(content=_BLOCK_MESSAGE)],
    }


def route_after_guard(state: ChatAgentState) -> str:
    return "blocked" if state.get("guard_blocked") else "continue"


__all__ = ["guard_node", "route_after_guard"]
