"""R4：分支 checkpoint 续跑与摘要隔离测试。

覆盖：首次无 checkpoint 全量重建、续跑只传增量且无消息重复、分支间隔离、
同分支串行、摘要 CAS 旧任务不覆盖新摘要、摘要分支不串扰。
"""
from __future__ import annotations

import uuid
from typing import Annotated, TypedDict

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB

from app.context import branch_thread_id, compose_run_inputs
from app.services.context.summary_updater import SummaryUpdater
from app.infrastructure.database import Base
from app.infrastructure.database.models.chats import Chat, Message
from app.infrastructure.database.models.summaries import BranchSummary

try:
    from langgraph.graph.message import add_messages  # noqa: F401
except Exception:  # noqa: BLE001
    add_messages = None  # type: ignore[assignment]

from langgraph.graph import END, START, StateGraph


class _State(TypedDict):
    messages: Annotated[list, add_messages]  # type: ignore[valid-type]


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(type_, compiler, **kw):
    return "TEXT"


async def _make_db() -> tuple[async_sessionmaker[AsyncSession], object]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession), engine


def _make_graph(checkpointer):
    graph = StateGraph(_State)
    graph.add_node(
        "echo",
        lambda state: {
            "messages": [{"role": "assistant", "content": f"收到：{state['messages'][-1].content}"}]
        },
    )
    graph.add_edge(START, "echo")
    graph.add_edge("echo", END)
    return graph.compile(checkpointer=checkpointer)


async def _build_branch(db, chat_id, n_msgs) -> list[Message]:
    """建立一条线性分支并返回分支消息。"""
    from app.services.chat_service import ChatService

    async with db() as session:
        svc = ChatService(session)
        msgs = []
        parent = None
        for i in range(n_msgs):
            u = await svc.save_user_message(chat_id, f"Q{i}", parent_message_id=parent)
            a = await svc.save_assistant_message(chat_id, "text", f"A{i}", parent_message_id=u.id)
            msgs.append(u)
            msgs.append(a)
            parent = a.id
        return msgs


@pytest.mark.asyncio
async def test_first_run_rebuilds_full_branch():
    """无 checkpoint 时输入包含完整分支历史 + 当前用户消息。"""
    from langgraph.checkpoint.memory import MemorySaver

    db, engine = await _make_db()
    checkpointer = MemorySaver()
    graph = _make_graph(checkpointer)

    async with db() as session:
        chat = Chat(id=uuid.uuid4(), title="t")
        session.add(chat)
        await session.commit()

    msgs = await _build_branch(db, chat.id, 2)
    branch_root = msgs[0].id
    history = [{"role": m.role, "content": m.content or ""} for m in msgs]
    current_id = str(uuid.uuid4())

    inputs, config = await compose_run_inputs(
        graph, str(chat.id), str(branch_root), history, current_id, "Q_new"
    )
    assert inputs["resumed_from_checkpoint"] is False
    assert "knowledge_mode" not in inputs
    assert len(inputs["messages"]) == len(history) + 1
    assert inputs["messages"][-1] == {"role": "user", "content": "Q_new"}
    assert config["configurable"]["thread_id"] == branch_thread_id(str(chat.id), str(branch_root))

    await engine.dispose()


@pytest.mark.asyncio
async def test_continue_passes_incremental_only():
    """已有 checkpoint 的分支续跑只传增量（当前用户消息），不重复注入历史。"""
    from langgraph.checkpoint.memory import MemorySaver

    db, engine = await _make_db()
    checkpointer = MemorySaver()
    graph = _make_graph(checkpointer)

    async with db() as session:
        chat = Chat(id=uuid.uuid4(), title="t")
        session.add(chat)
        await session.commit()

    msgs = await _build_branch(db, chat.id, 1)
    branch_root = str(msgs[0].id)
    history = [{"role": m.role, "content": m.content or ""} for m in msgs]

    # 首轮：全量输入运行一次，生成 checkpoint
    current_id1 = str(uuid.uuid4())
    inputs1, config1 = await compose_run_inputs(
        graph, str(chat.id), branch_root, history, current_id1, "Q1"
    )
    await graph.ainvoke(inputs1, config1)

    # 续跑：只传增量
    current_id2 = str(uuid.uuid4())
    inputs2, config2 = await compose_run_inputs(
        graph, str(chat.id), branch_root, history, current_id2, "Q2"
    )
    assert config2["configurable"]["thread_id"] == config1["configurable"]["thread_id"]
    assert inputs2["resumed_from_checkpoint"] is True
    assert inputs2["messages"] == [{"role": "user", "content": "Q2"}]
    assert "knowledge_mode" not in inputs2

    # 运行后 checkpoint 内消息无重复
    await graph.ainvoke(inputs2, config2)
    snapshot = await graph.aget_state(config2)
    contents = [m.content for m in snapshot.values["messages"]]
    assert len(contents) == len(set(contents))

    await engine.dispose()


