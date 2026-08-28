"""Persist Writer planning output for the existing TaskPlanCard API."""
from __future__ import annotations

from app.infrastructure.database.session import get_session_factory
from app.infrastructure.database.models.task_plans import SubTaskModel, TaskPlanModel


async def persist_task_plan(plan, goal: str, workspace_id: str, results: dict[str, str]) -> str:
    factory = get_session_factory()
    async with factory() as session:
        row = TaskPlanModel(workspace_id=workspace_id, goal=goal, status="done")
        session.add(row)
        await session.flush()
        for task in plan.tasks:
            session.add(
                SubTaskModel(
                    plan_id=row.id,
                    task_id=task.task_id,
                    type=task.type,
                    description=task.description,
                    depends_on=task.depends_on,
                    status="done" if task.task_id in results else "failed",
                    result=results.get(task.task_id),
                )
            )
        await session.commit()
        return str(row.id)


__all__ = ["persist_task_plan"]
