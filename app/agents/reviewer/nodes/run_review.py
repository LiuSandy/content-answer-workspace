from __future__ import annotations

from app.agents.reviewer.state import ReviewerState
from app.services.creation_review_service import run_creation_review
from app.services.llm_service import LLMServiceAdapter
from app.services.quality_service import evaluate_content


async def run_review_node(state: ReviewerState) -> dict:
    """执行现有创作评审循环，把结果或错误留在子图状态中。"""
    try:
        async def rewrite(content: str, instruction: str) -> str:
            return await LLMServiceAdapter().refine(
                instruction=instruction,
                current_answer=content,
            )

        outcome = None
        async for event in run_creation_review(
            initial_content=state.get("draft") or "",
            context=state["review_context"],
            evaluate=evaluate_content,
            rewrite=rewrite,
        ):
            if event.outcome is not None:
                outcome = event.outcome

        if outcome is None:
            raise RuntimeError("创作评审未产生结果")
        return {"review_outcome": outcome, "review_error": None}
    except Exception as error:
        return {"review_outcome": None, "review_error": str(error)}


def route_after_review(state: ReviewerState) -> str:
    return "preserve_draft" if state.get("review_error") else "finalize_review"
