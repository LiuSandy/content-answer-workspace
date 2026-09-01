"""R5 记忆 API 测试：create / confirm / reject / edit / list with status+evidence。"""
from __future__ import annotations

import uuid

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession, create_async_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB

from app.modules.memory.api.router import router
from app.platform.database import Base
from app.modules.memory.adapters.db.models import UserMemoryModel


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(type_, compiler, **kw):
    return "TEXT"


async def _make_db() -> tuple[async_sessionmaker[AsyncSession], object]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession), engine


def _make_app(session_factory) -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    from app.platform.database.session import get_session_factory
    app.state.session_factory = session_factory
    return app


@pytest.fixture
def mock_app():
    """重置全局 factory；测试通过 app.state.session_factory 注入会话工厂。"""
    from unittest.mock import MagicMock
    from app.platform.database import session as sess_mod
    orig = getattr(sess_mod, "get_session_factory", None)
    fake = MagicMock()
    sess_mod.get_session_factory = fake
    yield
    if orig:
        sess_mod.get_session_factory = orig


@pytest.mark.asyncio
async def test_create_memory_returns_active(monkeypatch):
    db, engine = await _make_db()
    monkeypatch.setattr("app.platform.database.session.get_session_factory", lambda: db)
    app = _make_app(db)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post("/api/memories", json={
            "content": "喜欢简短回答",
            "memoryType": "explicit",
            "confidence": 0.9,
            "evidence": "第三轮对话提到",
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["status"] == "active"
        assert data["evidence"] == "第三轮对话提到"
        assert data["content"] == "喜欢简短回答"

    await engine.dispose()


@pytest.mark.asyncio
async def test_confirm_memory(monkeypatch):
    db, engine = await _make_db()
    monkeypatch.setattr("app.platform.database.session.get_session_factory", lambda: db)

    mid = None
    async with db() as session:
        mem = UserMemoryModel(id=uuid.uuid4(), workspace_id="default", memory_type="implicit",
                              content="待确认", status="pending_confirmation")
        session.add(mem)
        await session.commit()
        mid = str(mem.id)

    app = _make_app(db)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post(f"/api/memories/{mid}/confirm")
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "active"

    await engine.dispose()


@pytest.mark.asyncio
async def test_reject_memory(monkeypatch):
    db, engine = await _make_db()
    monkeypatch.setattr("app.platform.database.session.get_session_factory", lambda: db)

    mid = None
    async with db() as session:
        mem = UserMemoryModel(id=uuid.uuid4(), workspace_id="default", memory_type="implicit",
                              content="待确认", status="pending_confirmation")
        session.add(mem)
        await session.commit()
        mid = str(mem.id)

    app = _make_app(db)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post(f"/api/memories/{mid}/reject")
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "rejected"

    await engine.dispose()


@pytest.mark.asyncio
async def test_list_includes_status_and_evidence(monkeypatch):
    db, engine = await _make_db()
    monkeypatch.setattr("app.platform.database.session.get_session_factory", lambda: db)

    async with db() as session:
        mem = UserMemoryModel(id=uuid.uuid4(), workspace_id="default", memory_type="explicit",
                              content="显式", status="active", evidence="来源说明")
        session.add(mem)
        await session.commit()

    app = _make_app(db)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/api/memories?workspaceId=default")
        assert resp.status_code == 200
        items = resp.json()["data"]
        assert len(items) >= 1
        assert "status" in items[0]
        assert "evidence" in items[0]


@pytest.mark.asyncio
async def test_confirm_nonexistent_returns_404(monkeypatch):
    db, engine = await _make_db()
    monkeypatch.setattr("app.platform.database.session.get_session_factory", lambda: db)
    app = _make_app(db)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post(f"/api/memories/{uuid.uuid4()}/confirm")
        assert resp.status_code == 404

    await engine.dispose()
