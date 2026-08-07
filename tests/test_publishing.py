"""R10 发布状态与指标测试：draft→ready→published 转换、URL 校验、指标 CRUD。"""
from __future__ import annotations

import uuid

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession, create_async_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB

from app.api.routes.publishing import router
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


def _make_app(sf):
    app = FastAPI()
    app.include_router(router)
    return app


async def _setup(db):
    async with db() as session:
        si = SourceItem(id=uuid.uuid4(), platform="zhihu", external_id="e", url="u", title="T", content="C")
        session.add(si)
        doc = AnswerDocument(id=uuid.uuid4(), source_item_id=si.id, publish_status="draft")
        session.add(doc)
        await session.commit()
        return doc.id


@pytest.mark.asyncio
async def test_draft_to_ready(monkeypatch):
    db, engine = await _make_db()
    monkeypatch.setattr(
        "app.api.routes.publishing.get_session_factory", lambda: db
    )
    did = await _setup(db)
    app = _make_app(db)

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.put(f"/api/publishing/documents/{did}/publish-status",
                           json={"status": "ready"})
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "ready"

        resp2 = await c.get(f"/api/publishing/documents/{did}/publish-status")
        assert resp2.json()["data"]["status"] == "ready"

    await engine.dispose()


@pytest.mark.asyncio
async def test_ready_to_published_with_url(monkeypatch):
    db, engine = await _make_db()
    monkeypatch.setattr(
        "app.api.routes.publishing.get_session_factory", lambda: db
    )
    did = await _setup(db)
    app = _make_app(db)

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        await c.put(f"/api/publishing/documents/{did}/publish-status", json={"status": "ready"})
        resp = await c.put(f"/api/publishing/documents/{did}/publish-status",
                           json={"status": "published", "url": "https://zhihu.com/question/1"})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["status"] == "published"

    await engine.dispose()


@pytest.mark.asyncio
async def test_invalid_transition_rejected(monkeypatch):
    db, engine = await _make_db()
    monkeypatch.setattr(
        "app.api.routes.publishing.get_session_factory", lambda: db
    )
    did = await _setup(db)
    app = _make_app(db)

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.put(f"/api/publishing/documents/{did}/publish-status", json={"status": "published"})
        assert resp.status_code == 400  # draft → published directly rejected

    await engine.dispose()


@pytest.mark.asyncio
async def test_metrics_crud(monkeypatch):
    db, engine = await _make_db()
    monkeypatch.setattr(
        "app.api.routes.publishing.get_session_factory", lambda: db
    )
    did = await _setup(db)
    app = _make_app(db)

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post(f"/api/publishing/documents/{did}/metrics",
                            json={"views": 100, "likes": 10, "label": "发布后1天"})
        assert resp.status_code == 200
        mid = resp.json()["data"]["id"]

        resp2 = await c.get(f"/api/publishing/documents/{did}/metrics")
        assert resp2.status_code == 200
        assert len(resp2.json()["data"]) == 1
        assert resp2.json()["data"][0]["views"] == 100

        resp3 = await c.delete(f"/api/publishing/documents/{did}/metrics/{mid}")
        assert resp3.status_code == 200

    await engine.dispose()
