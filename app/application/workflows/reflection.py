"""反思自评工作流；接收回答内容，LLM 按 spec 4.4 协议输出 5 维结构化评分。

独立于「修正」环节：本模块只负责「评」，调用方根据 overall_score 决定是否
触发定向修正（详见 refinement graph 组装）。每次自评落库一条 QualityScore。
"""
from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from typing import Any

from ...errors import LLMOutputError
from ...persistence.session import get_session_factory

logger = logging.getLogger(__name__)

# spec 4.6：综合评分 < 0.75 自动触发修正，≥ 0.75 视为收敛
REFLECTION_CONVERGE_THRESHOLD = 0.75


@dataclass
class ReflectionResult:
    """一次自评的解析结果。"""

    overall_score: float
    dimensions: dict[str, float]
    weakness_summary: str
    refinement_instruction: str | None
    converged: bool
    raw_json: dict[str, Any]


def _get_reflection_llm():
    """延迟导入避免循环引用；测试时可 monkeypatch 本函数注入 mock。"""
    from app.application.agent.adapters import DeepSeekLLMAdapter
    return DeepSeekLLMAdapter()


REQUIRED_DIMENSIONS = {
    "relevance",
    "information_density",
    "readability",
    "logic_coherence",
    "word_count_compliance",
}


def _parse_score_json(content: str) -> dict[str, Any]:
    """从 LLM 输出中提取并校验评分 JSON；不合法时抛 LLMOutputError。"""
    try:
        if "{" in content:
            json_str = content[content.index("{"): content.rindex("}") + 1]
            data = json.loads(json_str)
        else:
            raise ValueError("No JSON object found in LLM output")
    except (json.JSONDecodeError, ValueError) as e:
        raise LLMOutputError(f"反思评分 JSON 解析失败: {e}") from e

    if not isinstance(data, dict):
        raise LLMOutputError("反思评分输出不是 JSON 对象")

    if "overall_score" not in data:
        raise LLMOutputError("反思评分缺少 overall_score 字段")

    dims = data.get("dimensions", {})
    missing = REQUIRED_DIMENSIONS - set(dims.keys())
    if missing:
        raise LLMOutputError(f"反思评分缺少维度: {', '.join(sorted(missing))}")

    return data


async def reflect(
    content: str,
    document_id: uuid.UUID,
    version_id: uuid.UUID | None,
    iteration: int,
    workspace_id: str = "default",
) -> ReflectionResult:
    """对一篇回答内容执行自评，落库 QualityScore 并返回解析结果。

    Args:
        content: 当前回答完整文本
        document_id: 所属 AnswerDocument ID
        version_id: 评分针对的 AnswerVersion ID（可为 None）
        iteration: 第几轮自评（1-3）
        workspace_id: 隔离用

    Returns:
        ReflectionResult：综合分、五维分、弱点总结、修正指令、是否收敛
    """
    llm = _get_reflection_llm()

    from ...prompts.registry import prompt_registry
    rendered = prompt_registry.render(
        "writing.reflection",
        content=content,
        iteration=iteration,
    )
    messages = rendered.to_llm_request().messages
    system_prompt = messages[0].content if messages else ""
    user_prompt = messages[1].content if len(messages) > 1 else content

    raw_output = await llm.analyze(system_prompt, user_prompt)
    data = _parse_score_json(raw_output)

    overall = float(data["overall_score"])
    if overall < 0.0 or overall > 1.0:
        raise LLMOutputError(f"overall_score 必须在 0~1 之间，实际为 {overall}")

    converged = overall >= REFLECTION_CONVERGE_THRESHOLD
    instruction = data.get("refinement_instruction")
    if converged:
        # 收敛后无需修正，统一置 None
        instruction = None

    result = ReflectionResult(
        overall_score=overall,
        dimensions=dict(data["dimensions"]),
        weakness_summary=data.get("weakness_summary", ""),
        refinement_instruction=instruction,
        converged=converged,
        raw_json=data,
    )

    # 落库
    from ...persistence.models.quality_scores import QualityScoreModel
    factory = get_session_factory()
    async with factory() as session:
        score = QualityScoreModel(
            ai_operation_id=None,
            document_id=document_id,
            version_id=version_id,
            iteration=iteration,
            overall_score=overall,
            dimensions=result.dimensions,
            weakness_summary=result.weakness_summary,
            refinement_instruction=instruction,
            converged="true" if converged else "false",
        )
        session.add(score)
        await session.commit()

    return result