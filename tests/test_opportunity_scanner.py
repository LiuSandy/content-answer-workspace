"""Phase 2 · Task 8：机会扫描器与评分模型测试。"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.application.opportunity_service import (
    OpportunityService,
    _compute_scores,
    W_HOT,
    W_MATCH,
    W_COMPETITION,
    W_RECENCY,
)


def test_weights_sum_to_one():
    assert abs(W_HOT + W_MATCH + W_COMPETITION + W_RECENCY - 1.0) < 1e-9


def test_compute_scores_high_hot_high_match():
    item = MagicMock()
    item.title = "DeepSeek 大模型最新进展"
    item.answer_count = 500
    item.published_at = None
    item.heat = 0
    tags = ["DeepSeek", "大模型"]

    scores = _compute_scores(item, tags)
    assert 0.0 <= scores["hot"] <= 1.0
    assert 0.0 <= scores["match"] <= 1.0
    assert 0.0 <= scores["competition"] <= 1.0
    assert 0.0 <= scores["recency"] <= 1.0
    # title 含两个 tag → match_score = 1.0
    assert scores["match"] == 1.0


def test_compute_scores_no_tags_gives_mid_match():
    item = MagicMock()
    item.title = "随便一篇文章"
    item.answer_count = 10
    item.published_at = None
    item.heat = 0
    scores = _compute_scores(item, [])
    assert scores["match"] == 0.5


def test_compute_scores_low_competition_when_many_answers():
    item = MagicMock()
    item.title = "x"
    item.answer_count = 45
    item.published_at = None
    item.heat = 0
    scores = _compute_scores(item, [])
    assert scores["competition"] < 0.2


@pytest.mark.asyncio
async def test_scan_and_persist_disabled_settings(monkeypatch):
    """主动感知关闭时，scan 直接返回 0。"""
    fake_session = MagicMock()
    fake_svc = OpportunityService(fake_session)
    fake_settings = MagicMock()
    fake_settings.proactive_sensing_enabled = "false"
    fake_svc._get_settings = AsyncMock(return_value=fake_settings)

    count = await fake_svc.scan_and_persist("default")
    assert count == 0


@pytest.mark.asyncio
async def test_scan_and_persist_excludes_created_urls(monkeypatch):
    """已创作过的 URL 不入新机会列表。"""
    fake_session = MagicMock()
    fake_svc = OpportunityService(fake_session)

    fake_settings = MagicMock()
    fake_settings.proactive_sensing_enabled = "true"
    fake_settings.interest_tags = ["AI"]
    fake_svc._get_settings = AsyncMock(return_value=fake_settings)

    fake_item = MagicMock()
    fake_item.url = "https://zhihu.com/q/created"
    fake_item.title = "AI 问题"
    fake_item.answer_count = 10
    fake_item.platform = "zhihu"
    fake_item.published_at = None
    fake_item.heat = 0
    fake_item.model_dump = MagicMock(return_value={})

    fake_response = MagicMock()
    fake_response.items = [fake_item]
    monkeypatch.setattr(
        "app.services.hotlist_service.fetch_hotlist",
        AsyncMock(return_value=fake_response),
    )

    fake_svc._get_created_urls = AsyncMock(return_value={"https://zhihu.com/q/created"})

    added: list = []
    fake_session.add = MagicMock(side_effect=lambda m: added.append(m))
    fake_session.commit = AsyncMock()

    count = await fake_svc.scan_and_persist("default")
    assert count == 0
    assert added == []  # 排除已创作，不写入