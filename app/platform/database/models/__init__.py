"""持久化模型包；统一导入所有 ORM 模型，确保 Alembic autogenerate 可以发现所有表。"""
from __future__ import annotations

from app.modules.conversation.adapters.db.chats import Chat, Message
from app.modules.acquisition.adapters.db.models import ChatSourceItem, CollectionRun, SourceItem
from app.modules.documents.adapters.db.models import AIOperation, AnswerDocument, AnswerVersion
from app.modules.knowledge.adapters.db.models import (
    KnowledgeChunkModel,
    KnowledgeDocumentModel,
    KnowledgeIngestionJobModel,
    KnowledgeIngestionPageModel,
    KnowledgeSourceFileModel,
    RetrievalHitModel,
    RetrievalTraceModel,
)
from app.modules.writing.adapters.db.quality_scores import QualityScoreModel
from app.modules.acquisition.adapters.db.opportunity_models import OpportunityFeedModel, AgentSettingsModel
from app.modules.writing.adapters.db.task_plans import TaskPlanModel, SubTaskModel
from app.modules.memory.adapters.db.models import UserMemoryModel
from app.modules.settings.adapters.db.models import AppSettings
from app.modules.publishing.adapters.db.models import PublishMetricsModel
from app.modules.conversation.adapters.db.summaries import BranchSummary

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
    "KnowledgeSourceFileModel",
    "KnowledgeIngestionJobModel",
    "KnowledgeIngestionPageModel",
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
