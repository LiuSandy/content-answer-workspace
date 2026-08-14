"""R8 TopicAnalyst 测试：评估 pipe、失败降级、重评幂等、配额限制。"""
from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession, create_async_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB

from app.application.topic_analyst_service import TopicAnalystService
from app.persistence import Base
from app.persistence.models.opportunity_feeds import OpportunityFeedModel


@compiles(JSONB, "sqlite")
def _c(type_, compiler, **kw):
    return "TEXT"


async def _make_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession), engine


def _mock_llm(score=85, reason="匹配度高", user_match="适合"):
    llm = MagicMock()
    llm.generate_structured = AsyncMock(
        return_value=json.dumps({"score": score, "reason": reason, "userMatch": user_match})
    )
    return llm


@pytest.mark.asyncio
async def test_evaluate_top_n_scores_opportunities(monkeypatch):
    db, engine = await _make_db()
    async with db() as session:
        for i in range(6):
            session.add(OpportunityFeedModel(
                id=uuid.uuid4(), workspace_id="default", platform="zhihu",
                question_title=f"Q{i}", question_url=f"url{i}",
                opportunity_score=80 - i * 5,
            ))
        await session.commit()

    llm = _mock_llm()
    monkeypatch.setattr(
        "app.application.agent.adapters.DeepSeekLLMAdapter", lambda: llm
    )
    monkeypatch.setattr(
        "app.application.topic_analyst_service.TopicAnalystService._get_active_memories",
        AsyncMock(return_value=[]),
    )

    async with db() as session:
        svc = TopicAnalystService(session)
        count = await svc.evaluate_top_n("default", top_n=3)
        assert count == 3  # 只评估 top 3

        # 再次调用不应重复评估已评估的 3 条，剩余 3 条全评估
        count2 = await svc.evaluate_top_n("default", top_n=5)
        assert count2 == 3

    await engine.dispose()


@pytest.mark.asyncio
async def test_evaluate_failure_preserves_rule_score(monkeypatch):
    db, engine = await _make_db()
    async with db() as session:
        session.add(OpportunityFeedModel(
            id=uuid.uuid4(), workspace_id="default", platform="zhihu",
            question_title="FailQ", question_url="url", opportunity_score=70,
        ))
        await session.commit()

    llm = MagicMock()
    llm.generate_structured = AsyncMock(side_effect=Exception("LLM down"))
    monkeypatch.setattr(
        "app.application.agent.adapters.DeepSeekLLMAdapter", lambda: llm
    )
    monkeypatch.setattr(
        "app.application.topic_analyst_service.TopicAnalystService._get_active_memories",
        AsyncMock(return_value=[]),
    )

    async with db() as session:
        svc = TopicAnalystService(session)
        count = await svc.evaluate_top_n("default")
        assert count == 0  # 评估失败不影响

        from sqlalchemy import select
        row = (await session.execute(
            select(OpportunityFeedModel).where(OpportunityFeedModel.question_title == "FailQ")
        )).scalar_one()
        assert row.llm_evaluated == "false"
        assert row.opportunity_score == 70  # 规则分保留

    await engine.dispose()


@pytest.mark.asyncio
async def test_parse_evaluation():
    """解析成功/失败""" 
    score, reason, match = TopicAnalystService._parse_evaluation(
        '{"score":92,"reason":"高度匹配","userMatch":"你是专家"}'
    )
    assert score == 92
    assert reason == "高度匹配"

    score2, _, _ = TopicAnalystService._parse_evaluation("invalid")
    assert score2 == 50.0
