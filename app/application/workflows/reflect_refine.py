"""反思-修正循环工作流。

首次生成后调用 `reflect`，评分 < 0.75 调用 LLM 定向修正，再自评，
最多 3 轮；超过强制输出并标记未收敛。

复用现有 `DeepSeekLLMAdapter.refine(instruction, current_answer)` 做定向修正，
不重新设计 LLM 接入层。本工作流不直接写 DB AnswerVersion——版本持久化由
上层 API 路由在循环完成后调用 DocumentService 完成（详见 Task 6 API 集成）。
"""
from __future__ import annotations

import logging
import uuid

from .reflection import reflect, REFLECTION_CONVERGE_THRESHOLD

logger = logging.getLogger(__name__)

# spec 4.6：反思循环最多 3 轮，超过强制输出 + 用户告警
MAX_REFLECTION_ITERATIONS = 3


def _get_refine_llm():
    """延迟导入；测试可 monkeypatch 注入 mock。"""
    from app.application.agent.adapters import DeepSeekLLMAdapter
    return DeepSeekLLMAdapter()


async def reflect_and_refine(
    content: str,
    document_id: uuid.UUID,
    version_id: uuid.UUID | None,
    workspace_id: str = "default",
) -> dict:
    """执行「自评 → 修正 → 再自评」循环。

    Returns:
        dict containing:
        - final_content: 最终回答文本
        - iterations: 实际执行的自评轮次（1-3）
        - converged: 是否达成收敛（评分 ≥ 0.75 或达到 3 轮上限前收敛）
        - scores: 每轮 ReflectionResult
        - forced_message: 若达到上限未收敛，附加提示信息（否则为 None）
    """
    current = content
    scores = []
    converged = False

    for iteration in range(1, MAX_REFLECTION_ITERATIONS + 1):
        result = await reflect(
            content=current,
            document_id=document_id,
            version_id=version_id,
            iteration=iteration,
            workspace_id=workspace_id,
        )
        scores.append(result)

        if result.converged:
            converged = True
            logger.info("反思收敛于第 %d 轮，综合评分 %.2f", iteration, result.overall_score)
            break

        # 未收敛：调用 LLM 定向修正
        if result.refinement_instruction and iteration < MAX_REFLECTION_ITERATIONS:
            llm = _get_refine_llm()
            current = await llm.refine(
                instruction=result.refinement_instruction,
                current_answer=current,
            )
            logger.info("第 %d 轮修正完成，进入下一轮自评", iteration)
        else:
            # 达到上限无修正指令或已是最后一轮 → 强制终止
            break

    forced_message = None
    if not converged:
        forced_message = (
            f"已自评 {MAX_REFLECTION_ITERATIONS} 轮未收敛，"
            f"最终综合评分 {scores[-1].overall_score:.2f}，建议人工校对。"
        )
        logger.warning("反思循环 %d 轮未收敛，强制输出", MAX_REFLECTION_ITERATIONS)

    return {
        "final_content": current,
        "iterations": len(scores),
        "converged": converged,
        "scores": scores,
        "forced_message": forced_message,
    }