@pytest.mark.asyncio
async def test_branch_isolation():
    """不同分支使用不同 thread_id，互不共享 checkpoint。"""
    from langgraph.checkpoint.memory import MemorySaver

    db, engine = await _make_db()
    checkpointer = MemorySaver()
    graph = _make_graph(checkpointer)

    async with db() as session:
        chat = Chat(id=uuid.uuid4(), title="t")
        session.add(chat)
        await session.commit()

    msgs = await _build_branch(db, chat.id, 1)
    history = [{"role": m.role, "content": m.content or ""} for m in msgs]

    root_a = str(msgs[0].id)
    root_b = str(uuid.uuid4())
    _, config_a = await compose_run_inputs(graph, str(chat.id), root_a, history, str(uuid.uuid4()), "Qa")
    _, config_b = await compose_run_inputs(graph, str(chat.id), root_b, history, str(uuid.uuid4()), "Qb")
    assert config_a["configurable"]["thread_id"] != config_b["configurable"]["thread_id"]

    await graph.ainvoke({"messages": [{"role": "user", "content": "qa"}]}, config_a)
    snap_b = await graph.aget_state(config_b)
    assert not (snap_b.values and snap_b.values.get("messages"))

    await engine.dispose()


@pytest.mark.asyncio
async def test_summary_cas_old_task_does_not_override():
    """旧异步任务晚完成：expected_version 过期时被拒绝，不覆盖新摘要。"""
    db, engine = await _make_db()

    async def _summarizer(content: str) -> str:
        return f"摘要({len(content)}字)"

    async with db() as session:
        chat = Chat(id=uuid.uuid4(), title="t")
        session.add(chat)
        await session.commit()
        chat_id = chat.id

    msgs = await _build_branch(db, chat_id, 2)
    root = msgs[0].id

    async with db() as session:
        updater = SummaryUpdater(session, _summarizer)
        r1 = await updater.update_incremental(chat_id, root, msgs[:2], expected_version=0)
        assert r1.stale is False
        assert r1.version == 1

        # 旧任务持有 version 0，但当前已是 1：拒绝
        r_stale = await updater.update_incremental(chat_id, root, msgs[2:], expected_version=0)
        assert r_stale.stale is True

        # 正确版本续传
        r2 = await updater.update_incremental(chat_id, root, msgs[2:], expected_version=1)
        assert r2.stale is False
        assert r2.version == 2

        row = (
            await session.execute(
                select(BranchSummary).where(
                    BranchSummary.chat_id == chat_id,
                    BranchSummary.branch_root_message_id == root,
                )
            )
        ).scalar_one()
        assert row.version == 2

    await engine.dispose()


@pytest.mark.asyncio
async def test_summary_branch_isolation():
    """不同分支的摘要互不串扰。"""
    db, engine = await _make_db()

    async def _summarizer(content: str) -> str:
        return f"S({content[:10]})"

    async with db() as session:
        chat = Chat(id=uuid.uuid4(), title="t")
        session.add(chat)
        await session.commit()
        chat_id = chat.id

    msgs = await _build_branch(db, chat_id, 1)
    root_a = msgs[0].id
    root_b = uuid.uuid4()

    async with db() as session:
        updater = SummaryUpdater(session, _summarizer)
        ra = await updater.update_incremental(chat_id, root_a, msgs, expected_version=0)
        rb = await updater.update_incremental(chat_id, root_b, msgs, expected_version=0)
        assert ra.version == 1
        assert rb.version == 1
        rows = (await session.execute(select(BranchSummary))).scalars().all()
        assert len(rows) == 2
        assert rows[0].covered_message_ids != rows[1].covered_message_ids or rows[0].branch_root_message_id != rows[1].branch_root_message_id

    await engine.dispose()
