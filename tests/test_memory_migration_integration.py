from __future__ import annotations

import os
import subprocess
import sys
import uuid

import asyncpg
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        os.getenv("RUN_MEMORY_DB_TESTS") != "1",
        reason="set RUN_MEMORY_DB_TESTS=1 to run PostgreSQL migration tests",
    ),
]


def _connection_settings() -> dict[str, str | int]:
    return {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", "5432")),
        "user": os.getenv("DB_USER", "dev"),
        "password": os.getenv("DB_PASSWORD", "dev"),
    }


@pytest.mark.asyncio
async def test_fresh_database_migrates_memory_vectors_and_uses_hnsw():
    settings = _connection_settings()
    database = f"memory_migration_{uuid.uuid4().hex[:12]}"
    admin = await asyncpg.connect(**settings, database="postgres")
    await admin.execute(f'CREATE DATABASE "{database}"')
    await admin.close()

    url = (
        f"postgresql+asyncpg://{settings['user']}:{settings['password']}@"
        f"{settings['host']}:{settings['port']}/{database}"
    )
    env = os.environ.copy()
    env["DATABASE_URL"] = url
    engine = create_async_engine(url)

    try:
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            capture_output=True,
            text=True,
            env=env,
            cwd=os.getcwd(),
            timeout=120,
        )
        assert result.returncode == 0, result.stderr

        async with engine.begin() as connection:
            revision = await connection.scalar(
                text("SELECT version_num FROM alembic_version")
            )
            assert revision == "20260813_memory_vectors"

            embedding_type = await connection.scalar(
                text(
                    """
                    SELECT format_type(attribute.atttypid, attribute.atttypmod)
                    FROM pg_attribute AS attribute
                    JOIN pg_class AS relation ON relation.oid = attribute.attrelid
                    WHERE relation.relname = 'user_memories'
                      AND attribute.attname = 'embedding'
                      AND attribute.attnum > 0
                    """
                )
            )
            assert embedding_type == "vector(1536)"

            indexes = dict(
                (
                    await connection.execute(
                        text(
                            "SELECT indexname, indexdef FROM pg_indexes "
                            "WHERE tablename = 'user_memories'"
                        )
                    )
                ).all()
            )
            assert "USING hnsw" in indexes["ix_user_memories_embedding_hnsw"]
            assert "vector_cosine_ops" in indexes["ix_user_memories_embedding_hnsw"]
            assert "ix_user_memories_workspace_status" in indexes

            query_vector = [0.0] * 1536
            query_vector[0] = 1.0
            for index in range(120):
                vector = [0.0] * 1536
                vector[index % 8] = 1.0
                await connection.execute(
                    text(
                        """
                        INSERT INTO user_memories (
                            id, workspace_id, memory_type, content, embedding,
                            confidence, status, activation_count
                        ) VALUES (
                            :id, 'explain-test', 'explicit', :content,
                            CAST(:embedding AS vector), 0.8, 'active', 0
                        )
                        """
                    ),
                    {
                        "id": uuid.uuid4(),
                        "content": f"memory-{index}",
                        "embedding": str(vector),
                    },
                )

            await connection.execute(text("SET LOCAL enable_seqscan = off"))
            plan = "\n".join(
                row[0]
                for row in (
                    await connection.execute(
                        text(
                            """
                            EXPLAIN SELECT id
                            FROM user_memories
                            WHERE embedding IS NOT NULL
                            ORDER BY embedding <=> CAST(:query_vec AS vector)
                            LIMIT 5
                            """
                        ),
                        {"query_vec": str(query_vector)},
                    )
                ).all()
            )
            assert "ix_user_memories_embedding_hnsw" in plan
    finally:
        await engine.dispose()
        admin = await asyncpg.connect(**settings, database="postgres")
        try:
            await admin.execute(f'DROP DATABASE IF EXISTS "{database}" WITH (FORCE)')
        finally:
            await admin.close()
