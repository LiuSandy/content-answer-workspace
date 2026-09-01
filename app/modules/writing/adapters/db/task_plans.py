"""Phase 3 Task 11-15 集中实施：自主规划引擎（数据模型 + PlannerNode + ExecutorGraph + API + 前端）。"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.database import Base


class TaskPlanModel(Base):
    """一次复合创作目标的任务计划；spec 2.4 节。"""

    __tablename__ = "task_plans"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[str] = mapped_column(String(100), nullable=False)
    chat_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    goal: Mapped[str] = mapped_column(Text, nullable=False)
    # pending / running / done / failed
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_task_plans_chat_id", "chat_id"),
        Index("ix_task_plans_workspace_status", "workspace_id", "status"),
    )


class SubTaskModel(Base):
    """子任务；spec 2.4 节，type 为 search/analyze/outline/write/review。"""

    __tablename__ = "sub_tasks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("task_plans.id", ondelete="CASCADE"), nullable=False
    )
    # plan 内的唯一编号，与 depends_on 引用保持一致
    task_id: Mapped[str] = mapped_column(String(50), nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    # 依赖的 task_id 列表
    depends_on: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    # pending / running / done / failed
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    result: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_sub_tasks_plan_status", "plan_id", "status"),
    )
