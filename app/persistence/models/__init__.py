"""持久化模型包；统一导入所有 ORM 模型，确保 Alembic autogenerate 可以发现所有表。"""
from __future__ import annotations

from .chats import Chat, Message
from .content import ChatSourceItem, CollectionRun, SourceItem
from .documents import AIOperation, AnswerDocument, AnswerVersion
from .settings import AppSettings

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
]
