"""R6 大纲 API 测试：generate / update / regenerate / confirm / get-current。"""
from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession, create_async_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB

from app.api.routes.documents import router
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


def _make_app(session_factory) -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    return app


async def _setup(db, monkeypatch):
    """创建 document + source item，mock LLM + session factory。"""
    monkeypatch.setattr(
        "app.persistence.session.get_session_factory", lambda: db
    )
    async with db() as session:
        si = SourceItem(
            id=uuid.uuid4(), platform="zhihu", external_id="ext",
            url="http://z.com/1", title="Test Q", content="測試內容",
        )
        session.add(si)
        doc = AnswerDocument(id=uuid.uuid4(), source_item_id=si.id)
        session.add(doc)
        await session.commit()
        did, sid, lv = doc.id, si.id, doc.lock_version

    data = {
        "viewpointQuestions": ["你的偏好？"],
        "outline": [
            {"heading": "开头", "keyPoints": ["p1"], "wordCountEstimate": 100},
        ],
    }
    fake_llm = MagicMock()
    fake_llm.analyze = AsyncMock(return_value=json.dumps(data, ensure_ascii=False))
    monkeypatch.setattr(
        "app.application.agent.adapters.DeepSeekLLMAdapter", lambda: fake_llm
    )
    return did, sid, lv


@pytest.mark.asyncio
async def test_generate_outline(monkeypatch):
    db, engine = await _make_db()
    did, sid, lv = await _setup(db, monkeypatch)
    app = _make_app(db)

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post(
            f"/api/documents/{did}/outline/generate",
            json={"sourceItemId": str(sid), "expectedLockVersion": lv},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["status"] == "draft"
        assert data["viewpointQuestions"] == ["你的偏好？"]
        assert len(data["outline"]) == 1

    await engine.dispose()


@pytest.mark.asyncio
async def test_get_current_outline(monkeypatch):
    db, engine = await _make_db()
    did, sid, lv = await _setup(db, monkeypatch)
    app = _make_app(db)

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        await c.post(
            f"/api/documents/{did}/outline/generate",
            json={"sourceItemId": str(sid), "expectedLockVersion": lv},
        )
        resp = await c.get(f"/api/documents/{did}/outline/current")
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "draft"

    await engine.dispose()


@pytest.mark.asyncio
async def test_update_outline(monkeypatch):
    db, engine = await _make_db()
    did, sid, lv = await _setup(db, monkeypatch)
    app = _make_app(db)

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        await c.post(
            f"/api/documents/{did}/outline/generate",
            json={"sourceItemId": str(sid), "expectedLockVersion": lv},
        )
        resp = await c.put(
            f"/api/documents/{did}/outline/update",
            json={
                "sections": [{"heading": "新", "keyPoints": [], "wordCountEstimate": 50}],
                "viewpointAnswers": {"Q": "A"},
                "expectedLockVersion": lv,
            },
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["outline"][0]["heading"] == "新"

    await engine.dispose()


@pytest.mark.asyncio
async def test_confirm_outline(monkeypatch):
    db, engine = await _make_db()
    did, sid, lv = await _setup(db, monkeypatch)
    app = _make_app(db)

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        await c.post(
            f"/api/documents/{did}/outline/generate",
            json={"sourceItemId": str(sid), "expectedLockVersion": lv},
        )
        resp = await c.post(
            f"/api/documents/{did}/outline/confirm",
            json={"expectedLockVersion": lv},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "confirmed"

        # 再次确认返回 409
        resp2 = await c.post(
            f"/api/documents/{did}/outline/confirm",
            json={"expectedLockVersion": lv},
        )
        assert resp2.status_code == 409

    await engine.dispose()


@pytest.mark.asyncio
async def test_generate_lock_conflict(monkeypatch):
    db, engine = await _make_db()
    did, sid, lv = await _setup(db, monkeypatch)
    app = _make_app(db)

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post(
            f"/api/documents/{did}/outline/generate",
            json={"sourceItemId": str(sid), "expectedLockVersion": lv + 99},
        )
        assert resp.status_code == 409

    await engine.dispose()
