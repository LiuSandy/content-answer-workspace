"""R6 大纲服务测试：生成/编辑/确认/并发锁与恢复。"""
from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession, create_async_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB

from app.application.outline_service import OutlineService
from app.errors import DocumentConflictError
from app.persistence import Base
from app.persistence.models.content import SourceItem
from app.persistence.models.documents import AnswerDocument


@compiles(JSONB, "sqlite")
def _c(type_, compiler, **kw):
    return "TEXT"


async def _make_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession), engine


async def _setup_doc(db) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    async with db() as session:
        si = SourceItem(
            id=uuid.uuid4(), platform="zhihu", external_id="ext-1",
            url="http://z.com/q1", title="测试问题", content="源材料内容描述",
        )
        session.add(si)
        doc = AnswerDocument(id=uuid.uuid4(), source_item_id=si.id)
        session.add(doc)
        await session.commit()
        return doc.id, si.id, doc.lock_version


def _mock_outline_llm(questions: list | None = None, sections: list | None = None):
    """返回一个 mock llm adapter 用于注入。"""
    llm = MagicMock()
    data = {
        "viewpointQuestions": questions,
        "outline": sections or [
            {"heading": "引言", "keyPoints": ["要点A"], "wordCountEstimate": 150},
            {"heading": "主体", "keyPoints": ["要点B"], "wordCountEstimate": 400},
        ],
    }
    llm.analyze = AsyncMock(return_value=json.dumps(data, ensure_ascii=False))
    return llm


@pytest.mark.asyncio
async def test_generate_produces_viewpoint_and_outline(monkeypatch):
    db, engine = await _make_db()
    doc_id, si_id, lv = await _setup_doc(db)
    fake_llm = _mock_outline_llm(
        questions=["偏好什么风格？"],
        sections=[{"heading":"开场","keyPoints":["h1"],"wordCountEstimate":100}],
    )
    monkeypatch.setattr("app.application.agent.adapters.DeepSeekLLMAdapter", lambda: fake_llm)

    async with db() as session:
        svc = OutlineService(session)
        result = await svc.generate(doc_id, si_id, "default", lv)
        assert result.status == "draft"
        assert result.viewpoint_questions == ["偏好什么风格？"]
        assert len(result.outline) == 1
        assert result.outline[0]["heading"] == "开场"

    await engine.dispose()


@pytest.mark.asyncio
async def test_generate_with_answers_injects_context(monkeypatch):
    db, engine = await _make_db()
    doc_id, si_id, lv = await _setup_doc(db)
    llm = _mock_outline_llm(questions=None)
    monkeypatch.setattr("app.application.agent.adapters.DeepSeekLLMAdapter", lambda: llm)

    async with db() as session:
        svc = OutlineService(session)
        await svc.generate(doc_id, si_id, "default", lv,
                           viewpoint_answers={"Q1": "精炼风格", "Q2": "面向开发者"})
        call_arg = llm.analyze.call_args[0][0] + llm.analyze.call_args[0][1]
        assert "精炼风格" in call_arg
        assert "面向开发者" in call_arg

    await engine.dispose()


@pytest.mark.asyncio
async def test_edit_outline_updates_sections(monkeypatch):
    db, engine = await _make_db()
    doc_id, si_id, lv = await _setup_doc(db)
    fake_llm = _mock_outline_llm()
    monkeypatch.setattr("app.application.agent.adapters.DeepSeekLLMAdapter", lambda: fake_llm)

    async with db() as session:
        svc = OutlineService(session)
        await svc.generate(doc_id, si_id, "default", lv)
        result = await svc.update(doc_id, [
            {"heading": "新标题", "keyPoints": ["p1"], "wordCountEstimate": 200}
        ], viewpoint_answers={"Q": "A"}, expected_lock_version=lv)
        assert result.outline[0]["heading"] == "新标题"

    await engine.dispose()


@pytest.mark.asyncio
async def test_regenerate_replaces_outline(monkeypatch):
    db, engine = await _make_db()
    doc_id, si_id, lv = await _setup_doc(db)
    llm1 = _mock_outline_llm(sections=[{"heading":"旧","keyPoints":[],"wordCountEstimate":50}])
    monkeypatch.setattr("app.application.agent.adapters.DeepSeekLLMAdapter", lambda: llm1)

    async with db() as session:
        svc = OutlineService(session)
        r1 = await svc.generate(doc_id, si_id, "default", lv)
        assert r1.outline[0]["heading"] == "旧"

    llm2 = _mock_outline_llm(sections=[{"heading":"新","keyPoints":[],"wordCountEstimate":50}])
    monkeypatch.setattr("app.application.agent.adapters.DeepSeekLLMAdapter", lambda: llm2)

    async with db() as session:
        svc = OutlineService(session)
        r2 = await svc.regenerate(doc_id, si_id, "default", lv)
        assert r2.outline[0]["heading"] == "新"

    await engine.dispose()


@pytest.mark.asyncio
async def test_confirm_sets_confirmed_and_lock(monkeypatch):
    db, engine = await _make_db()
    doc_id, si_id, lv = await _setup_doc(db)
    llm = _mock_outline_llm()
    monkeypatch.setattr("app.application.agent.adapters.DeepSeekLLMAdapter", lambda: llm)

    async with db() as session:
        svc = OutlineService(session)
        await svc.generate(doc_id, si_id, "default", lv)
        result = await svc.confirm(doc_id, lv)
        assert result.status == "confirmed"

    await engine.dispose()


@pytest.mark.asyncio
async def test_confirm_on_confirmed_raises(monkeypatch):
    db, engine = await _make_db()
    doc_id, si_id, lv = await _setup_doc(db)
    llm = _mock_outline_llm()
    monkeypatch.setattr("app.application.agent.adapters.DeepSeekLLMAdapter", lambda: llm)

    from app.application.outline_service import OutlineError

    async with db() as session:
        svc = OutlineService(session)
        await svc.generate(doc_id, si_id, "default", lv)
        await svc.confirm(doc_id, lv)
        with pytest.raises(OutlineError, match="already confirmed"):
            await svc.confirm(doc_id, lv)

    await engine.dispose()


@pytest.mark.asyncio
async def test_get_current_restores_outline(monkeypatch):
    db, engine = await _make_db()
    doc_id, si_id, lv = await _setup_doc(db)
    llm = _mock_outline_llm(questions=["Q?"])
    monkeypatch.setattr("app.application.agent.adapters.DeepSeekLLMAdapter", lambda: llm)

    async with db() as session:
        svc = OutlineService(session)
        await svc.generate(doc_id, si_id, "default", lv)

    async with db() as session:
        svc = OutlineService(session)
        result = await svc.get_current(doc_id)
        assert result is not None
        assert result.viewpoint_questions == ["Q?"]
        assert len(result.outline) > 0

    await engine.dispose()


@pytest.mark.asyncio
async def test_generate_with_document_lock_conflict(monkeypatch):
    db, engine = await _make_db()
    doc_id, si_id, lv = await _setup_doc(db)
    llm = _mock_outline_llm()
    monkeypatch.setattr("app.application.agent.adapters.DeepSeekLLMAdapter", lambda: llm)

    async with db() as session:
        svc = OutlineService(session)
        with pytest.raises(DocumentConflictError):
            await svc.generate(doc_id, si_id, "default", lv + 99)

    await engine.dispose()
