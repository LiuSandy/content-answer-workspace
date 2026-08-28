"""Specialist business nodes for the single Writer graph."""
from __future__ import annotations

import asyncio
import time

from app.agents.writer.nodes.finalize_draft import finalize_draft_node
from app.agents.writer.nodes.generate_draft import generate_draft_node
from app.agents.writer.nodes.prepare_prompt import prepare_prompt_node
from app.agents.writer.state import SubAgentState, WriterState
from app.services import planning_service
from app.services.creation_review_service import run_creation_review
from app.services.llm_service import LLMServiceAdapter
from app.services.quality_service import ReviewContext, evaluate_content


async def research_node(state: WriterState) -> dict:
    states = dict(state.get("sub_agent_states") or {})
    sub = SubAgentState(name="research", status="running", started_at=time.monotonic())
    states["research"] = sub
    tasks = [task for task in state["plan"].tasks if task.type in ("search", "analyze")]
    results: dict[str, str] = {}
    error: str | None = None
    if tasks:
        partial_plan = planning_service.TaskPlan(
            plan_id=state["plan"].plan_id,
            goal=state["plan"].goal,
            tasks=tasks,
        )
        try:
            results = await planning_service.execute_task_plan(partial_plan)
        except Exception as exc:  # specialist failure is isolated
            error = str(exc)

    sub.tool_calls = [
        {
            "task_id": task.task_id,
            "type": task.type,
            "status": "done" if task.task_id in results else "failed",
        }
        for task in tasks
    ]
    if error:
        sub.status = "failed"
        sub.error = error
    elif tasks:
        partial_plan = planning_service.TaskPlan(
            plan_id=state["plan"].plan_id,
            goal=state["plan"].goal,
            tasks=tasks,
        )
        sub.result = {
            "concurrent_calls": max(len(layer) for layer in planning_service.topological_order(partial_plan)),
            "completed": len(results),
        }
        sub.status = "done"
    else:
        sub.status = "done"
    sub.completed_at = time.monotonic()

    if error and not results:
        report = state.get("research_report")
    else:
        report = "\n\n".join(f"## {task_id}\n{value}" for task_id, value in results.items())
    return {
        "research_report": report,
        "research_tasks": tasks,
        "task_results": results,
        "research_error": error,
        "sub_agent_states": states,
    }


async def write_node(state: WriterState) -> dict:
    working = {**state, **prepare_prompt_node(state)}
    working.update(await generate_draft_node(working))
    working.update(finalize_draft_node(working))
    return {
        "draft": working.get("draft"),
        "writing_prompt": working.get("writing_prompt", ""),
        "writing_error": working.get("writing_error"),
        "draft_metadata": working.get("draft_metadata") or {},
        "sub_agent_states": working.get("sub_agent_states") or {},
    }


async def review_node(state: WriterState) -> dict:
    states = dict(state.get("sub_agent_states") or {})
    sub = SubAgentState(name="review", status="running", started_at=time.monotonic())
    states["review"] = sub
    context = ReviewContext(
        question=state["plan"].goal,
        style_rules=None,
        target_word_count=1000,
        iteration=1,
    )

    try:
        async def rewrite(content: str, instruction: str) -> str:
            return await LLMServiceAdapter().refine(
                instruction=instruction,
                current_answer=content,
            )

        outcome = None
        async for event in run_creation_review(
            initial_content=state.get("draft") or "",
            context=context,
            evaluate=evaluate_content,
            rewrite=rewrite,
        ):
            if event.outcome is not None:
                outcome = event.outcome
        if outcome is None:
            raise RuntimeError("创作评审未产生结果")

        score = outcome.final_report.overall_score if outcome.final_report else None
        sub.result = {
            "iterations": outcome.iterations,
            "passed": outcome.passed,
            "review_failed": outcome.review_failed,
            "quality_score": score,
        }
        sub.status = "done"
        return {
            "final_output": outcome.final_content,
            "quality_score": score,
            "review_context": context,
            "review_outcome": outcome,
            "review_error": None,
            "sub_agent_states": states,
        }
    except Exception as exc:  # preserve draft when review fails
        sub.status = "failed"
        sub.error = str(exc)
        return {
            "final_output": state.get("draft"),
            "review_context": context,
            "review_outcome": None,
            "review_error": str(exc),
            "sub_agent_states": states,
        }
    finally:
        sub.completed_at = time.monotonic()


async def writer_memory_node(state: WriterState) -> dict:
    from app.services.memory import service as memory_service

    states = dict(state.get("sub_agent_states") or {})
    sub = SubAgentState(name="memory", status="running", started_at=time.monotonic())
    states["memory"] = sub
    try:
        saved = await memory_service.extract_memories(
            [
                {"role": "user", "content": state["plan"].goal},
                {"role": "assistant", "content": state.get("final_output") or ""},
            ],
            session_id=state["plan"].plan_id,
        )
        sub.result = {"memories_saved": len(saved)}
        sub.status = "done"
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # memory is non-blocking
        sub.status = "failed"
        sub.error = str(exc)
    finally:
        sub.completed_at = time.monotonic()
    return {"sub_agent_states": states}


def finalize_writer_node(state: WriterState) -> dict:
    return {
        "final_output": state.get("final_output") or state.get("draft") or "",
        "sub_agent_states": state.get("sub_agent_states") or {},
    }


__all__ = ["finalize_writer_node", "research_node", "review_node", "write_node", "writer_memory_node"]
