"""首次生成自动评审的 API/SSE 与持久化集成测试。"""
from __future__ import annotations

import json
import uuid

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from app.modules.documents.api import router as documents_route
from app.shared.dto import QualityReport
from app.shared.errors import LLMOutputError
from app.platform.database import Base
from app.modules.acquisition.adapters.db.models import SourceItem
from app.modules.documents.adapters.db.models import AIOperation, AnswerDocument, AnswerVersion
from app.modules.writing.adapters.db.quality_scores import QualityScoreModel


@compiles(JSONB, "sqlite")
def _compile_jsonb_for_sqlite(type_, compiler, **kw):
    return "TEXT"


async def _make_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession), engine


async def _setup(db):
    async with db() as session:
        source = SourceItem(
            platform="zhihu",
            external_id=str(uuid.uuid4()),
            url="https://example.test/question",
            title="原始问题",
            content="问题详情",
        )
        session.add(source)
        await session.flush()
        document = AnswerDocument(source_item_id=source.id)
        session.add(document)
        await session.commit()
        return source.id, document.id, document.lock_version


def _report(score: int, instruction: str = "只修复指定问题") -> QualityReport:
    return QualityReport(
        overall_score=score,
        dimension_scores={
            "relevance": score,
            "information_density": score,
            "readability": score,
            "logic_coherence": score,
            "word_count_compliance": score,
        },
        issues=[],
        suggestions=[],
        rewrite_instruction=None if score >= 75 else instruction,
        summary=f"score {score}",
    )


def _events(body: str) -> list[tuple[str, dict]]:
    parsed = []
    for block in body.strip().split("\n\n"):
        lines = block.splitlines()
        name = next(line[7:] for line in lines if line.startswith("event: "))
        data = json.loads(next(line[6:] for line in lines if line.startswith("data: ")))
        parsed.append((name, data))
    return parsed


async def _post_generate(monkeypatch, db, source_id, lock_version, reports, rewrites):
    monkeypatch.setattr(documents_route, "get_session_factory", lambda: db)

    async def fake_generate(*, session, document_id, capture, **kwargs):
        operation = AIOperation(
            document_id=document_id,
            operation_type="generate",
            status="running",
        )
        session.add(operation)
        await session.commit()
        capture.operation_id = operation.id
        capture.document_id = document_id
        capture.content = "draft-1"
        yield "draft-1"

    report_iter = iter(reports)

    async def fake_evaluate(content, context):
        result = next(report_iter)
        if isinstance(result, Exception):
            raise result
        return result

    async def fake_rewrite(content, instruction):
        return rewrites[content]

    monkeypatch.setattr(documents_route, "generate_answer_workflow", fake_generate)
    monkeypatch.setattr(documents_route, "evaluate_content", fake_evaluate, raising=False)
    monkeypatch.setattr(documents_route, "_rewrite_creation_draft", fake_rewrite, raising=False)

    app = FastAPI()
    app.include_router(documents_route.router)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            f"/api/source-items/{source_id}/document/generate",
            json={"expectedLockVersion": lock_version, "wordCount": 800},
        )
    assert response.status_code == 200
    return _events(response.text)


@pytest.mark.asyncio
async def test_generation_reviews_before_single_final_version(monkeypatch):
    db, engine = await _make_db()
    source_id, document_id, lock_version = await _setup(db)

    events = await _post_generate(
        monkeypatch,
        db,
        source_id,
        lock_version,
        reports=[_report(60), _report(82)],
        rewrites={"draft-1": "final draft"},
    )

    assert [name for name, _ in events] == [
        "run.started",
        "document.delta",
        "review.started",
        "review.completed",
        "rewrite.started",
        "review.started",
        "review.completed",
        "document.completed",
        "run.completed",
    ]
    completed = next(data for name, data in events if name == "document.completed")
    assert completed["currentContent"] == "final draft"
    assert completed["creationReview"]["reviewStatus"] == "completed"
    assert completed["creationReview"]["passed"] is True

    async with db() as session:
        versions = (
            await session.execute(
                select(AnswerVersion).where(AnswerVersion.document_id == document_id)
            )
        ).scalars().all()
        scores = (
            await session.execute(
                select(QualityScoreModel).where(
                    QualityScoreModel.document_id == document_id
                )
            )
        ).scalars().all()
        operation = (
            await session.execute(
                select(AIOperation).where(AIOperation.document_id == document_id)
            )
        ).scalar_one()
    assert len(versions) == 1
    assert versions[0].content == "final draft"
    assert [score.overall_score for score in scores] == [60, 82]
    assert {score.ai_operation_id for score in scores} == {operation.id}
    assert {score.version_id for score in scores} == {versions[0].id}
    assert operation.output_metadata["creationReview"]["selectedIteration"] == 2
    await engine.dispose()


