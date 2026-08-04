"""机会扫描与评分；spec 5.4 评分模型。

复用现有热榜工具（fetch_hotlist + analyze_hotlist），结合 AgentSettings.interest_tags
算领域匹配度，排除已创作过的 SourceItem，结果落库 opportunity_feeds。

机会得分 = hot_score × 0.4 + match_score × 0.35 + competition_score × 0.15
+ recency_score × 0.10
"""
from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from ..persistence.models.opportunity_feeds import (
    AgentSettingsModel,
    OpportunityFeedModel,
)
from ..persistence.models.content import SourceItem

logger = logging.getLogger(__name__)

# spec 5.4 评分权重
W_HOT = 0.40
W_MATCH = 0.35
W_COMPETITION = 0.15
W_RECENCY = 0.10


class OpportunityService:
    def __init__(self, session):
        self.session = session

    async def _get_settings(self, workspace_id: str) -> AgentSettingsModel:
        stmt = select(AgentSettingsModel).where(
            AgentSettingsModel.workspace_id == workspace_id
        )
        settings = (await self.session.execute(stmt)).scalar_one_or_none()
        if settings is None:
            # 默认开启
            settings = AgentSettingsModel(workspace_id=workspace_id)
            self.session.add(settings)
            await self.session.commit()
        return settings

    async def scan_and_persist(self, workspace_id: str = "default") -> int:
        """扫一次热榜，算机会得分，落库新机会；返回新增条数。"""
        settings = await self._get_settings(workspace_id)
        if settings.proactive_sensing_enabled != "true":
            logger.info("Proactive sensing disabled for workspace %s, skip scan", workspace_id)
            return 0

        # 复用现有热榜服务
        try:
            from ..services.hotlist_service import fetch_hotlist
            response = await fetch_hotlist(limit=20)
            hot_items = response.items
        except Exception as e:
            logger.warning("Hotlist fetch failed: %s", e)
            return 0

        # 已创作过的 SourceItem URL 集合（排除）
        created_urls = await self._get_created_urls(workspace_id)

        interest_tags = list(settings.interest_tags or [])

        new_count = 0
        for item in hot_items:
            url = item.url or ""
            if not url or url in created_urls:
                continue

            scores = _compute_scores(item, interest_tags)
            opportunity_score = (
                scores["hot"] * W_HOT
                + scores["match"] * W_MATCH
                + scores["competition"] * W_COMPETITION
                + scores["recency"] * W_RECENCY
            )

            feed = OpportunityFeedModel(
                workspace_id=workspace_id,
                platform=getattr(item, "platform", "zhihu"),
                question_title=item.title or "",
                question_url=url,
                hot_score=scores["hot"],
                match_score=scores["match"],
                competition_score=scores["competition"],
                recency_score=scores["recency"],
                opportunity_score=round(opportunity_score, 4),
                existing_answer_count=getattr(item, "answer_count", 0) or 0,
                raw_metadata=item.model_dump(by_alias=True) if hasattr(item, "model_dump") else {},
            )
            self.session.add(feed)
            new_count += 1

        if new_count:
            await self.session.commit()
        return new_count

    async def _get_created_urls(self, workspace_id: str) -> set[str]:
        stmt = select(SourceItem.url).where(SourceItem.workspace_id == workspace_id)
        rows = (await self.session.execute(stmt)).scalars().all()
        return set(rows)

    async def list_top_opportunities(
        self, workspace_id: str, limit: int = 3
    ) -> list[OpportunityFeedModel]:
        """取今日 top N 机会卡片；按 opportunity_score 降序。"""
        stmt = (
            select(OpportunityFeedModel)
            .where(OpportunityFeedModel.workspace_id == workspace_id)
            .order_by(OpportunityFeedModel.opportunity_score.desc())
            .limit(limit)
        )
        return list((await self.session.execute(stmt)).scalars().all())


def _compute_scores(item: Any, interest_tags: list[str]) -> dict[str, float]:
    """算 hot/match/competition/recency 四维分数，归一化到 0~1。"""
    # 热度：用 answer_count 或 heat 归一化
    raw_hot = getattr(item, "answer_count", 0) or getattr(item, "heat", 0) or 0
    hot_score = min(1.0, math.log1p(raw_hot) / math.log1p(1000))

    # 领域匹配度：title 含兴趣 Tag 的比例
    title = (getattr(item, "title", "") or "").lower()
    if interest_tags:
        matched = sum(1 for tag in interest_tags if tag.lower() in title)
        match_score = matched / len(interest_tags)
    else:
        match_score = 0.5  # 无 Tag 配置时给中等分

    # 竞争程度：现有回答数越少分越高
    answer_count = getattr(item, "answer_count", 0) or 0
    competition_score = max(0.0, 1.0 - answer_count / 50)

    # 时效性：越新分越高（24h 内满分，30 天衰减到 0）
    published = getattr(item, "published_at", None) or getattr(item, "created_at", None)
    recency_score = 0.5
    if published:
        try:
            if isinstance(published, str):
                dt = datetime.fromisoformat(published.replace("Z", "+00:00"))
            else:
                dt = published
            now = datetime.now(timezone.utc)
            age_hours = (now - dt).total_seconds() / 3600
            recency_score = max(0.0, 1.0 - age_hours / (30 * 24))
        except Exception:
            recency_score = 0.5

    return {
        "hot": round(hot_score, 4),
        "match": round(match_score, 4),
        "competition": round(competition_score, 4),
        "recency": round(recency_score, 4),
    }