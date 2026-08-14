"""Reviewer Agent 的内容审核流程。"""
from __future__ import annotations

import asyncio

from app.services.llm_service import DeepSeekLLMAdapter
from app.agents.orchestrator.state import MultiAgentState, SubAgentState
from app.services.creation_review_service import run_creation_review
from app.services.quality_service import ReviewContext, evaluate_content


async def review_agent_node(state: MultiAgentState) -> dict:
    """运行统一创作评审循环。"""
    sub = SubAgentState(name="review", status="running")
    state.sub_agent_states["review"] = sub
    sub.started_at = asyncio.get_event_loop().time()

    try:
        async def rewrite(content: str, instruction: str) -> str:
            return await DeepSeekLLMAdapter().refine(instruction=instruction, current_answer=content)

        outcome = None
        async for event in run_creation_review(
            initial_content=state.draft or "",
            context=ReviewContext(
                question=state.plan.goal,
                style_rules=None,
                target_word_count=1000,
                iteration=1,
            ),
            evaluate=evaluate_content,
            rewrite=rewrite,
        ):
            if event.outcome is not None:
                outcome = event.outcome

        if outcome is None:
            raise RuntimeError("创作评审未产生结果")

        state.final_output = outcome.final_content
        state.quality_score = outcome.final_report.overall_score if outcome.final_report else None
        sub.result = {
            "iterations": outcome.iterations,
            "passed": outcome.passed,
            "review_failed": outcome.review_failed,
            "quality_score": state.quality_score,
        }
        sub.status = "done"
    except Exception as error:
        sub.status = "failed"
        sub.error = str(error)
        state.final_output = state.draft
    finally:
        sub.completed_at = asyncio.get_event_loop().time()

    return {"final_output": state.final_output, "sub_agent_states": state.sub_agent_states}
