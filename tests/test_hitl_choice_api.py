"""HITL 选择 API 与每 chat 并发锁测试（roadmap R2 Step 1/2）。

覆盖：POST /api/chats/{chat_id}/choices 保存选择消息并以
hitl_selection/hitl_choice.context 恢复续跑（新 thread_id）；校验非法输入；
每 chat 并发最多 1 次；preprocess 不清空续跑选择。
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB

from app.api.routes.chats import router as chats_router
from app.application.agent.scheduling import ChatRuntime
from app.application.chat_service import ChatService
from app.persistence import Base

_RECORDED_RUNS: list[dict] = []


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(type_, compiler, **kw):
    return "TEXT"


class _RecordingGraph:
    """记录每次续跑的 inputs/config；事件流为空；无 checkpoint（返回空状态）。"""

    async def astream_events(self, inputs, config, version="v2"):
        _RECORDED_RUNS.append({"inputs": inputs, "config": config})
        if False:
            yield {}

    async def aget_state(self, config):
        return SimpleNamespace(values=None)


async def _make_db() -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession), engine


def _make_app(session_factory) -> FastAPI:
    app = FastAPI()
    app.state.conversation_graph = _RecordingGraph()
    app.state.chat_runtime = ChatRuntime()
    app.state.session_factory = session_factory
    app.include_router(chats_router)
    return app


def _body(text: str) -> str:
    return text


async def _setup_choice(db, selection_payload: dict | None = None):
    async with db() as session:
        svc = ChatService(session)
        chat = await svc.create_chat("hitl-chat")
        req = await svc.save_user_message(chat.id, "帮我选")
        choice = await svc.save_assistant_message(
            chat.id,
            "choice_request",
            "请选择方案",
            payload=selection_payload or {"choices": ["A", "B"], "context": {}},
            parent_message_id=req.id,
        )
        return chat.id, req.id, choice.id


@pytest.mark.asyncio
async def test_post_choice_restores_from_saved_choice_request():
    """提交选择后：保存 hitl_selection 消息（parent 指向 choice_request），
    并在该分支根 thread 上恢复续跑（roadmap R4：thread_id 以分支根消息 id 结尾）。"""
    db, engine = await _make_db()
    chat_id, req_id, choice_id = await _setup_choice(db)
    _RECORDED_RUNS.clear()

    app = _make_app(db)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            f"/api/chats/{chat_id}/choices",
            json={"messageId": str(choice_id), "selection": "use_found"},
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")

    # 续跑在既有分支根 thread 上恢复（thread_id 以分支根消息 id 结尾）
    assert len(_RECORDED_RUNS) == 1
    run = _RECORDED_RUNS[0]
    assert run["inputs"]["hitl_selection"] == "use_found"
    assert run["inputs"]["hitl_choice"]["context"] == {}
    assert run["config"]["configurable"]["thread_id"] == f"{chat_id}_{req_id}"
    assert run["inputs"]["user_message"] == "use_found"

    # 选择消息已持久化
    async with db() as session:
        msgs = await ChatService(session).get_messages(chat_id)
        sel = [m for m in msgs if m.message_type == "hitl_selection"]
        assert len(sel) == 1
        assert sel[0].content == "use_found"
        assert str(sel[0].parent_message_id) == str(choice_id)

    await engine.dispose()


@pytest.mark.asyncio
async def test_post_choice_rejects_missing_choice_request():
    db, engine = await _make_db()
    chat_id, _, _ = await _setup_choice(db)
    app = _make_app(db)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(f"/api/chats/{chat_id}/choices", json={"messageId": "nope", "selection": "A"})
        assert resp.status_code == 404
        assert resp.json()["error"]

    await engine.dispose()


@pytest.mark.asyncio
async def test_post_choice_rejects_empty_selection():
    db, engine = await _make_db()
    chat_id, _, choice_id = await _setup_choice(db)
    app = _make_app(db)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            f"/api/chats/{chat_id}/choices", json={"messageId": str(choice_id), "selection": "   "}
        )
        assert resp.status_code == 422

    await engine.dispose()


@pytest.mark.asyncio
async def test_duplicate_choice_submission_is_idempotent():
    """同一 choice_request + 同一 selection 重复提交不产生第二次续跑。"""
    db, engine = await _make_db()
    chat_id, _, choice_id = await _setup_choice(db)
    _RECORDED_RUNS.clear()

    app = _make_app(db)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r1 = await client.post(
            f"/api/chats/{chat_id}/choices", json={"messageId": str(choice_id), "selection": "use_found"}
        )
        r2 = await client.post(
            f"/api/chats/{chat_id}/choices", json={"messageId": str(choice_id), "selection": "use_found"}
        )
        assert r1.status_code == 200
        assert r2.status_code == 200

    assert len(_RECORDED_RUNS) == 1

    async with db() as session:
        msgs = await ChatService(session).get_messages(chat_id)
        sel = [m for m in msgs if m.message_type == "hitl_selection"]
        assert len(sel) == 1

    await engine.dispose()


@pytest.mark.asyncio
async def test_per_chat_run_lock_serializes_runs():
    """同一 chat 的第二个运行被拒绝；不同 chat 互不影响；释放后可再获取。"""
    runtime = ChatRuntime()
    assert await runtime.try_acquire("a") is True
    assert await runtime.try_acquire("a") is False
    assert await runtime.try_acquire("b") is True
    runtime.release("a")
    assert await runtime.try_acquire("a") is True
    runtime.release("a")
    runtime.release("b")


@pytest.mark.asyncio
async def test_preprocess_keeps_hitl_selection():
    """续跑轮 preprocess 不清空 hitl_selection，只重置本轮 pending/choice。"""
    from app.application.agent.nodes.preprocess import preprocess_node

    result = await preprocess_node(
        {
            "user_message": "use_found",
            "hitl_selection": "use_found",
            "hitl_pending": True,
            "hitl_choice": {"context": {}},
        }
    )
    assert result["hitl_selection"] == "use_found"
    assert result["hitl_pending"] is False
    assert result["hitl_choice"] is None


@pytest.mark.asyncio
async def test_post_choice_concurrent_run_returns_conflict():
    """同一 chat 已有运行在进行时，新提交返回 409。"""
    db, engine = await _make_db()
    chat_id, _, choice_id = await _setup_choice(db)
    _RECORDED_RUNS.clear()

    app = _make_app(db)
    # 模拟已有运行占用该 chat 的锁
    assert await app.state.chat_runtime.try_acquire(str(chat_id)) is True

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            f"/api/chats/{chat_id}/choices", json={"messageId": str(choice_id), "selection": "use_found"}
        )
        assert resp.status_code == 409
        assert "busy" in resp.json()["error"]["code"]

    assert len(_RECORDED_RUNS) == 0
    await engine.dispose()
