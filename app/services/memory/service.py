"""长期记忆服务；spec 3.3 节。

MemoryExtractor：Agent 运行结束后从对话中用 LLM 抽取可记忆信息，向量化后落库
MemoryRetriever：Agent 运行开始时从 user_memories 检索相关记忆注入 system prompt
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

from sqlalchemy import select, text

from app.contracts.errors import LLMOutputError
from app.infrastructure.database.models.user_memories import UserMemoryModel

logger = logging.getLogger(__name__)

MemoryType = Literal["explicit", "implicit", "work_pattern"]
# spec 3.6：单次记忆检索耗时 ≤ 200ms
MEMORY_RETRIEVAL_TIMEOUT_MS = 200

VALID_TYPES = {"explicit", "implicit", "work_pattern"}


@dataclass
class MemorySnippet:
    """注入 system prompt 的一段记忆。"""

    id: str
    memory_type: str
    content: str
    confidence: float
    rank_score: float = 0.0


def _memory_vector_search_sql():
    """生产长期记忆 cosine Top-K 查询；参数始终通过 SQLAlchemy 绑定。"""
    return text(
        """
        SELECT id::text AS id, memory_type, content, confidence,
               1 - (embedding <=> CAST(:query_vec AS vector)) AS rank_score
        FROM user_memories
        WHERE workspace_id = :workspace_id
          AND status = 'active'
          AND embedding IS NOT NULL
        ORDER BY embedding <=> CAST(:query_vec AS vector)
        LIMIT :top_k
        """
    )


def _get_memory_llm():
    from app.services.llm_service import LLMServiceAdapter
    return LLMServiceAdapter()


def _get_embedding_provider():
    """复用知识库 Embedding Provider。"""
    from app.infrastructure.embeddings.provider import get_embedding_provider

    return get_embedding_provider()


def _parse_extraction_json(content: str) -> list[dict[str, Any]]:
    """解析 LLM 抽取的记忆条目 JSON 列表。"""
    try:
        if "[" in content:
            json_str = content[content.index("["): content.rindex("]") + 1]
            data = json.loads(json_str)
        elif "{" in content:
            json_str = content[content.index("{"): content.rindex("}") + 1]
            data = [json.loads(json_str)]
        else:
            raise ValueError("No JSON in extraction output")
    except (json.JSONDecodeError, ValueError) as e:
        raise LLMOutputError(f"记忆抽取 JSON 解析失败: {e}") from e

    cleaned = []
    for item in data:
        if not isinstance(item, dict):
            continue
        mt = item.get("memory_type", "explicit")
        if mt not in VALID_TYPES:
            mt = "explicit"
        content_text = (item.get("content") or "").strip()
        if not content_text:
            continue
        cleaned.append({
            "memory_type": mt,
            "content": content_text,
            "confidence": float(item.get("confidence", 0.8)),
            "evidence": item.get("evidence"),
        })
    return cleaned


async def extract_memories(
    messages: list[dict[str, str]],
    session_id: str,
    workspace_id: str = "default",
    idempotency_key: str | None = None,
) -> list[UserMemoryModel]:
    """从本次对话中抽取可记忆信息并落库。

    R5：显式记忆初始 active，隐式/工作习惯初始 pending_confirmation；
    evidence 记录证据来源；idempotency_key（run_id）命中时跳过重复提取。
    """
    from app.prompts.registry import prompt_registry

    rendered = prompt_registry.render("memory.extract", conversation=json.dumps(messages, ensure_ascii=False))
    msg = rendered.to_llm_request().messages
    system_prompt = msg[0].content if msg else ""
    user_prompt = msg[1].content if len(msg) > 1 else ""

    llm = _get_memory_llm()
    raw = await llm.analyze(system_prompt, user_prompt)
    items = _parse_extraction_json(raw)

    # 向量化（批量）
    contents = [it["content"] for it in items]
    embeddings: list[list[float] | None] = [None] * len(items)
    if contents:
        try:
            provider = _get_embedding_provider()
            vecs = await provider.embed(contents)
            from app.infrastructure.embeddings.provider import validate_embeddings
            validate_embeddings(contents, vecs, provider.dimensions)
            embeddings = [list(v) for v in vecs]
        except Exception as e:
            logger.warning("Memory embedding failed, will persist without vectors: %s", e)

    from app.infrastructure.database.session import get_session_factory
    factory = get_session_factory()
    saved: list[UserMemoryModel] = []
    async with factory() as session:
        if idempotency_key:
            existing_run = (
                await session.execute(
                    select(UserMemoryModel.id).where(
                        UserMemoryModel.source == f"run:{idempotency_key}"
                    ).limit(1)
                )
            ).scalar_one_or_none()
            if existing_run is not None:
                return saved

        for it, emb in zip(items, embeddings):
            status = "active" if it["memory_type"] == "explicit" else "pending_confirmation"
            mem = UserMemoryModel(
                workspace_id=workspace_id,
                memory_type=it["memory_type"],
                content=it["content"],
                embedding=emb,
                confidence=it["confidence"],
                status=status,
                evidence=it.get("evidence"),
                source=f"run:{idempotency_key}" if idempotency_key else session_id,
            )
            session.add(mem)
            saved.append(mem)
        await session.commit()
    return saved


async def retrieve_memories(
    query: str,
    workspace_id: str = "default",
    top_k: int = 5,
) -> list[MemorySnippet]:
    """优先用 pgvector cosine Top-K 检索 active 记忆，失败时文本降级。

    200ms 预算仅约束数据库召回；远端查询向量化耗时独立于该预算。
    """
    from app.infrastructure.database.session import get_session_factory
    factory = get_session_factory()

    normalized_query = query.strip()
    if not normalized_query or top_k <= 0:
        return []

    query_vector: list[float] | None = None
    try:
        provider = _get_embedding_provider()
        vectors = await provider.embed([normalized_query])
        from app.infrastructure.embeddings.provider import validate_embeddings
        validate_embeddings([normalized_query], vectors, provider.dimensions)
        query_vector = list(vectors[0])
    except Exception as error:  # noqa: BLE001 - 检索允许显式文本降级
        logger.warning("Memory query embedding unavailable; using text fallback: %s", error)

    try:
        async def _do_query():
            async with factory() as session:
                bind = session.get_bind()
                dialect_name = getattr(getattr(bind, "dialect", None), "name", "")
                if query_vector is not None and dialect_name == "postgresql":
                    result = await session.execute(
                        _memory_vector_search_sql(),
                        {
                            "query_vec": str(query_vector),
                            "workspace_id": workspace_id,
                            "top_k": top_k,
                        },
                    )
                    rows = result.mappings().all()
                    snippets = [
                        MemorySnippet(
                            id=row["id"],
                            memory_type=row["memory_type"],
                            content=row["content"],
                            confidence=row["confidence"],
                            rank_score=float(row["rank_score"]),
                        )
                        for row in rows
                    ]
                else:
                    # SQLite 测试与 Provider/pgvector 不可用时的显式文本降级。
                    # 仍强制 workspace/status 隔离，绝不跨租户扩大召回。
                    like = f"%{normalized_query.split()[0]}%"
                    stmt = (
                        select(UserMemoryModel)
                        .where(UserMemoryModel.workspace_id == workspace_id)
                        .where(UserMemoryModel.status == "active")
                        .where(UserMemoryModel.content.ilike(like))
                        .order_by(
                            UserMemoryModel.activation_count.desc(),
                            UserMemoryModel.created_at.desc(),
                        )
                        .limit(top_k)
                    )
                    rows = (await session.execute(stmt)).scalars().all()
                    snippets = [
                        MemorySnippet(
                            id=str(row.id),
                            memory_type=row.memory_type,
                            content=row.content,
                            confidence=row.confidence,
                        )
                        for row in rows
                    ]

                if not snippets:
                    return []

                memory_ids = [uuid.UUID(snippet.id) for snippet in snippets]
                stmt = (
                    select(UserMemoryModel)
                    .where(UserMemoryModel.id.in_(memory_ids))
                    .where(UserMemoryModel.workspace_id == workspace_id)
                    .where(UserMemoryModel.status == "active")
                )
                activated = (await session.execute(stmt)).scalars().all()
                for memory in activated:
                    memory.activation_count = (memory.activation_count or 0) + 1
                    memory.last_activated_at = datetime.now(timezone.utc)
                await session.commit()
                return snippets

        return await asyncio.wait_for(
            _do_query(), timeout=MEMORY_RETRIEVAL_TIMEOUT_MS / 1000
        )
    except asyncio.TimeoutError:
        logger.warning("Memory retrieval timed out after %dms", MEMORY_RETRIEVAL_TIMEOUT_MS)
    except Exception as e:
        logger.warning("Memory retrieval failed: %s", e)

    return []


async def list_memories(workspace_id: str = "default") -> list[UserMemoryModel]:
    """供前端「我的记忆」管理页：返回全部记忆条目。"""
    from app.infrastructure.database.session import get_session_factory
    factory = get_session_factory()
    async with factory() as session:
        stmt = (
            select(UserMemoryModel)
            .where(UserMemoryModel.workspace_id == workspace_id)
            .order_by(UserMemoryModel.created_at.desc())
        )
        return list((await session.execute(stmt)).scalars().all())


async def delete_memory(memory_id: str, workspace_id: str = "default") -> bool:
    from app.infrastructure.database.session import get_session_factory
    factory = get_session_factory()
    async with factory() as session:
        mem = await session.get(UserMemoryModel, uuid.UUID(memory_id))
        if not mem or mem.workspace_id != workspace_id:
            return False
        await session.delete(mem)
        await session.commit()
        return True


async def clear_all_memories(workspace_id: str = "default") -> int:
    from app.infrastructure.database.session import get_session_factory
    from sqlalchemy import delete as sql_delete
    factory = get_session_factory()
    async with factory() as session:
        stmt = sql_delete(UserMemoryModel).where(UserMemoryModel.workspace_id == workspace_id)
        result = await session.execute(stmt)
        await session.commit()
        return result.rowcount or 0


# ── R5 记忆生命周期管理 ──────────────────────────────────────────────────────────


async def create_memory(
    workspace_id: str,
    memory_type: str,
    content: str,
    confidence: float = 0.8,
    evidence: str | None = None,
) -> UserMemoryModel:
    """创建一条显式记忆（直接 active）。"""
    from app.infrastructure.database.session import get_session_factory
    factory = get_session_factory()
    async with factory() as session:
        mem = UserMemoryModel(
            workspace_id=workspace_id,
            memory_type=memory_type,
            content=content,
            confidence=confidence,
            status="active",
            evidence=evidence,
            source="manual",
        )
        session.add(mem)
        await session.commit()
        await session.refresh(mem)
        return mem


async def set_memory_status(
    memory_id: str, workspace_id: str, status: str
) -> UserMemoryModel | None:
    from app.infrastructure.database.session import get_session_factory
    factory = get_session_factory()
    async with factory() as session:
        mem = await session.get(UserMemoryModel, uuid.UUID(memory_id))
        if not mem or mem.workspace_id != workspace_id:
            return None
        mem.status = status
        await session.commit()
        return mem


async def confirm_memory(memory_id: str, workspace_id: str = "default") -> UserMemoryModel | None:
    """确认 pending 记忆 → active。"""
    return await set_memory_status(memory_id, workspace_id, "active")


async def reject_memory(memory_id: str, workspace_id: str = "default") -> UserMemoryModel | None:
    """拒绝 pending 记忆 → rejected（不注入）。"""
    return await set_memory_status(memory_id, workspace_id, "rejected")


async def update_memory_content(
    memory_id: str,
    workspace_id: str,
    content: str,
    confidence: float | None = None,
) -> UserMemoryModel | None:
    """编辑记忆内容并重新向量化（失败时保留旧 embedding）。"""
    from app.infrastructure.database.session import get_session_factory
    factory = get_session_factory()
    async with factory() as session:
        mem = await session.get(UserMemoryModel, uuid.UUID(memory_id))
        if not mem or mem.workspace_id != workspace_id:
            return None
        mem.content = content
        if confidence is not None:
            mem.confidence = confidence
        try:
            provider = _get_embedding_provider()
            vecs = await provider.embed([content])
            from app.infrastructure.embeddings.provider import validate_embeddings
            validate_embeddings([content], vecs, provider.dimensions)
            mem.embedding = list(vecs[0])
        except Exception as e:  # noqa: BLE001 - 向量化失败保留旧 embedding
            logger.warning("Re-embed on memory edit failed: %s", e)
        await session.commit()
        return mem
