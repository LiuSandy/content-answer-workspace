"""R9 风格学习测试：版本分析、幂等、AI→AI 跳过。"""
from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession, create_async_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB

from app.modules.memory.application.style_learning import (
    learn_style_from_versions,
    analyze_document_versions,
)
from app.platform.database import Base
from app.modules.documents.adapters.db.models import AnswerDocument, AnswerVersion
from app.modules.acquisition.adapters.db.models import SourceItem


@compiles(JSONB, "sqlite")
def _c(type_, compiler, **kw):
    return "TEXT"


async def _make_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession), engine


async def _setup(db):
    async with db() as session:
        si = SourceItem(id=uuid.uuid4(), platform="zhihu", external_id="x", url="u", title="T", content="C")
        session.add(si)
        doc = AnswerDocument(id=uuid.uuid4(), source_item_id=si.id)
        session.add(doc)
        await session.commit()
        return doc.id


@pytest.mark.asyncio
async def test_learn_style_ai_to_manual(monkeypatch):
    db, engine = await _make_db()
    doc_id = await _setup(db)

    llm = MagicMock()
    llm.analyze = AsyncMock(return_value=json.dumps([
        {"content": "偏好短句", "confidence": 0.85},
    ]))
    monkeypatch.setattr(
        "app.modules.memory.application.style_learning.get_memory_llm",
        lambda: llm,
    )

    async with db() as session:
        v1 = AnswerVersion(id=uuid.uuid4(), document_id=doc_id, version_type="initial_generation",
                            content="AI generated long text.", version_number=1)
        v2 = AnswerVersion(id=uuid.uuid4(), document_id=doc_id, version_type="manual_checkpoint",
                            content="AI generated short text.", version_number=2)
        session.add_all([v1, v2])
        await session.commit()

        count = await learn_style_from_versions(session, (v1, v2), doc_id)
        assert count == 1

    await engine.dispose()


@pytest.mark.asyncio
async def test_ai_to_ai_skipped(monkeypatch):
    db, engine = await _make_db()
    doc_id = await _setup(db)

    async with db() as session:
        v1 = AnswerVersion(id=uuid.uuid4(), document_id=doc_id, version_type="initial_generation",
                            content="AI v1", version_number=1)
        v2 = AnswerVersion(id=uuid.uuid4(), document_id=doc_id, version_type="inline_refinement",
                            content="AI v2", version_number=2)
        session.add_all([v1, v2])
        await session.commit()

        count = await learn_style_from_versions(session, (v1, v2), doc_id)
        assert count == 0  # AI→AI 跳过

    await engine.dispose()


@pytest.mark.asyncio
async def test_idempotent_skip(monkeypatch):
    db, engine = await _make_db()
    doc_id = await _setup(db)

    llm = MagicMock()
    llm.analyze = AsyncMock(return_value=json.dumps([{"content": "风格A"}]))
    monkeypatch.setattr(
        "app.modules.memory.application.style_learning.get_memory_llm",
        lambda: llm,
    )

    async with db() as session:
        v1 = AnswerVersion(id=uuid.uuid4(), document_id=doc_id, version_type="initial_generation",
                            content="orig", version_number=1)
        v2 = AnswerVersion(id=uuid.uuid4(), document_id=doc_id, version_type="manual_checkpoint",
                            content="edited", version_number=2)
        session.add_all([v1, v2])
        await session.commit()

        c1 = await learn_style_from_versions(session, (v1, v2), doc_id)
        assert c1 == 1
        c2 = await learn_style_from_versions(session, (v1, v2), doc_id)
        assert c2 == 0  # 幂等

    await engine.dispose()
