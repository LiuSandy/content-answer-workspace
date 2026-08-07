"""持久化模型包；统一导入所有 ORM 模型，确保 Alembic autogenerate 可以发现所有表。"""
from __future__ import annotations

from .chats import Chat, Message
from .content import ChatSourceItem, CollectionRun, SourceItem
from .documents import AIOperation, AnswerDocument, AnswerVersion
from .knowledge import (
    KnowledgeChunkModel,
    KnowledgeDocumentModel,
    RetrievalHitModel,
    RetrievalTraceModel,
)
from .quality_scores import QualityScoreModel
from .opportunity_feeds import OpportunityFeedModel, AgentSettingsModel
from .task_plans import TaskPlanModel, SubTaskModel
from .user_memories import UserMemoryModel
from .settings import AppSettings
from .publish_metrics import PublishMetricsModel
from .summaries import BranchSummary

__all__ = [
    "Chat",
    "Message",
    "SourceItem",
    "ChatSourceItem",
    "CollectionRun",
    "AnswerDocument",
    "AnswerVersion",
    "AIOperation",
    "AppSettings",
    "KnowledgeDocumentModel",
    "KnowledgeChunkModel",
    "RetrievalTraceModel",
    "RetrievalHitModel",
    "QualityScoreModel",
    "OpportunityFeedModel",
    "AgentSettingsModel",
    "TaskPlanModel",
    "SubTaskModel",
    "UserMemoryModel",
    "PublishMetricsModel",
    "BranchSummary",
]

