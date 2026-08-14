"""R11 发布分析测试：数据不足拒绝、指标聚合、异常值和结构化分析结果。"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession, create_async_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB

from app.application.publish_analyst_service import PublishAnalystService
from app.persistence import Base
from app.persistence.models.content import SourceItem
from app.persistence.models.documents import AnswerDocument
from app.persistence.models.publish_metrics import PublishMetricsModel


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
        si = SourceItem(id=uuid.uuid4(), platform="zhihu", external_id="e", url="u", title="Test", content="C")
        session.add(si)
        doc = AnswerDocument(id=uuid.uuid4(), source_item_id=si.id)
        session.add(doc)
        await session.commit()
        return doc.id


@pytest.mark.asyncio
async def test_insufficient_data_returns_none(monkeypatch):
    db, engine = await _make_db()
    did = await _setup(db)

    async with db() as session:
        for i in range(2):  # 只有 2 个日期
            session.add(PublishMetricsModel(
                document_id=did, views=10, likes=1, recorded_at=None,
            ))
        await session.commit()
        # 重设 recorded_at 为不同日期
        from sqlalchemy import update
        import datetime as _dt
        metrics = (await session.execute(
            select(PublishMetricsModel).where(PublishMetricsModel.document_id == did)
        )).scalars().all()
        metrics[0].recorded_at = _dt.datetime(2026, 1, 1)
        metrics[1].recorded_at = _dt.datetime(2026, 1, 2)
        await session.commit()

    async with db() as session:
        svc = PublishAnalystService(session)
        result = await svc.analyze_document(did)
        assert result is None

    await engine.dispose()


@pytest.mark.asyncio
async def test_sufficient_data_generates_report(monkeypatch):
    from unittest.mock import AsyncMock, MagicMock
    llm = MagicMock()
    llm.analyze = AsyncMock(return_value="表现良好，建议继续深耕该话题。")
    monkeypatch.setattr(
        "app.application.agent.adapters.DeepSeekLLMAdapter", lambda: llm
    )

    db, engine = await _make_db()
    did = await _setup(db)

    async with db() as session:
        for i in range(3):
            session.add(PublishMetricsModel(
                document_id=did, views=100, likes=10,
            ))
        await session.commit()
        import datetime as _dt
        metrics = (await session.execute(
            select(PublishMetricsModel).where(PublishMetricsModel.document_id == did)
        )).scalars().all()
        for i, m in enumerate(metrics):
            m.recorded_at = _dt.datetime(2026, 1, i + 1)
        await session.commit()

    async with db() as session:
        svc = PublishAnalystService(session)
        result = await svc.analyze_document(did)
        assert result is not None
        assert result["totalViews"] == 300
        assert result["engagementRate"] >= 0
        assert "insights" in result
        assert "metricsSnapshot" in result
        assert "generatedAt" in result

    await engine.dispose()


@pytest.mark.asyncio
async def test_llm_failure_still_returns_report(monkeypatch):
    from unittest.mock import AsyncMock, MagicMock
    llm = MagicMock()
    llm.analyze = AsyncMock(side_effect=Exception("LLM down"))
    monkeypatch.setattr(
        "app.application.agent.adapters.DeepSeekLLMAdapter", lambda: llm
    )

    db, engine = await _make_db()
    did = await _setup(db)

    async with db() as session:
        for i in range(3):
            session.add(PublishMetricsModel(document_id=did, views=50, likes=5))
        await session.commit()
        import datetime as _dt
        metrics = (await session.execute(
            select(PublishMetricsModel).where(PublishMetricsModel.document_id == did)
        )).scalars().all()
        for i, m in enumerate(metrics):
            m.recorded_at = _dt.datetime(2026, 1, i + 1)
        await session.commit()

    async with db() as session:
        svc = PublishAnalystService(session)
        result = await svc.analyze_document(did)
        assert result is not None
        assert result["llmAnalyzed"] is False
        assert result["insights"] == "分析暂时不可用"

    await engine.dispose()