@pytest.mark.asyncio
async def test_twenty_failed_rounds_persist_highest_not_latest(monkeypatch):
    db, engine = await _make_db()
    source_id, document_id, lock_version = await _setup(db)
    events = await _post_generate(
        monkeypatch,
        db,
        source_id,
        lock_version,
        reports=[_report(70), _report(74), *[_report(71) for _ in range(18)]],
        rewrites={f"draft-{i}": f"draft-{i + 1}" for i in range(1, 20)},
    )

    completed = next(data for name, data in events if name == "document.completed")
    assert completed["currentContent"] == "draft-2"
    assert completed["creationReview"]["selectedIteration"] == 2
    async with db() as session:
        versions = (
            await session.execute(
                select(AnswerVersion).where(AnswerVersion.document_id == document_id)
            )
        ).scalars().all()
    assert [version.content for version in versions] == ["draft-2"]
    await engine.dispose()


@pytest.mark.asyncio
async def test_review_failure_still_persists_current_draft(monkeypatch):
    db, engine = await _make_db()
    source_id, document_id, lock_version = await _setup(db)
    events = await _post_generate(
        monkeypatch,
        db,
        source_id,
        lock_version,
        reports=[LLMOutputError("bad structured output")],
        rewrites={},
    )

    assert [name for name, _ in events] == [
        "run.started",
        "document.delta",
        "review.started",
        "document.completed",
        "run.completed",
    ]
    completed = next(data for name, data in events if name == "document.completed")
    assert completed["currentContent"] == "draft-1"
    assert completed["creationReview"]["reviewStatus"] == "failed"
    assert completed["creationReview"]["finalReport"] is None
    async with db() as session:
        versions = (
            await session.execute(
                select(AnswerVersion).where(AnswerVersion.document_id == document_id)
            )
        ).scalars().all()
    assert [version.content for version in versions] == ["draft-1"]
    await engine.dispose()


@pytest.mark.asyncio
async def test_unknown_review_error_emits_only_run_failed_after_progress(monkeypatch):
    db, engine = await _make_db()
    source_id, document_id, lock_version = await _setup(db)
    events = await _post_generate(
        monkeypatch,
        db,
        source_id,
        lock_version,
        reports=[RuntimeError("unexpected")],
        rewrites={},
    )

    names = [name for name, _ in events]
    assert names[-1] == "run.failed"
    assert "document.completed" not in names
    assert "run.completed" not in names
    async with db() as session:
        versions = (
            await session.execute(
                select(AnswerVersion).where(AnswerVersion.document_id == document_id)
            )
        ).scalars().all()
        operation = (
            await session.execute(
                select(AIOperation).where(AIOperation.document_id == document_id)
            )
        ).scalar_one()
    assert versions == []
    assert operation.status == "failed"
    await engine.dispose()


@pytest.mark.asyncio
async def test_quality_score_persistence_failure_does_not_fail_completed_run(monkeypatch):
    db, engine = await _make_db()
    source_id, document_id, lock_version = await _setup(db)

    async def fail_quality_score_persistence(*args, **kwargs):
        raise RuntimeError("quality score storage unavailable")

    monkeypatch.setattr(
        documents_route,
        "persist_creation_review",
        fail_quality_score_persistence,
    )
    events = await _post_generate(
        monkeypatch,
        db,
        source_id,
        lock_version,
        reports=[_report(80)],
        rewrites={},
    )

    names = [name for name, _ in events]
    assert names[-2:] == ["document.completed", "run.completed"]
    assert "run.failed" not in names
    completed = next(data for name, data in events if name == "document.completed")
    assert completed["creationReview"]["finalReport"]["overallScore"] == 80
    async with db() as session:
        versions = (
            await session.execute(
                select(AnswerVersion).where(AnswerVersion.document_id == document_id)
            )
        ).scalars().all()
        operation = (
            await session.execute(
                select(AIOperation).where(AIOperation.document_id == document_id)
            )
        ).scalar_one()
    assert len(versions) == 1
    assert versions[0].content == "draft-1"
    assert operation.status == "completed"
    assert operation.output_metadata["creationReview"]["finalReport"]["overallScore"] == 80
    await engine.dispose()
