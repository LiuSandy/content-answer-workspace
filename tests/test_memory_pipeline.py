"""R5 记忆管线测试：迁移 SQL、提取去重、active-only 检索、编辑重嵌入。

需要 sqlite 来测试业务逻辑；迁移 SQL 部分通过 alembic --sql 离线生成验证。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession, create_async_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB

from app.application.memory_extractor import run_memory_extraction, ExtractionResult
from app.application.memory_service import (
    create_memory,
    confirm_memory,
    reject_memory,
    update_memory_content,
    delete_memory,
    clear_all_memories,
    retrieve_memories,
)
from app.persistence import Base
from app.persistence.models.user_memories import UserMemoryModel


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(type_, compiler, **kw):
    return "TEXT"


async def _make_db() -> tuple[async_sessionmaker[AsyncSession], object]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession), engine


# ── 1. 迁移 SQL（离线生成验证） ──────────────────────────────────────────────────


def _offline_sql() -> str:
    """通过 'alembic upgrade head --sql' 生成针对 PostgreSQL 的迁移 SQL。"""
    env = os.environ.copy()
    env["DATABASE_URL"] = "postgresql+psycopg://dev:dev@localhost:5432/test_db"
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head", "--sql"],
        capture_output=True,
        text=True,
        env=env,
        cwd=os.getcwd(),
    )
    return result.stdout


@pytest.mark.slow
def test_migration_sql_contains_vector_conversion():
    sql = _offline_sql()
    assert "vector(1536)" in sql
    assert "embedding::vector" in sql
    assert "json_array_length(" in sql
    assert "1536" in sql


@pytest.mark.slow
def test_migration_sql_contains_hnsw_index():
    sql = _offline_sql()
    assert "ix_user_memories_embedding_hnsw" in sql
    assert "USING hnsw" in sql  # uppercase in offline SQL


@pytest.mark.slow
def test_migration_sql_contains_status_backfill():
    sql = _offline_sql()
    assert "UPDATE user_memories SET status = 'active'" in sql


@pytest.mark.slow
def test_migration_sql_contains_branch_summaries():
    sql = _offline_sql()
    assert "branch_summaries" in sql


# ── 2. 提取与去重 ──────────────────────────────────────────────────────────────


class _FakeLLM:
    def __init__(self, items: list[dict] | None = None):
        self.analyze = AsyncMock(
            return_value=(
                json.dumps(items)
                if items
                else '[{"memory_type":"explicit","content":"喜欢幽默","confidence":0.9},'
                     '{"memory_type":"implicit","content":"偏好长文","confidence":0.7,"evidence":"用户说过"}]'
            )
        )


class _FakeEmbedder:
    def __init__(self):
        self.embed = AsyncMock(return_value=[[0.1] * 8, [0.2] * 8])


@pytest.mark.asyncio
async def test_extraction_sets_status_per_type(monkeypatch):
    """显式 → active；隐式 → pending_confirmation。"""
    db, engine = await _make_db()

    monkeypatch.setattr(
        "app.application.memory_extractor._get_embedding_provider",
        lambda: _FakeEmbedder(),
    )
    monkeypatch.setattr(
        "app.persistence.session.get_session_factory", lambda: db
    )

    from app.application.memory_extractor import _extract_once
    llm = _FakeLLM()
    embedder = _FakeEmbedder()
    _, saved, _ = await _extract_once(llm, embedder, [{"role":"user","content":"hi"}], "rk-test-1", "default")
    assert len(saved) == 2
    assert saved[0].status == "active"
    assert saved[1].status == "pending_confirmation"
    assert saved[1].evidence == "用户说过"

    await engine.dispose()


@pytest.mark.asyncio
async def test_idempotency_key_prevents_duplicate(monkeypatch):
    """同一 idempotency_key 再次运行不重复落库。"""
    db, engine = await _make_db()
    monkeypatch.setattr(
        "app.application.memory_extractor._get_embedding_provider",
        lambda: _FakeEmbedder(),
    )
    monkeypatch.setattr(
        "app.persistence.session.get_session_factory", lambda: db
    )

    llm = _FakeLLM()
    embedder = _FakeEmbedder()

    from app.application.memory_extractor import _extract_once
    _, saved1, _ = await _extract_once(
        llm, embedder, [{"role":"user","content":"x"}], "run-dedup", "default"
    )
    assert len(saved1) == 2

    _, saved2, skipped = await _extract_once(
        llm, embedder, [{"role":"user","content":"x"}], "run-dedup", "default"
    )
    assert len(saved2) == 0
    assert skipped is True

    await engine.dispose()


@pytest.mark.asyncio
async def test_run_memory_extraction_skips_on_inprocess_dup(monkeypatch):
    """进程内幂等：第一次成功，第二次直接 skipped。"""
    db, engine = await _make_db()
    monkeypatch.setattr(
        "app.application.memory_extractor._get_embedding_provider",
        lambda: _FakeEmbedder(),
    )
    monkeypatch.setattr(
        "app.persistence.session.get_session_factory", lambda: db
    )

    r1 = await run_memory_extraction(
        [{"role":"user","content":"hi"}], "rk-proc", "default",
        llm=_FakeLLM(), embedding_provider=_FakeEmbedder(),
    )
    assert r1.saved > 0
    assert r1.skipped is False

    r2 = await run_memory_extraction(
        [{"role":"user","content":"hi"}], "rk-proc", "default",
        llm=_FakeLLM(), embedding_provider=_FakeEmbedder(),
    )
    assert r2.skipped is True

    await engine.dispose()


# ── 3. active‑only 检索 ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_retrieve_only_returns_active(monkeypatch):
    """pending / rejected 记忆不被注入。"""
    db, engine = await _make_db()
    fake_factory = db
    monkeypatch.setattr(
        "app.persistence.session.get_session_factory", lambda: fake_factory
    )

    async with db() as session:
        active = UserMemoryModel(id=uuid.uuid4(), workspace_id="default", memory_type="explicit",
                                  content="active-mem", status="active")
        pending = UserMemoryModel(id=uuid.uuid4(), workspace_id="default", memory_type="implicit",
                                   content="pending-mem", status="pending_confirmation")
        rejected = UserMemoryModel(id=uuid.uuid4(), workspace_id="default", memory_type="implicit",
                                    content="rejected-mem", status="rejected")
        session.add_all([active, pending, rejected])
        await session.commit()

    snippets = await retrieve_memories("mem", "default", top_k=10)
    contents = {s.content for s in snippets}
    assert "active-mem" in contents
    assert "pending-mem" not in contents
    assert "rejected-mem" not in contents

    await engine.dispose()


# ── 4. 编辑重嵌入 ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_update_memory_content_re_embeds(monkeypatch):
    db, engine = await _make_db()
    monkeypatch.setattr(
        "app.persistence.session.get_session_factory", lambda: db
    )

    memory_id = None
    async with db() as session:
        mem = UserMemoryModel(id=uuid.uuid4(), workspace_id="default", memory_type="explicit",
                              content="旧内容", status="active", embedding=[0.0]*8)
        session.add(mem)
        await session.commit()
        memory_id = str(mem.id)

    fake_embedder = _FakeEmbedder()
    fake_embedder.embed = AsyncMock(return_value=[[0.9]*8])
    monkeypatch.setattr(
        "app.application.memory_service._get_embedding_provider", lambda: fake_embedder
    )

    updated = await update_memory_content(memory_id, "default", "新内容")
    assert updated is not None
    assert updated.content == "新内容"
    assert updated.embedding == [0.9]*8

    fake_embedder.embed.assert_called_once()

    await engine.dispose()


# ── 5. confirm / reject ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_confirm_and_reject_transitions(monkeypatch):
    db, engine = await _make_db()
    monkeypatch.setattr(
        "app.persistence.session.get_session_factory", lambda: db
    )

    async with db() as session:
        mem = UserMemoryModel(id=uuid.uuid4(), workspace_id="default", memory_type="implicit",
                              content="待确认", status="pending_confirmation")
        session.add(mem)
        await session.commit()
        mid = str(mem.id)

    confirmed = await confirm_memory(mid, "default")
    assert confirmed is not None
    assert confirmed.status == "active"

    rejected = await reject_memory(mid, "default")
    assert rejected is not None
    assert rejected.status == "rejected"

    await engine.dispose()
