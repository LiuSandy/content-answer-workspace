"""Agent 运行调度测试（roadmap R2 Step 3）。

覆盖：断线/超时有稳定终态（agent.error）、生成不自动重试、幂等检索最多重试一次、
已持久化部分结果在超时后不丢失。
"""
from __future__ import annotations

import asyncio

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB

from app.application.agent.scheduling import run_agent_stream, retrieve_with_retry
from app.application.chat_service import ChatService
from app.persistence import Base


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(type_, compiler, **kw):
    return "TEXT"


class _SlowGraph:
    """astream_events 超过超时阈值的假图。"""

    def __init__(self) -> None:
        self.calls = 0

    async def astream_events(self, inputs, config, version="v2"):
        self.calls += 1
        await asyncio.sleep(0.2)
        yield {}


class _BoomGraph:
    """首轮即抛错的假图；记录调用次数验证调度层不自动重试。"""

    def __init__(self) -> None:
        self.calls = 0

    async def astream_events(self, inputs, config, version="v2"):
        self.calls += 1
        if False:
            yield {}
        raise RuntimeError("boom")


def _collect(graph, timeout: float):
    async def _run():
        out = []
        async for ev in run_agent_stream(graph, {}, {"configurable": {"thread_id": "t"}}, timeout_seconds=timeout):
            out.append(ev)
        return out

    return asyncio.run(_run())


@pytest.mark.asyncio
async def test_run_agent_timeout_emits_terminal_error():
    """超时进入稳定终态：产出 agent.error（不抛异常、不挂起）。"""
    graph = _SlowGraph()
    events = []
    async for ev in run_agent_stream(graph, {}, {"configurable": {"thread_id": "t"}}, timeout_seconds=0.05):
        events.append(ev)
    assert events[-1][0] == "agent.error"
    assert events[-1][1]["errorCode"] == "agent_timeout"
    assert graph.calls == 1


@pytest.mark.asyncio
async def test_generation_error_not_auto_retried():
    """生成/图执行失败不自动重试：astream_events 只被调用一次。"""
    graph = _BoomGraph()
    with pytest.raises(RuntimeError):
        async for _ in run_agent_stream(graph, {}, {}, timeout_seconds=5):
            pass
    assert graph.calls == 1


@pytest.mark.asyncio
async def test_retrieve_with_retry_succeeds_after_one_failure():
    """幂等检索失败后最多重试一次；第二次成功。"""
    calls = {"n": 0}

    async def flaky():
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("transient")
        return {"ok": True}

    result, error = await retrieve_with_retry(flaky)
    assert result == {"ok": True}
    assert error is None
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_retrieve_with_retry_at_most_two_calls():
    """始终失败时最多调用两次，随后返回失败信息。"""
    calls = {"n": 0}

    async def always_fail():
        calls["n"] += 1
        raise RuntimeError("nope")

    result, error = await retrieve_with_retry(always_fail)
    assert result is None
    assert error is not None
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_timeout_keeps_persisted_partial_results():
    """已持久化的部分结果在超时后不丢失。"""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with factory() as session:
        svc = ChatService(session)
        chat = await svc.create_chat("timeout-chat")
        user_msg = await svc.save_user_message(chat.id, "q")
        partial = await svc.save_assistant_message(
            chat.id, "source_list", "已采集部分结果", payload={"items": []}, parent_message_id=user_msg.id
        )

    graph = _SlowGraph()
    events = []
    async for ev in run_agent_stream(graph, {}, {"configurable": {"thread_id": "t"}}, timeout_seconds=0.05):
        events.append(ev)
    assert events[-1][0] == "agent.error"

    async with factory() as session:
        msgs = await ChatService(session).get_messages(chat.id)
        assert len(msgs) == 2
        assert str(partial.id) in {str(m.id) for m in msgs}

    await engine.dispose()
