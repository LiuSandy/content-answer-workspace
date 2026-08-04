"""OpportunityFeed + AgentSettings 持久化模型；支撑 Phase 2 主动感知。

- OpportunityFeed：定时扫描热榜产出的内容机会记录，含机会评分与已推送状态
- AgentSettings：用户级主动感知配置（领域 Tag、时间窗口、扫描频率、开关）
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .. import Base


class OpportunityFeedModel(Base):
    """一次内容机会扫描产出的记录；前端「今日机会」卡片的数据源。"""

    __tablename__ = "opportunity_feeds"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[str] = mapped_column(String(100), nullable=False)
    # 来源平台，如 zhihu / xiaohongshu
    platform: Mapped[str] = mapped_column(String(50), nullable=False)
    question_title: Mapped[str] = mapped_column(Text, nullable=False)
    question_url: Mapped[str] = mapped_column(Text, nullable=False)
    # 细分评分（spec 5.4 评分模型）
    hot_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    match_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    competition_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    recency_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    # 最终机会得分 = 加权和
    opportunity_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    # 现有回答数（用于竞争程度评估）
    existing_answer_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # 是否已推送到前端（避免重复推送）
    pushed: Mapped[bool] = mapped_column(String(20), nullable=False, default="false")
    scanned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    # 原始 hotlist 项的 metadata
    raw_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    __table_args__ = (
        Index("ix_opportunity_feeds_workspace_score", "workspace_id", "opportunity_score"),
        Index("ix_opportunity_feeds_pushed", "pushed"),
    )


class AgentSettingsModel(Base):
    """用户级 Agent 配置；主动感知开关、领域 Tag、推送时间窗口。"""

    __tablename__ = "agent_settings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    # 主动感知总开关
    proactive_sensing_enabled: Mapped[bool] = mapped_column(
        String(20), nullable=False, default="true"
    )
    # 感兴趣领域 Tag 列表，如 ["AI", "算法", "个人网站"]
    interest_tags: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    # 推送时间窗口（24h 制），如 {"start": 8, "end": 23}
    push_time_window: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # 扫描间隔小时数，默认 1
    scan_interval_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )