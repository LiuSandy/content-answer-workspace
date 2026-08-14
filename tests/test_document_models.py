"""R0：AIOperation.output_metadata 契约 round-trip 测试。"""
import uuid

import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB

from app.infrastructure.database import Base
from app.infrastructure.database.models.documents import AIOperation


@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(type_, compiler, **kw):
    return "TEXT"


@pytest.mark.asyncio
async def test_ai_operation_output_metadata_roundtrip() -> None:
    """AIOperation.output_metadata 可写入并完整读回（结构化报告应存输出字段）。"""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    report = {
        "scores": {"aiFlavorScore": 72, "hookScore": 88},
        "suggestions": ["开头改为反问句式"],
        "adopted": [],
    }

    async with session_factory() as session:
        op = AIOperation(
            id=uuid.uuid4(),
            operation_type="quality_review",
            status="completed",
            output_metadata=report,
        )
        session.add(op)
        await session.commit()

    async with session_factory() as session:
        from sqlalchemy import select

        row = (
            await session.execute(select(AIOperation).where(AIOperation.operation_type == "quality_review"))
        ).scalar_one()
        assert row.output_metadata == report
        assert row.output_metadata["scores"]["aiFlavorScore"] == 72

    await engine.dispose()


@pytest.mark.asyncio
async def test_ai_operation_output_metadata_optional() -> None:
    """output_metadata 可缺省为 {}，不破坏既有写入。"""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with session_factory() as session:
        op = AIOperation(id=uuid.uuid4(), operation_type="chat", status="completed")
        session.add(op)
        await session.commit()

    async with session_factory() as session:
        from sqlalchemy import select

        row = (await session.execute(select(AIOperation))).scalar_one()
        assert row.output_metadata == {}
        assert row.input_metadata == {}

    await engine.dispose()
