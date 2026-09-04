"""Document-operation nodes hosted by the single Writer graph."""
from __future__ import annotations

import logging

from langgraph.config import get_stream_writer

from app.modules.writing.application.creation_review import CreationReviewOutcome, run_creation_review
from app.modules.documents.application.documents import DocumentService
from app.modules.writing.application.review import ReviewContext, persist_creation_review
from app.modules.writing.application.writing_service import WriterRunCapture, finalize_deferred_writer_run
from app.modules.writing.agent.state import WriterState

logger = logging.getLogger(__name__)


def _emit(event: str, data: dict) -> None:
    get_stream_writer()({"event": event, "data": data})


def creation_review_metadata(outcome: CreationReviewOutcome) -> dict:
    report = outcome.final_report
    return {
        "creationReview": {
            "reviewStatus": "failed" if outcome.review_failed else "completed",
            "iterations": outcome.iterations,
            "passed": outcome.passed,
            "selectedIteration": outcome.selected_iteration,
            "finalReport": report.model_dump(mode="json", by_alias=True) if report else None,
            "rounds": [
                {
                    "iteration": row.iteration,
                    "overallScore": row.report.overall_score,
                    "passed": row.report.overall_score >= 75,
                }
                for row in outcome.rounds
            ],
            "errorMessage": outcome.error_message,
        }
    }


def route_writer_operation(state: WriterState) -> str:
    return state.get("operation", "compose")


def _with_memory_preferences(value: str | None, state: WriterState) -> str | None:
    memories = state.get("applied_memories") or []
    if not memories:
        return value
    memory_text = "\n".join(
        f"- [{memory.get('memory_scope', 'general')}] {memory.get('content', '')}"
        for memory in memories
    )
    blocks = [block for block in (value, f"用户长期创作偏好：\n{memory_text}") if block]
    return "\n\n".join(blocks)


def _with_writing_context(state: WriterState) -> str | None:
    """Make the plan and research explicit in the final document prompt."""
    blocks = []
    if state.get("goal"):
        blocks.append(
            "\n\n【本次创作目标（最高优先级）】\n"
            + str(state["goal"])
            + "\n必须围绕该目标完成文章，不能退回回答原始帖子主题。"
        )
    if state.get("research_report"):
        blocks.append(
            "\n\n【本次研究报告】\n"
            + str(state["research_report"])
            + "\n请使用其中与创作目标相关的事实和结论。"
        )
    return "".join(blocks) or None


async def generate_document_node(state: WriterState) -> dict:
    session = state["session"]
    capture = WriterRunCapture()
    workflow = state["generate_workflow"]
    async for delta in workflow(
        session=session,
        source_item_id=state["source_item_id"],
        document_id=state["document_id"],
        platform=state.get("platform") or "zhihu",
        title=state["title"],
        content=state.get("content"),
        expected_lock_version=state["expected_lock_version"],
        style_rules=_with_memory_preferences(state.get("style_rules"), state),
        word_count=state.get("word_count", 1000),
        instruction=state.get("instruction"),
        extra_context=_with_writing_context(state),
        capture=capture,
        outline=state.get("outline"),
        outline_operation_id=state.get("outline_operation_id"),
        writing_settings=state.get("writing_settings"),
    ):
        _emit("document.delta", {"delta": delta})

    outcome: CreationReviewOutcome | None = None
    async for review_event in run_creation_review(
        initial_content=capture.content,
        context=ReviewContext(
            question=state.get("goal") or state["title"],
            style_rules=_with_memory_preferences(state.get("style_rules"), state),
            target_word_count=state.get("word_count", 1000),
            iteration=1,
        ),
        evaluate=state["evaluate_content"],
        rewrite=state["rewrite_content"],
    ):
        if review_event.outcome is not None:
            outcome = review_event.outcome
        else:
            _emit(review_event.name, review_event.data)

    if outcome is None or capture.operation_id is None:
        raise RuntimeError("creation review completed without a persistable outcome")

    metadata = creation_review_metadata(outcome)
    version = await finalize_deferred_writer_run(
        session,
        capture,
        outcome.final_content,
        state["expected_lock_version"],
        output_metadata=metadata,
    )
    try:
        persist_review = state.get("persist_creation_review") or persist_creation_review
        await persist_review(
            session,
            document_id=state["document_id"],
            version_id=version.id,
            operation_id=capture.operation_id,
            outcome=outcome,
        )
    except Exception as audit_error:  # ancillary audit must not fail the run
        await session.rollback()
        logger.warning("Creation review score persistence failed: %s", audit_error)

    document = await DocumentService(session).get_document_state(state["document_id"])
    payload = {
        **document.model_dump(mode="json", by_alias=True),
        "creationReview": metadata["creationReview"],
    }
    _emit("document.completed", payload)
    return {
        "final_output": outcome.final_content,
        "document_state": payload,
    }


async def inline_refine_document_node(state: WriterState) -> dict:
    session = state["session"]
    async for delta in state["refine_workflow"](
        session=session,
        document_id=state["document_id"],
        selection=state["selection"],
        instruction=_with_memory_preferences(state.get("instruction"), state) or "",
        expected_lock_version=state["expected_lock_version"],
    ):
        _emit("document.delta", {"delta": delta})
    document = await DocumentService(session).get_document_state(state["document_id"])
    payload = document.model_dump(mode="json", by_alias=True)
    _emit("document.completed", payload)
    return {"final_output": payload.get("currentContent"), "document_state": payload}


async def rewrite_document_node(state: WriterState) -> dict:
    session = state["session"]
    async for delta in state["rewrite_workflow"](
        session=session,
        document_id=state["document_id"],
        instruction=state.get("instruction") or "",
        expected_lock_version=state["expected_lock_version"],
        platform=state.get("platform"),
        style_rules=_with_memory_preferences(state.get("style_rules"), state),
        word_count=state.get("word_count", 1000),
        extra_context=_with_writing_context(state),
        writing_settings=state.get("writing_settings"),
    ):
        _emit("document.delta", {"delta": delta})
    document = await DocumentService(session).get_document_state(state["document_id"])
    payload = document.model_dump(mode="json", by_alias=True)
    _emit("document.completed", payload)
    return {"final_output": payload.get("currentContent"), "document_state": payload}


__all__ = [
    "creation_review_metadata",
    "generate_document_node",
    "inline_refine_document_node",
    "rewrite_document_node",
    "route_writer_operation",
]
