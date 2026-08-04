"""Phase 2 · Task 4：ReflectionNode 自评与评分协议。

验证 `reflect` LLM 解析、QualityScore 落库、非法 JSON 抛 LLMOutputError。
"""
from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.application.workflows.reflection import reflect, ReflectionResult
from app.persistence.models.quality_scores import QualityScoreModel
from app.prompts.registry import warmup as warmup_prompts

# 确保测试中 prompt_registry 已加载 writing.reflection
warmup_prompts(freeze=False)


def _valid_score_json() -> str:
    return json.dumps({
        "overall_score": 0.68,
        "dimensions": {
            "relevance": 0.85,
            "information_density": 0.60,
            "readability": 0.72,
            "logic_coherence": 0.70,
            "word_count_compliance": 0.65,
        },
        "weakness_summary": "信息密度不足，缺少具体数据和案例支撑",
        "refinement_instruction": "在第 2、3 段补充具体数据，删除冗余的过渡句",
    })


@pytest.mark.asyncio
async def test_reflect_parses_valid_json_and_persists(monkeypatch):
    """LLM 返回合法评分 JSON → ReflectionResult 解析正确 + QualityScore 落库。"""
    fake_llm = MagicMock()
    fake_llm.analyze = AsyncMock(return_value=_valid_score_json())
    monkeypatch.setattr(
        "app.application.workflows.reflection._get_reflection_llm", lambda: fake_llm
    )

    captured_scores: list[QualityScoreModel] = []
    fake_session = MagicMock()
    fake_session.add = lambda m: captured_scores.append(m)
    fake_session.commit = AsyncMock()
    fake_session_factory = MagicMock()
    fake_session_factory.return_value.__aenter__ = AsyncMock(return_value=fake_session)
    fake_session_factory.return_value.__aexit__ = AsyncMock(return_value=None)
    monkeypatch.setattr(
        "app.application.workflows.reflection.get_session_factory", lambda: fake_session_factory
    )

    doc_id = uuid.uuid4()
    version_id = uuid.uuid4()

    result = await reflect(
        content="这是测试回答内容",
        document_id=doc_id,
        version_id=version_id,
        iteration=1,
        workspace_id="default",
    )

    assert isinstance(result, ReflectionResult)
    assert result.overall_score == 0.68
    assert result.dimensions["relevance"] == 0.85
    assert "信息密度" in result.weakness_summary
    assert result.refinement_instruction is not None

    assert len(captured_scores) == 1
    score = captured_scores[0]
    assert score.document_id == doc_id
    assert score.version_id == version_id
    assert score.iteration == 1
    assert score.overall_score == 0.68
    assert score.dimensions["information_density"] == 0.60


@pytest.mark.asyncio
async def test_reflect_raises_on_invalid_json(monkeypatch):
    """LLM 返回非法 JSON → 抛 LLMOutputError，不落库。"""
    fake_llm = MagicMock()
    fake_llm.analyze = AsyncMock(return_value="这不是 JSON")
    monkeypatch.setattr(
        "app.application.workflows.reflection._get_reflection_llm", lambda: fake_llm
    )
    fake_session = MagicMock()
    fake_session_factory = MagicMock()
    fake_session_factory.return_value.__aenter__ = AsyncMock(return_value=fake_session)
    fake_session_factory.return_value.__aexit__ = AsyncMock(return_value=None)
    monkeypatch.setattr(
        "app.application.workflows.reflection.get_session_factory", lambda: fake_session_factory
    )

    from app.errors import LLMOutputError
    with pytest.raises(LLMOutputError):
        await reflect(
            content="x",
            document_id=uuid.uuid4(),
            version_id=None,
            iteration=1,
            workspace_id="default",
        )
    fake_session.add.assert_not_called()


@pytest.mark.asyncio
async def test_reflect_high_score_no_refinement_instruction(monkeypatch):
    """综合评分 ≥ 0.75 → refinement_instruction 可以留空（达标不再修正）。"""
    high_score = json.dumps({
        "overall_score": 0.88,
        "dimensions": {
            "relevance": 0.9, "information_density": 0.85,
            "readability": 0.88, "logic_coherence": 0.87,
            "word_count_compliance": 0.9,
        },
        "weakness_summary": "整体良好，无明显短板",
        "refinement_instruction": None,
    })
    fake_llm = MagicMock()
    fake_llm.analyze = AsyncMock(return_value=high_score)
    monkeypatch.setattr(
        "app.application.workflows.reflection._get_reflection_llm", lambda: fake_llm
    )
    monkeypatch.setattr(
        "app.application.workflows.reflection.get_session_factory",
        lambda: _noop_factory(),
    )

    result = await reflect("ok content", uuid.uuid4(), None, 1, "default")
    assert result.overall_score == 0.88
    assert result.refinement_instruction is None
    assert result.converged is True


def _noop_factory():
    fake = MagicMock()
    fake.return_value.__aenter__ = AsyncMock(return_value=MagicMock(add=lambda _m: None, commit=AsyncMock()))
    fake.return_value.__aexit__ = AsyncMock(return_value=None)
    return fake