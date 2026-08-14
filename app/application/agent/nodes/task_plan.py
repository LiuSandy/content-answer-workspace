"""复合任务执行节点：意图识别为 task_plan 时，调用 TaskPlannerService 规划并执行。"""
from __future__ import annotations

import logging

from langchain_core.messages import AIMessage

from ...task_planner_service import generate_plan, execute_task_plan
from ..state import ChatAgentState

logger = logging.getLogger(__name__)


async def task_plan_node(state: ChatAgentState) -> dict:
    """将用户目标拆解为 TaskPlan 并执行，产出最终创作内容。"""
    goal = state.get("user_message", "")
    workspace_id = state.get("workspace_id", "default")

    try:
        plan = await generate_plan(goal)
        results = await execute_task_plan(plan)

        # 将 plan 与子任务落库，供前端 TaskPlanCard 通过 REST API 查询进度
        plan_row_id = await _persist_plan(plan, goal, workspace_id, results)

        # 生成创作正文：优先取 write 子任务的输出
        write_outputs = [
            results[t.task_id] for t in plan.tasks
            if t.type == "write" and t.task_id in results
        ]
        final_content = write_outputs[-1] if write_outputs else (
            list(results.values())[-1] if results else ""
        )

        summary = "\n\n".join(
            f"### {t.task_id}\n{results[t.task_id][:800]}"
            for t in plan.tasks if t.task_id in results
        )[:6000]

        msg = AIMessage(content=f"已完成复合创作任务「{goal}」：\n\n{final_content or summary}")
        return {
            "messages": [msg],
            "task_plan_result": {
                "planId": str(plan_row_id),
                "goal": goal,
                "status": "done",
                "taskCount": len(plan.tasks),
                "preview": (final_content or summary)[:500],
            },
        }
    except Exception as e:
        logger.error("Task plan execution failed: %s", e)
        msg = AIMessage(content=f"复合任务执行失败：{e}")
        return {
            "messages": [msg],
            "task_plan_result": {"planId": None, "goal": goal, "status": "failed", "error": str(e)},
        }


async def _persist_plan(plan, goal: str, workspace_id: str, results: dict[str, str]) -> str:
    """将 TaskPlan 及其子任务执行结果落库，供前端 TaskPlanCard 查询。"""
    from app.persistence.session import get_session_factory
    from app.persistence.models.task_plans import TaskPlanModel, SubTaskModel

    factory = get_session_factory()
    async with factory() as session:
        plan_row = TaskPlanModel(
            workspace_id=workspace_id,
            goal=goal,
            status="done",
        )
        session.add(plan_row)
        await session.flush()
        for t in plan.tasks:
            sub = SubTaskModel(
                plan_id=plan_row.id,
                task_id=t.task_id,
                type=t.type,
                description=t.description,
                depends_on=t.depends_on,
                status="done",
                result=results.get(t.task_id),
            )
            session.add(sub)
        await session.commit()
        return str(plan_row.id)
