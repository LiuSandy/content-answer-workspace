from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import delete

from app.modules.memory.application.manage_memory import retrieve_memories
from app.modules.memory.adapters.db.models import UserMemoryModel


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_MEMORY_DB_TESTS") != "1",
    reason="set RUN_MEMORY_DB_TESTS=1 to run PostgreSQL pgvector tests",
)


class _QueryEmbedder:
    dimensions = 1536

    async def embed(self, texts: list[str]) -> list[list[float]]:
        vector = [0.0] * self.dimensions
        vector[0] = 1.0
        return [vector.copy() for _ in texts]


@pytest.mark.asyncio
async def test_memory_cosine_top_k_respects_workspace_and_status(monkeypatch):
    from app.platform.database.session import get_session_factory

    factory = get_session_factory()
    workspace_id = f"memory-vector-test-{uuid.uuid4()}"
    other_workspace = f"{workspace_id}-other"

    def vector(first: float, second: float) -> list[float]:
        value = [0.0] * 1536
        value[0] = first
        value[1] = second
        return value

    async with factory() as session:
        session.add_all(
            [
                UserMemoryModel(
                    workspace_id=workspace_id,
                    memory_type="explicit",
                    content="closest",
                    status="active",
                    embedding=vector(1.0, 0.0),
                ),
                UserMemoryModel(
                    workspace_id=workspace_id,
                    memory_type="explicit",
                    content="second",
                    status="active",
                    embedding=vector(0.8, 0.6),
                ),
                UserMemoryModel(
                    workspace_id=workspace_id,
                    memory_type="explicit",
                    content="rejected-closest",
                    status="rejected",
                    embedding=vector(1.0, 0.0),
                ),
                UserMemoryModel(
                    workspace_id=other_workspace,
                    memory_type="explicit",
                    content="other-workspace",
                    status="active",
                    embedding=vector(1.0, 0.0),
                ),
            ]
        )
        await session.commit()

    monkeypatch.setattr(
        "app.modules.memory.application.manage_memory._get_embedding_provider",
        lambda: _QueryEmbedder(),
    )

    try:
        rows = await retrieve_memories("semantic query", workspace_id, top_k=2)
        assert [row.content for row in rows] == ["closest", "second"]
        assert rows[0].rank_score == pytest.approx(1.0)
        assert rows[1].rank_score == pytest.approx(0.8)
    finally:
        async with factory() as session:
            await session.execute(
                delete(UserMemoryModel).where(
                    UserMemoryModel.workspace_id.in_([workspace_id, other_workspace])
                )
            )
            await session.commit()
