"""多 Agent 协作执行节点：意图识别为 multi_agent 时，调用 run_multi_agent_plan。"""
from __future__ import annotations

import logging

from langchain_core.messages import AIMessage

from .multi_agent import run_multi_agent_plan
from ..state import ChatAgentState

logger = logging.getLogger(__name__)


async def multi_agent_node(state: ChatAgentState) -> dict:
    """启动 5 个子 Agent（编排/调研/写作/自评/记忆）协作完成复杂目标。"""
    goal = state.get("user_message", "")
    workspace_id = state.get("workspace_id", "default")

    try:
        result = await run_multi_agent_plan(goal, workspace_id)

        final_content = result.final_output or result.draft or ""
        subs = result.sub_agent_states or {}

        agents_preview = [
            {
                "name": name,
                "status": sub.status,
                "message": sub.error or (str(sub.result)[:200] if sub.result else None),
            }
            for name, sub in subs.items()
        ]

        msg = AIMessage(content=f"多 Agent 协作已完成「{goal}」：\n\n{final_content}")
        return {
            "messages": [msg],
            "multi_agent_result": {
                "status": "done",
                "agents": agents_preview,
                "finalContent": final_content[:4000],
            },
        }
    except Exception as e:
        logger.error("Multi-agent execution failed: %s", e)
        msg = AIMessage(content=f"多 Agent 协作执行失败：{e}")
        return {
            "messages": [msg],
            "multi_agent_result": {
                "status": "failed",
                "agents": [],
                "error": str(e),
            },
        }
