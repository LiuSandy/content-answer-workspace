"""结构化输出公共底座测试（roadmap R1）。

覆盖：profile 能力选择、Pydantic 校验、一次重试、JSON mode 降级、
通用解析降级、StructuredResult 元数据可审计、五类公共 schema 可导入、
DeepSeek profile 不错误假定原生 json_schema。
"""
from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from app.application.agent.adapters import DeepSeekLLMAdapter
from app.domain.dto import (
    ConversationSummary,
    IntentRoute,
    LLMRequest,
    MemoryExtraction,
    QualityReport,
    StructuredResult,
    TopicEvaluation,
)
from app.infrastructure.llm.structured import generate_structured


def _quality_dimension_scores(score: int = 80) -> dict[str, int]:
    return {
        "relevance": score,
        "information_density": score,
        "readability": score,
        "logic_coherence": score,
        "word_count_compliance": score,
    }


class _Resp:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeProvider:
    """顺序返回内容的 fake provider；耗尽后返回空串。"""

    def __init__(self, contents: list[str]) -> None:
        self._contents = list(contents)
        self.calls: list[LLMRequest | object] = []

    async def generate(self, request: object) -> _Resp:
        self.calls.append(request)
        content = self._contents.pop(0) if self._contents else ""
        return _Resp(content)


class _RejectingProvider:
    """拒绝任何 response_format 的 fake provider；模拟不兼容端点。

    json_mode/json_schema 调用直接抛错，仅无格式调用（通用解析）返回内容。
    """

    def __init__(self, content: str) -> None:
        self.content = content
        self.calls: list[object] = []

    async def generate(self, request: object) -> _Resp:
        fmt = getattr(request, "response_format", None)
        self.calls.append(request)
        if fmt:
            raise RuntimeError("endpoint rejects json response_format")
        return _Resp(self.content)


def _request() -> LLMRequest:
    return LLMRequest(
        messages=[
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "user"},
        ],
        model="deepseek-v4-pro",
        temperature=0.1,
        max_tokens=1024,
    )


# ── profile 能力选择 ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_json_schema_priority_when_declared():
    """profile 声明 json_schema 时优先使用 json_schema。"""
    provider = _FakeProvider(['{"intent": "chat", "knowledge_mode": "off"}'])
    result = await generate_structured(
        provider=provider,
        request=_request(),
        schema=IntentRoute,
        structured_methods=["json_schema", "json_mode", "generic_parse"],
    )
    assert result.method_used == "json_schema"
    assert result.attempts == 1
    assert result.value is not None
    assert result.value.intent == "chat"
    assert result.value.knowledge_mode == "off"
    # json_schema 方法应携带 response_format
    assert provider.calls[0].response_format == {
        "type": "json_schema",
        "json_schema": {
            "name": "IntentRoute",
            "strict": True,
            "schema": IntentRoute.model_json_schema(),
        },
    }


@pytest.mark.asyncio
async def test_json_mode_start_without_json_schema_capability():
    """未声明 json_schema 的 profile 直接从 json_mode 开始，不做异常探测。"""
    provider = _FakeProvider(['{"intent": "chat", "knowledge_mode": "off"}'])
    result = await generate_structured(
        provider=provider,
        request=_request(),
        schema=IntentRoute,
        structured_methods=["json_mode", "generic_parse"],
    )
    assert result.method_used == "json_mode"
    assert result.attempts == 1
    assert provider.calls[0].response_format == {"type": "json_object"}


@pytest.mark.asyncio
async def test_default_methods_when_profile_silent():
    """profile 未声明 structured_methods 时使用保守默认（json_mode → generic_parse）。"""
    provider = _FakeProvider(['{"intent": "chat", "knowledge_mode": "normal"}'])
    result = await generate_structured(provider=provider, request=_request(), schema=IntentRoute)
    assert result.method_used == "json_mode"
    assert result.attempts == 1


