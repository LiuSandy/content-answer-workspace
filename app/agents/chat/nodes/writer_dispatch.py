"""Map ChatState to WriterState and invoke the single Writer graph."""
from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import AIMessage

from app.state import ChatAgentState

logger = logging.getLogger(__name__)


def build_writer_dispatch_node(writer_graph: Any | None = None):
    async def writer_dispatch_node(state: ChatAgentState) -> dict:
        graph = writer_graph
        if graph is None:
            from app.agents.writer.graph import writer_graph as default_writer_graph

            graph = default_writer_graph

        goal = state.get("user_message", "")
        intent = state.get("intent") or "multi_agent"
        try:
            result = await graph.ainvoke(
                {
                    "operation": "compose",
                    "goal": goal,
                    "workspace_id": state.get("workspace_id", "default"),
                    "owner_id": state.get("owner_id", "default"),
                    "sub_agent_states": {},
                    "interrupted": False,
                }
            )
            if result.get("guard_blocked"):
                content = result.get("final_output") or "该写作请求已被安全策略拦截。"
                if intent == "task_plan":
                    return {
                        "messages": [AIMessage(content=content)],
                        "task_plan_result": {
                            "planId": None,
                            "goal": goal,
                            "status": "blocked",
                            "error": result.get("guard_reason"),
                        },
                    }
                return {
                    "messages": [AIMessage(content=content)],
                    "multi_agent_result": {
                        "status": "blocked",
                        "agents": [],
                        "error": result.get("guard_reason"),
                    },
                }

            final_content = result.get("final_output") or result.get("draft") or ""
            subs = result.get("sub_agent_states") or {}
            agents = [
                {
                    "name": name,
                    "status": sub.status,
                    "message": sub.error or (str(sub.result)[:200] if sub.result else None),
                }
                for name, sub in subs.items()
            ]
            if intent == "task_plan":
                plan = result.get("plan")
                plan_id = getattr(plan, "plan_id", None)
                task_results = dict(result.get("task_results") or {})
                for task in getattr(plan, "tasks", []) or []:
                    if getattr(task, "type", None) == "write" and final_content:
                        task_results.setdefault(task.task_id, final_content)
                try:
                    from app.agents.writer.nodes.task_plan_persistence import persist_task_plan

                    plan_id = await persist_task_plan(
                        plan,
                        goal,
                        state.get("workspace_id", "default"),
                        task_results,
                    )
                except Exception as persist_error:  # graph result remains useful without the card audit
                    logger.warning("Task plan persistence failed: %s", persist_error)
                payload = {
                    "planId": str(plan_id) if plan_id else None,
                    "goal": goal,
                    "status": "done",
                    "taskCount": len(getattr(plan, "tasks", []) or []),
                    "preview": final_content[:500],
                }
                return {
                    "messages": [AIMessage(content=f"已完成复合创作任务「{goal}」：\n\n{final_content}")],
                    "task_plan_result": payload,
                }
            return {
                "messages": [AIMessage(content=f"多 Agent 协作已完成「{goal}」：\n\n{final_content}")],
                "multi_agent_result": {
                    "status": "done",
                    "agents": agents,
                    "finalContent": final_content[:4000],
                },
            }
        except Exception as error:  # noqa: BLE001 - graph boundary returns stable state
            logger.exception("Writer graph dispatch failed")
            if intent == "task_plan":
                return {
                    "messages": [AIMessage(content=f"复合创作执行失败：{error}")],
                    "task_plan_result": {
                        "planId": None,
                        "goal": goal,
                        "status": "failed",
                        "error": str(error),
                    },
                }
            return {
                "messages": [AIMessage(content=f"内容创作执行失败：{error}")],
                "multi_agent_result": {
                    "status": "failed",
                    "agents": [],
                    "error": str(error),
                },
            }

    return writer_dispatch_node


__all__ = ["build_writer_dispatch_node"]
