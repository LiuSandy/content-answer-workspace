"""SQLAlchemy persistence adapter for extracted memories."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from app.modules.memory.adapters.db.models import UserMemoryModel

from ...domain.extraction import ExtractedMemory
from ...ports.extraction import MemorySaveResult


class SQLAlchemyMemoryRepository:
    def __init__(self, session_factory: Any) -> None:
        self._session_factory = session_factory

    async def save_extracted(
        self,
        *,
        workspace_id: str,
        source: str,
        memories: list[ExtractedMemory],
        embeddings: list[list[float] | None],
    ) -> MemorySaveResult:
        async with self._session_factory() as session:
            existing = (
                await session.execute(
                    select(UserMemoryModel.id)
                    .where(UserMemoryModel.source == source)
                    .limit(1)
                )
            ).scalar_one_or_none()
            if existing is not None:
                return MemorySaveResult(saved=0, skipped=True)

            for memory, embedding in zip(memories, embeddings, strict=True):
                session.add(
                    UserMemoryModel(
                        workspace_id=workspace_id,
                        memory_type=memory.memory_type,
                        memory_scope=memory.memory_scope,
                        content=memory.content,
                        embedding=embedding,
                        confidence=memory.confidence,
                        status=(
                            "active"
                            if memory.memory_type == "explicit"
                            else "pending_confirmation"
                        ),
                        evidence=memory.evidence,
                        source=source,
                    )
                )
            await session.commit()
        return MemorySaveResult(saved=len(memories))
