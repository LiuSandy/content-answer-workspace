"""Specialist business nodes for the single Writer graph."""
from __future__ import annotations

import asyncio
import time

from app.modules.writing.agent.nodes.finalize_draft import finalize_draft_node
from app.modules.writing.agent.nodes.generate_draft import generate_draft_node
from app.modules.writing.agent.nodes.prepare_prompt import prepare_prompt_node
from app.modules.writing.agent.state import SubAgentState, WriterState
from app.modules.writing.application import planning as planning_service
from app.modules.writing.application.creation_review import run_creation_review
from app.modules.writing.application.llm import get_writing_llm
from app.modules.writing.application.review import ReviewContext, evaluate_content
from app.modules.writing.agent.progress import emit_progress


async def research_node(state: WriterState) -> dict:
    emit_progress(state, "research")
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
            results = await planning_service.execute_task_plan(
                partial_plan,
                fail_fast=bool(state.get("direct_stream")),
            )
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
    if error and state.get("direct_stream"):
        emit_progress(state, "research", "failed", error=error)
        raise RuntimeError(f"研究资料失败：{error}")

    emit_progress(state, "research", "completed", completed=len(results), total=len(tasks))
    return {
        "research_report": report,
        "research_tasks": tasks,
        "task_results": results,
        "research_error": error,
        "sub_agent_states": states,
    }


async def write_node(state: WriterState) -> dict:
    emit_progress(state, "write")
    # Document generation and full rewrite share the compose branch. Their
    # existing document workflows remain the persistence/streaming adapters,
    # while the graph still guarantees plan -> research -> outline first.
    if state.get("direct_stream"):
        from app.modules.writing.agent.nodes.document_pipeline import (
            generate_document_node,
            rewrite_document_node,
        )

        handler = (
            rewrite_document_node
            if state.get("creation_mode") == "rewrite"
            else generate_document_node
        )
        result = await handler(state)
        result = {
            "draft": result.get("final_output"),
            "final_output": result.get("final_output"),
            "document_state": result.get("document_state") or {},
            "writing_error": None,
            "draft_metadata": {"document_completed": True},
            "sub_agent_states": state.get("sub_agent_states") or {},
        }
        emit_progress(state, "write", "completed")
        return result

    working = {**state, **prepare_prompt_node(state)}
    working.update(await generate_draft_node(working))
    working.update(finalize_draft_node(working))
    result = {
        "draft": working.get("draft"),
        "writing_prompt": working.get("writing_prompt", ""),
        "writing_error": working.get("writing_error"),
        "draft_metadata": working.get("draft_metadata") or {},
        "sub_agent_states": working.get("sub_agent_states") or {},
    }
    emit_progress(state, "write", "completed")
    return result


async def review_node(state: WriterState) -> dict:
    if state.get("direct_stream"):
        states = dict(state.get("sub_agent_states") or {})
        states["review"] = SubAgentState(
            name="review",
            status="done",
            result={"handled_by": "document_creation_workflow"},
        )
        return {
            "final_output": state.get("final_output") or state.get("draft") or "",
            "sub_agent_states": states,
        }
    emit_progress(state, "review")
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
            return await get_writing_llm().refine(
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
        result = {
            "final_output": outcome.final_content,
            "quality_score": score,
            "review_context": context,
            "review_outcome": outcome,
            "review_error": None,
            "sub_agent_states": states,
        }
        emit_progress(state, "review", "completed")
        return result
    except Exception as exc:  # preserve draft when review fails
        sub.status = "failed"
        sub.error = str(exc)
        result = {
            "final_output": state.get("draft"),
            "review_context": context,
            "review_outcome": None,
            "review_error": str(exc),
            "sub_agent_states": states,
        }
        emit_progress(state, "review", "failed")
        return result
    finally:
        sub.completed_at = time.monotonic()


async def writer_memory_node(state: WriterState) -> dict:
    if state.get("direct_stream"):
        states = dict(state.get("sub_agent_states") or {})
        states["memory"] = SubAgentState(
            name="memory",
            status="done",
            result={"skipped": "document_creation_workflow"},
        )
        return {"sub_agent_states": states}
    emit_progress(state, "memory")
    from app.modules.memory.application import manage_memory as memory_service

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
    emit_progress(state, "memory", "completed" if sub.status == "done" else "failed")
    return {"sub_agent_states": states}


def finalize_writer_node(state: WriterState) -> dict:
    emit_progress(state, "finalize")
    return {
        "final_output": state.get("final_output") or state.get("draft") or "",
        "sub_agent_states": state.get("sub_agent_states") or {},
    }


__all__ = ["finalize_writer_node", "research_node", "review_node", "write_node", "writer_memory_node"]
