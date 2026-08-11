"""R3：质检评审与逐条采纳（QualityService）测试。

覆盖：合法报告、结构化失败、报告写入 output_metadata、来源版本锁定、
单条采纳（version_type=inline_refinement + quality_adopt 回填 result_version_id）、
重复采纳幂等、乐观锁冲突，以及 review/adopt REST API。
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB

from app.application.document_service import DocumentService
from app.application.quality_service import QualityService, ReviewContext, evaluate_content
from app.domain.dto import QualityReport, QualitySuggestion, StructuredResult
from app.errors import DocumentConflictError, LLMOutputError
from app.persistence import Base
from app.persistence.models.content import SourceItem
from app.persistence.models.documents import AIOperation, AnswerDocument, AnswerVersion


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(type_, compiler, **kw):
    return "TEXT"


async def _make_db() -> tuple[async_sessionmaker[AsyncSession], object]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession), engine


async def _make_document(
    db,
    content: str = "这是一个回答内容。",
    versioned: bool = True,
) -> tuple[uuid.UUID, uuid.UUID | None, int]:
    """创建 SourceItem + AnswerDocument，并可选生成一个 initial_generation 版本。"""
    async with db() as session:
        source = SourceItem(title="测试问题", content="测试内容", platform="zhihu", url="https://example.com/q/1")
        session.add(source)
        await session.flush()
        doc_service = DocumentService(session)
        doc = await doc_service.get_or_create_document(source.id)
        if versioned:
            version = await doc_service.create_version(
                document_id=doc.id,
                content=content,
                version_type="initial_generation",
                expected_lock_version=doc.lock_version,
            )
            return doc.id, version.id, doc.lock_version
        return doc.id, None, doc.lock_version


class _FakeLLM:
    """可编程的 mock adapter；generate_structured 返回预置 StructuredResult。"""

    def __init__(self, result: StructuredResult) -> None:
        self._result = result
        self.calls: list[tuple[str, str]] = []

    async def generate_structured(self, schema, system_prompt: str, user_prompt: str, retries: int = 1):
        self.calls.append((system_prompt, user_prompt))
        return self._result


def _sample_report() -> QualityReport:
    return QualityReport(
        overall_score=82,
        dimension_scores={
            "relevance": 90,
            "information_density": 65,
            "readability": 85,
            "logic_coherence": 80,
            "word_count_compliance": 90,
        },
        issues=[{"severity": "major", "description": "信息密度不足"}],
        suggestions=["信息密度需要加强"],
        quality_suggestions=[
            QualitySuggestion(
                id="s1",
                dimension="information_density",
                title="第 2 段补充具体数据",
                reason="论点缺少数据支撑",
                anchor="这是一个回答内容。",
                replacement="这是一个回答内容，2024 年相关用户增长达 300%。",
            ),
            QualitySuggestion(
                id="s2",
                dimension="readability",
                title="拆分过长段落",
                reason="段落过长",
                anchor="",
                replacement="这是拆分后的两个段落。\n\n第二段内容。",
            ),
        ],
        summary="整体尚可，信息密度需要加强",
    )


@pytest.mark.asyncio
async def test_evaluate_content_passes_creation_context(monkeypatch):
    expected = _sample_report().model_copy(
        update={"overall_score": 68, "rewrite_instruction": "补充第二段数据"}
    )
    fake = _FakeLLM(
        StructuredResult(value=expected, method_used="json_schema", attempts=1)
    )
    monkeypatch.setattr("app.application.quality_service._get_llm", lambda: fake)

    report = await evaluate_content(
        "当前草稿",
        ReviewContext(
            question="原始问题",
            style_rules="专业、简洁",
            target_word_count=1000,
            iteration=2,
            previous_review={"overallScore": 68},
        ),
    )

    assert report.overall_score == 68
    assert report.rewrite_instruction == "补充第二段数据"
    rendered_user = fake.calls[0][1]
    assert "原始问题" in rendered_user
    assert "专业、简洁" in rendered_user
    assert "1000" in rendered_user
    assert "2/3" in rendered_user
    assert "68" in rendered_user


def test_quality_report_uses_system_computed_pass_status():
    report = _sample_report().model_copy(
        update={"overall_score": 68, "rewrite_instruction": None}
    )
    assert "passed" not in report.model_dump()
    assert report.overall_score == 68


@pytest.mark.asyncio
async def test_review_writes_report_to_output_metadata(monkeypatch):
    """合法报告：review() 返回报告与 reportId，报告完整写入 quality_review 的 output_metadata。"""
    db, engine = await _make_db()
    doc_id, version_id, _ = await _make_document(db)
    fake = _FakeLLM(StructuredResult(value=_sample_report(), method_used="json_schema", attempts=1))
    monkeypatch.setattr("app.application.quality_service._get_llm", lambda: fake)

    async with db() as session:
        result = await QualityService(session).review(doc_id, version_id=version_id)
        report = result.report
        assert report.overall_score == 82
        assert report.dimension_scores["relevance"] == 90
        assert len(report.quality_suggestions) == 2

        op = await session.get(AIOperation, uuid.UUID(result.report_id))
        assert op is not None
        assert op.operation_type == "quality_review"
        assert op.status == "completed"
        stored = op.output_metadata["report"]
        assert stored["overallScore"] == 82
        assert stored["qualitySuggestions"][0]["id"] == "s1"
        assert stored["qualitySuggestions"][0]["replacement"].startswith("这是一个回答内容，2024")
        assert op.input_metadata["sourceVersionId"] == str(version_id)
        assert "测试问题" in fake.calls[0][1]

    await engine.dispose()


@pytest.mark.asyncio
async def test_review_structured_failure_records_failed_operation(monkeypatch):
    """结构化失败：value=None 时抛 LLMOutputError，并落库一条 failed 的 quality_review。"""
    db, engine = await _make_db()
    doc_id, version_id, _ = await _make_document(db)
    fake = _FakeLLM(
        StructuredResult(value=None, method_used="generic_parse", attempts=3, degradation_reason="json: boom")
    )
    monkeypatch.setattr("app.application.quality_service._get_llm", lambda: fake)

    async with db() as session:
        with pytest.raises(LLMOutputError):
            await QualityService(session).review(doc_id, version_id=version_id)

        ops = (
            (await session.execute(select(AIOperation).where(AIOperation.operation_type == "quality_review")))
            .scalars()
            .all()
        )
        assert len(ops) == 1
        assert ops[0].status == "failed"
        assert ops[0].error_code == "llm_output_error"
        assert "boom" in (ops[0].error_message or "")

    await engine.dispose()


@pytest.mark.asyncio
async def test_adopt_suggestion_creates_inline_refinement_version(monkeypatch):
    """单条采纳：生成 version_type=inline_refinement 新版本，quality_adopt 回填 result_version_id。"""
    db, engine = await _make_db()
    doc_id, version_id, lock = await _make_document(db)
    fake = _FakeLLM(StructuredResult(value=_sample_report(), method_used="json_mode", attempts=1))
    monkeypatch.setattr("app.application.quality_service._get_llm", lambda: fake)

    async with db() as session:
        result = await QualityService(session).review(doc_id, version_id=version_id)
        version = await QualityService(session).adopt_suggestion(
            document_id=doc_id,
            report_id=result.report_id,
            suggestion_id="s1",
            expected_lock_version=lock,
        )
        assert version.version_type == "inline_refinement"
        assert "300%" in version.content

        doc = await session.get(AnswerDocument, doc_id)
        assert doc.current_version_id == version.id
        assert doc.current_content == version.content
        assert doc.lock_version == lock + 1

        ops = (
            (await session.execute(select(AIOperation).where(AIOperation.operation_type == "quality_adopt")))
            .scalars()
            .all()
        )
        assert len(ops) == 1
        assert ops[0].result_version_id == version.id
        assert ops[0].output_metadata["suggestionId"] == "s1"
        assert ops[0].output_metadata["reportId"] == result.report_id

    await engine.dispose()


@pytest.mark.asyncio
async def test_adopt_anchor_replaces_only_matching_fragment(monkeypatch):
    """锚点替换：仅替换匹配的原文片段，不触碰其余内容。"""
    db, engine = await _make_db()
    content = "开头。\n这是一个回答内容。\n结尾。"
    doc_id, version_id, lock = await _make_document(db, content=content)
    fake = _FakeLLM(StructuredResult(value=_sample_report(), method_used="json_mode", attempts=1))
    monkeypatch.setattr("app.application.quality_service._get_llm", lambda: fake)

    async with db() as session:
        result = await QualityService(session).review(doc_id, version_id=version_id)
        version = await QualityService(session).adopt_suggestion(
            document_id=doc_id,
            report_id=result.report_id,
            suggestion_id="s1",
            expected_lock_version=lock,
        )
        assert "开头。" in version.content
        assert "结尾。" in version.content
        assert "300%" in version.content

    await engine.dispose()


@pytest.mark.asyncio
async def test_adopt_missing_anchor_raises(monkeypatch):
    """锚点不存在：报告明确提示原文片段缺失，采纳应报错而非静默替换。"""
    db, engine = await _make_db()
    doc_id, version_id, lock = await _make_document(db, content="完全不同的正文。")
    fake = _FakeLLM(StructuredResult(value=_sample_report(), method_used="json_mode", attempts=1))
    monkeypatch.setattr("app.application.quality_service._get_llm", lambda: fake)

    async with db() as session:
        result = await QualityService(session).review(doc_id, version_id=version_id)
        with pytest.raises(Exception):
            await QualityService(session).adopt_suggestion(
                document_id=doc_id,
                report_id=result.report_id,
                suggestion_id="s1",
                expected_lock_version=lock,
            )

    await engine.dispose()


@pytest.mark.asyncio
async def test_adopt_source_version_lock_rejects_stale_report(monkeypatch):
    """来源版本锁定：报告基于的版本不再是当前版本时，采纳被拒绝。"""
    db, engine = await _make_db()
    doc_id, version_id, lock = await _make_document(db)
    fake = _FakeLLM(StructuredResult(value=_sample_report(), method_used="json_mode", attempts=1))
    monkeypatch.setattr("app.application.quality_service._get_llm", lambda: fake)

    async with db() as session:
        result = await QualityService(session).review(doc_id, version_id=version_id)
        # 用户又创建了一个新版本，报告来源版本已过期
        async with db() as session2:
            doc = await session2.get(AnswerDocument, doc_id)
            await DocumentService(session2).create_version(
                document_id=doc_id,
                content="后续编辑后的新内容",
                version_type="manual_checkpoint",
                expected_lock_version=doc.lock_version,
            )
        with pytest.raises(Exception):
            await QualityService(session).adopt_suggestion(
                document_id=doc_id,
                report_id=result.report_id,
                suggestion_id="s1",
                expected_lock_version=doc.lock_version + 1,
            )

    await engine.dispose()


@pytest.mark.asyncio
async def test_duplicate_adopt_is_idempotent(monkeypatch):
    """重复采纳同一建议：不产生第二个版本，返回既有版本，只落一条 quality_adopt。"""
    db, engine = await _make_db()
    doc_id, version_id, lock = await _make_document(db)
    fake = _FakeLLM(StructuredResult(value=_sample_report(), method_used="json_mode", attempts=1))
    monkeypatch.setattr("app.application.quality_service._get_llm", lambda: fake)

    async with db() as session:
        result = await QualityService(session).review(doc_id, version_id=version_id)
        svc = QualityService(session)
        v1 = await svc.adopt_suggestion(
            document_id=doc_id, report_id=result.report_id, suggestion_id="s1", expected_lock_version=lock
        )
        # 幂等：第二次调用返回同一版本，lock_version 不再自增
        v2 = await svc.adopt_suggestion(
            document_id=doc_id, report_id=result.report_id, suggestion_id="s1", expected_lock_version=lock + 1
        )
        assert v1.id == v2.id

        versions = (await session.execute(select(AnswerVersion))).scalars().all()
        assert len(versions) == 2  # initial_generation + inline_refinement

        ops = (
            (await session.execute(select(AIOperation).where(AIOperation.operation_type == "quality_adopt")))
            .scalars()
            .all()
        )
        assert len(ops) == 1

        doc = await session.get(AnswerDocument, doc_id)
        assert doc.lock_version == lock + 1

    await engine.dispose()


@pytest.mark.asyncio
async def test_adopt_optimistic_lock_conflict(monkeypatch):
    """乐观锁冲突：expected_lock_version 过期时抛 DocumentConflictError（API 返回 409）。"""
    db, engine = await _make_db()
    doc_id, version_id, lock = await _make_document(db)
    fake = _FakeLLM(StructuredResult(value=_sample_report(), method_used="json_mode", attempts=1))
    monkeypatch.setattr("app.application.quality_service._get_llm", lambda: fake)

    async with db() as session:
        result = await QualityService(session).review(doc_id, version_id=version_id)
        with pytest.raises(DocumentConflictError):
            await QualityService(session).adopt_suggestion(
                document_id=doc_id,
                report_id=result.report_id,
                suggestion_id="s1",
                expected_lock_version=lock + 99,
            )

    await engine.dispose()


@pytest.mark.asyncio
async def test_adopt_unknown_suggestion_raises(monkeypatch):
    """采纳不存在的建议 id 时抛错。"""
    db, engine = await _make_db()
    doc_id, version_id, lock = await _make_document(db)
    fake = _FakeLLM(StructuredResult(value=_sample_report(), method_used="json_mode", attempts=1))
    monkeypatch.setattr("app.application.quality_service._get_llm", lambda: fake)

    async with db() as session:
        result = await QualityService(session).review(doc_id, version_id=version_id)
        with pytest.raises(Exception):
            await QualityService(session).adopt_suggestion(
                document_id=doc_id,
                report_id=result.report_id,
                suggestion_id="missing",
                expected_lock_version=lock,
            )

    await engine.dispose()


@pytest.mark.asyncio
async def test_list_quality_scores_returns_reports(monkeypatch):
    """报告可恢复查询：list_quality_scores 返回全部 completed 报告及综合分。"""
    db, engine = await _make_db()
    doc_id, version_id, _ = await _make_document(db)
    fake = _FakeLLM(StructuredResult(value=_sample_report(), method_used="json_mode", attempts=1))
    monkeypatch.setattr("app.application.quality_service._get_llm", lambda: fake)

    async with db() as session:
        svc = QualityService(session)
        await svc.review(doc_id, version_id=version_id)
        await svc.review(doc_id, version_id=version_id)

    async with db() as session:
        rows = await QualityService(session).list_quality_scores(doc_id)
        assert len(rows) == 2
        assert rows[0]["overallScore"] == 82
        assert rows[0]["reportId"]
        # 未采纳前所有建议 adopted=False
        assert rows[0]["suggestions"][0]["adopted"] is False

    await engine.dispose()


@pytest.mark.asyncio
async def test_list_quality_scores_marks_adopted_suggestions(monkeypatch):
    """已采纳的建议在报告列表中标记 adopted=True。"""
    db, engine = await _make_db()
    doc_id, version_id, lock = await _make_document(db)
    fake = _FakeLLM(StructuredResult(value=_sample_report(), method_used="json_mode", attempts=1))
    monkeypatch.setattr("app.application.quality_service._get_llm", lambda: fake)

    async with db() as session:
        result = await QualityService(session).review(doc_id, version_id=version_id)
        await QualityService(session).adopt_suggestion(
            document_id=doc_id,
            report_id=result.report_id,
            suggestion_id="s1",
            expected_lock_version=lock,
        )

    async with db() as session:
        rows = await QualityService(session).list_quality_scores(doc_id)
        by_id = {s["id"]: s["adopted"] for s in rows[0]["suggestions"]}
        assert by_id["s1"] is True
        assert by_id["s2"] is False

    await engine.dispose()


# ── REST API 层 ──────────────────────────────────────────────────────────────


def _make_app(db, monkeypatch) -> FastAPI:
    import app.api.routes.documents as documents_route

    app = FastAPI()
    monkeypatch.setattr(documents_route, "get_db_session", _yield_session(db))
    app.include_router(documents_route.router)
    return app


def _yield_session(db):
    async def _gen():
        async with db() as session:
            yield session

    return _gen


@pytest.mark.asyncio
async def test_review_api_returns_report(monkeypatch):
    """POST /api/documents/{id}/quality/review 返回报告与 reportId。"""
    db, engine = await _make_db()
    doc_id, version_id, _ = await _make_document(db)
    fake = _FakeLLM(StructuredResult(value=_sample_report(), method_used="json_mode", attempts=1))
    monkeypatch.setattr("app.application.quality_service._get_llm", lambda: fake)

    app = _make_app(db, monkeypatch)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(f"/api/documents/{doc_id}/quality/review", json={})
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["ok"] is True
        data = payload["data"]
        assert data["report"]["overallScore"] == 82
        assert data["reportId"]

    await engine.dispose()


@pytest.mark.asyncio
async def test_adopt_api_returns_updated_state(monkeypatch):
    """POST /api/documents/{id}/quality/adopt 采纳后返回文档最新状态。"""
    db, engine = await _make_db()
    doc_id, version_id, lock = await _make_document(db)
    fake = _FakeLLM(StructuredResult(value=_sample_report(), method_used="json_mode", attempts=1))
    monkeypatch.setattr("app.application.quality_service._get_llm", lambda: fake)

    async with db() as session:
        result = await QualityService(session).review(doc_id, version_id=version_id)

    app = _make_app(db, monkeypatch)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            f"/api/documents/{doc_id}/quality/adopt",
            json={"reportId": result.report_id, "suggestionId": "s1", "expectedLockVersion": lock},
        )
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["ok"] is True
        assert payload["data"]["lockVersion"] == lock + 1
        assert "300%" in payload["data"]["currentContent"]

    await engine.dispose()


@pytest.mark.asyncio
async def test_adopt_api_returns_409_on_lock_conflict(monkeypatch):
    """乐观锁冲突时 API 返回 409 document_conflict。"""
    db, engine = await _make_db()
    doc_id, version_id, lock = await _make_document(db)
    fake = _FakeLLM(StructuredResult(value=_sample_report(), method_used="json_mode", attempts=1))
    monkeypatch.setattr("app.application.quality_service._get_llm", lambda: fake)

    async with db() as session:
        result = await QualityService(session).review(doc_id, version_id=version_id)

    app = _make_app(db, monkeypatch)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            f"/api/documents/{doc_id}/quality/adopt",
            json={"reportId": result.report_id, "suggestionId": "s1", "expectedLockVersion": lock + 99},
        )
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "document_conflict"

    await engine.dispose()
