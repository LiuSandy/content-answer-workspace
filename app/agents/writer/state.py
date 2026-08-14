"""Writer Agent 私有状态类型。"""

from typing import Any

from app.agents.orchestrator.state import MultiAgentGraphState
from app.state import AgentState


class WriterState(MultiAgentGraphState, total=False):
    writing_prompt: str
    writing_error: str | None
    draft_metadata: dict[str, Any]

__all__ = ["AgentState", "WriterState"]