# ── Pydantic 校验 ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_validation_failure_degrades_to_json_mode():
    """json_schema 返回 JSON 但校验失败 → 重试后降级到 json_mode。"""
    provider = _FakeProvider([
        '{"intent": "unknown_intent_value", "knowledge_mode": "off"}',
        '{"intent": "unknown_intent_value", "knowledge_mode": "off"}',
        '{"intent": "chat", "knowledge_mode": "off"}',
    ])
    result = await generate_structured(
        provider=provider,
        request=_request(),
        schema=IntentRoute,
        structured_methods=["json_schema", "json_mode", "generic_parse"],
    )
    assert result.method_used == "json_mode"
    assert result.attempts == 3
    assert result.value is not None
    assert result.value.intent == "chat"
    assert result.degradation_reason is not None
    assert "json_schema" in result.degradation_reason


# ── 一次重试 ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_one_retry_before_degrade():
    """同一方法内失败重试一次后成功；attempts=2。"""
    provider = _FakeProvider([
        "这不是JSON",
        '{"intent": "task_plan", "knowledge_mode": "normal"}',
    ])
    result = await generate_structured(
        provider=provider,
        request=_request(),
        schema=IntentRoute,
        structured_methods=["json_mode"],
    )
    assert result.method_used == "json_mode"
    assert result.attempts == 2
    assert result.value is not None
    assert result.value.intent == "task_plan"


# ── 通用解析降级 ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_generic_parse_degrades_when_endpoint_rejects_json_mode():
    """端点拒绝 json_object → 重试后降级到通用解析，从杂质文本中恢复 JSON。"""
    provider = _RejectingProvider(
        "好的，结果如下：\n```json\n{\"intent\": \"chat\", \"knowledge_mode\": \"off\"}\n```\n请查收。"
    )
    result = await generate_structured(
        provider=provider,
        request=_request(),
        schema=IntentRoute,
        structured_methods=["json_mode", "generic_parse"],
    )
    assert result.method_used == "generic_parse"
    assert result.attempts == 3
    assert result.value is not None
    assert result.value.intent == "chat"
    assert result.value.knowledge_mode == "off"
    assert result.degradation_reason is not None
    assert "json_mode" in result.degradation_reason


@pytest.mark.asyncio
async def test_all_methods_fail_returns_none_value_without_raise():
    """全部方法失败不抛异常，返回 value=None 的 StructuredResult 供调用方兜底。"""
    provider = _FakeProvider(["完全无法解析", "完全无法解析", "完全无法解析", "完全无法解析"])
    result = await generate_structured(
        provider=provider,
        request=_request(),
        schema=IntentRoute,
        structured_methods=["json_schema", "json_mode", "generic_parse"],
    )
    assert result.value is None
    assert result.method_used == "generic_parse"
    assert result.attempts == 6  # 3 方法 × (1 retry + 1)
    assert result.degradation_reason


# ── StructuredResult 元数据可审计 ───────────────────────────────────────

@pytest.mark.asyncio
async def test_structured_result_metadata_serializable_for_audit():
    """降级元数据可序列化，供调用方审计到 AIOperation.model_parameters。"""
    provider = _FakeProvider([
        '{"intent": "chat", "knowledge_mode": "off"}',
    ])
    result = await generate_structured(
        provider=provider,
        request=_request(),
        schema=IntentRoute,
        structured_methods=["json_mode", "generic_parse"],
    )
    model_parameters = {
        "structured_method": result.method_used,
        "attempts": result.attempts,
        "degradation_reason": result.degradation_reason,
    }
    assert json.dumps(model_parameters, ensure_ascii=False)
    assert result.value is not None


# ── 五类公共 schema 可导入 ───────────────────────────────────────────────

