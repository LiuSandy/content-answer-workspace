"""Writer Agent 私有状态类型。"""

from app.agents.orchestrator.state import MultiAgentState
from app.state import AgentState

WriterState = MultiAgentState

__all__ = ["AgentState", "WriterState"]
