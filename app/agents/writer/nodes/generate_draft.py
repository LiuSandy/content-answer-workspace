from __future__ import annotations

from app.agents.writer.state import WriterState
from app.services.planning_service import _get_planner_llm


async def generate_draft_node(state: WriterState) -> dict:
    """调用现有 LLM 生成初稿，并把异常留在 Writer 子图内。"""
    try:
        llm = _get_planner_llm()
        draft = await llm.analyze(
            "你是写作子 Agent，只产出初稿正文。",
            state["writing_prompt"],
        )
        return {
            "draft": draft,
            "writing_error": None,
            "draft_metadata": {"draft_length": len(draft or "")},
        }
    except Exception as error:
        return {
            "writing_error": str(error),
            "draft_metadata": {},
        }
