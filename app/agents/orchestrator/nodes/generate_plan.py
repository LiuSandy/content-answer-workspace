from __future__ import annotations

from app.agents.orchestrator.state import MultiAgentGraphState
from app.services.planning_service import generate_plan


async def generate_plan_node(state: MultiAgentGraphState) -> dict:
    """根据协作目标生成现有 TaskPlan。"""
    plan = await generate_plan(state["goal"])
    return {"plan": plan}
