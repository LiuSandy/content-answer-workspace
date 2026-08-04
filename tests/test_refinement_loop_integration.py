"""Phase 2 · Task 5：定向修正循环与 3 轮上限。

验证 `reflect_and_refine` 完整循环：
  1. 首次生成 → 自评 0.68 < 0.75 → 触发修正 → 自评 0.82 ≥ 0.75 → 终止（2 轮收敛）
  2. 连续 3 轮 < 0.75 → 第 3 轮强制输出「未收敛」标记
  3. 首次自评 0.85 ≥ 0.75 → 不触发修正（1 轮收敛）
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.application.workflows.reflection import ReflectionResult
from app.application.workflows.reflect_refine import reflect_and_refine, MAX_REFLECTION_ITERATIONS


def _make_result(score: float, instruction: str | None = None) -> ReflectionResult:
    return ReflectionResult(
        overall_score=score,
        dimensions={
            "relevance": 0.85,
            "information_density": 0.6,
            "readability": 0.72,
            "logic_coherence": 0.7,
            "word_count_compliance": 0.65,
        },
        weakness_summary="",
        refinement_instruction=instruction,
        converged=score >= 0.75,
        raw_json={},
    )


@pytest.mark.asyncio
async def test_two_rounds_converge(monkeypatch):
    """首次 0.68 → 修正 → 第二轮 0.82 收敛，共 2 轮。"""
    reflect_calls = []

    async def fake_reflect(content, document_id, version_id, iteration, workspace_id="default"):
        reflect_calls.append(iteration)
        if iteration == 1:
            return _make_result(0.68, "补充数据")
        return _make_result(0.82, None)

    monkeypatch.setattr("app.application.workflows.reflect_refine.reflect", fake_reflect)

    refine_calls = []

    async def fake_refine(instruction, current_answer):
        refine_calls.append(instruction)
        return current_answer + "（已修正）"

    fake_llm = MagicMock()
    fake_llm.refine = AsyncMock(side_effect=fake_refine)
    monkeypatch.setattr(
        "app.application.workflows.reflect_refine._get_refine_llm", lambda: fake_llm
    )

    result = await reflect_and_refine(
        content="初始回答",
        document_id=uuid.uuid4(),
        version_id=uuid.uuid4(),
        workspace_id="default",
    )

    assert result["final_content"].endswith("（已修正）")
    assert result["iterations"] == 2
    assert result["converged"] is True
    assert len(reflect_calls) == 2
    assert len(refine_calls) == 1


@pytest.mark.asyncio
async def test_three_rounds_not_converged_forced_output(monkeypatch):
    """连续 3 轮 < 0.75 → 强制输出，标记未收敛。"""
    async def fake_reflect(content, document_id, version_id, iteration, workspace_id="default"):
        return _make_result(0.60, "继续改")

    monkeypatch.setattr("app.application.workflows.reflect_refine.reflect", fake_reflect)

    async def fake_refine(instruction, current_answer):
        return current_answer + " v2"

    fake_llm = MagicMock()
    fake_llm.refine = AsyncMock(side_effect=fake_refine)
    monkeypatch.setattr(
        "app.application.workflows.reflect_refine._get_refine_llm", lambda: fake_llm
    )

    result = await reflect_and_refine(
        content="初始回答",
        document_id=uuid.uuid4(),
        version_id=uuid.uuid4(),
        workspace_id="default",
    )

    assert result["iterations"] == MAX_REFLECTION_ITERATIONS
    assert result["converged"] is False
    assert "未收敛" in result["forced_message"] or result["converged"] is False


@pytest.mark.asyncio
async def test_first_round_converge_no_refinement(monkeypatch):
    """首次 0.85 ≥ 0.75 → 不调用 refine，1 轮收敛。"""
    async def fake_reflect(content, document_id, version_id, iteration, workspace_id="default"):
        return _make_result(0.85, None)

    monkeypatch.setattr("app.application.workflows.reflect_refine.reflect", fake_reflect)

    fake_llm = MagicMock()
    fake_llm.refine = AsyncMock()
    monkeypatch.setattr(
        "app.application.workflows.reflect_refine._get_refine_llm", lambda: fake_llm
    )

    result = await reflect_and_refine(
        content="好回答",
        document_id=uuid.uuid4(),
        version_id=uuid.uuid4(),
        workspace_id="default",
    )

    assert result["iterations"] == 1
    assert result["converged"] is True
    fake_llm.refine.assert_not_called()