def test_five_public_schemas_importable():
    route = IntentRoute(intent="chat", knowledge_mode="off", confidence=0.9)
    assert route.platform is None
    assert route.query is None

    report = QualityReport(
        overall_score=88,
        dimension_scores={
            "relevance": 90,
            "information_density": 88,
            "readability": 85,
            "logic_coherence": 87,
            "word_count_compliance": 90,
        },
        issues=[{"text": "开头过长", "fix": "精简引言"}],
        suggestions=["精简引言"],
        summary="整体良好",
    )
    assert report.overall_score == 88

    topic = TopicEvaluation(
        worth_score=75,
        reason="高浏览低回答，蓝海选题",
        competition_level="medium",
        user_match=60,
        suggestion="建议尽快创作",
    )
    assert topic.worth_score == 75

    mem = MemoryExtraction(memory_type="implicit", content="用户偏好简洁风格", confidence=0.8)
    assert mem.memory_type == "implicit"

    summary = ConversationSummary(summary="用户询问 RAG 原理", covered_message_ids=["m1", "m2"])
    assert summary.covered_message_ids == ["m1", "m2"]


def test_quality_report_score_is_0_to_100_integer():
    with pytest.raises(ValidationError):
        QualityReport(overall_score=120, dimension_scores=_quality_dimension_scores())
    with pytest.raises(ValidationError):
        QualityReport(overall_score=-1, dimension_scores=_quality_dimension_scores())
    with pytest.raises(ValidationError):
        QualityReport(overall_score=8.5, dimension_scores=_quality_dimension_scores())
    with pytest.raises(ValidationError):
        QualityReport(overall_score="75", dimension_scores=_quality_dimension_scores())
    with pytest.raises(ValidationError):
        QualityReport(overall_score=True, dimension_scores=_quality_dimension_scores())
    assert (
        QualityReport(
            overall_score=75,
            dimension_scores=_quality_dimension_scores(),
        ).overall_score
        == 75
    )


def test_quality_report_requires_all_five_dimension_scores():
    scores = {
        "relevance": 80,
        "information_density": 80,
        "readability": 80,
        "logic_coherence": 80,
        "word_count_compliance": 80,
    }
    for dimension in scores:
        incomplete = {key: value for key, value in scores.items() if key != dimension}
        with pytest.raises(ValidationError):
            QualityReport(overall_score=80, dimension_scores=incomplete)


@pytest.mark.parametrize("invalid_score", [-1, 101, 80.5, "80", True])
def test_quality_report_dimension_scores_are_bounded_strict_integers(invalid_score):
    scores = {
        "relevance": 80,
        "information_density": 80,
        "readability": 80,
        "logic_coherence": 80,
        "word_count_compliance": 80,
    }
    scores["relevance"] = invalid_score
    with pytest.raises(ValidationError):
        QualityReport(overall_score=80, dimension_scores=scores)


def test_topic_evaluation_fixed_fields():
    topic = TopicEvaluation(
        worth_score=50,
        reason="理由",
        competition_level="high",
        user_match=40,
        suggestion="建议",
    )
    assert topic.competition_level == "high"
    assert topic.user_match == 40
    assert topic.suggestion == "建议"


# ── DeepSeek profile 不假定原生 json_schema（阶段门禁）──────────────────

def test_deepseek_profiles_do_not_assume_native_json_schema():
    import yaml
    from pathlib import Path

    profiles_file = (
        Path(__file__).resolve().parent.parent / "prompts" / "model_profiles.yml"
    )
    raw = yaml.safe_load(profiles_file.read_text(encoding="utf-8"))
    assert "model_profiles" in raw
    for name, entry in raw["model_profiles"].items():
        methods = entry.get("structured_methods") or []
        assert "json_schema" not in methods, (
            f"profile '{name}' 不得声明原生 json_schema（DeepSeek 兼容端点不支持）"
        )


# ── DeepSeekLLMAdapter 公共入口 ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_adapter_generate_structured_returns_metadata(monkeypatch):
    from app.infrastructure.llm.registry import llm_provider_registry

    provider = _FakeProvider([
        "这不是JSON",
        '{"intent": "chat", "knowledge_mode": "off"}',
    ])
    monkeypatch.setattr(llm_provider_registry, "get", lambda key: provider)

    adapter = DeepSeekLLMAdapter()
    result = await adapter.generate_structured(
        schema=IntentRoute,
        system_prompt="sys",
        user_prompt="user",
        retries=1,
    )
    assert result.value is not None
    assert result.value.intent == "chat"
    assert result.method_used == "json_mode"
    assert result.attempts == 2
