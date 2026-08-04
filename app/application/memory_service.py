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

from sqlalchemy import select

from ..errors import LLMOutputError
from ..persistence.models.user_memories import UserMemoryModel

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


def _get_memory_llm():
    from app.application.agent.adapters import DeepSeekLLMAdapter
    return DeepSeekLLMAdapter()


def _get_embedding_provider():
    """复用知识库 Embedding Provider。"""
    from ..core.config import get_knowledge_settings
    from ..infrastructure.knowledge.embedding import EmbeddingProviderPort
    from ..infrastructure.knowledge.embedding import KnowledgeEmbeddingProvider

    settings = get_knowledge_settings()
    return KnowledgeEmbeddingProvider(settings)


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
        })
    return cleaned


async def extract_memories(
    messages: list[dict[str, str]],
    session_id: str,
    workspace_id: str = "default",
) -> list[UserMemoryModel]:
    """从本次对话中抽取可记忆信息并落库。"""
    from ..prompts.registry import prompt_registry

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
            embeddings = [list(v) for v in vecs]
        except Exception as e:
            logger.warning("Memory embedding failed, will persist without vectors: %s", e)

    from ..persistence.session import get_session_factory
    factory = get_session_factory()
    saved: list[UserMemoryModel] = []
    async with factory() as session:
        for it, emb in zip(items, embeddings):
            mem = UserMemoryModel(
                workspace_id=workspace_id,
                memory_type=it["memory_type"],
                content=it["content"],
                embedding=emb,
                confidence=it["confidence"],
                source=session_id,
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
    """检索与当前查询最相关的 top_k 条记忆；超 200ms 截断。

    第一版无 HNSW 索引时退化用 content LIKE；后续配 pgvector 走 cosine。
    """
    from ..persistence.session import get_session_factory
    factory = get_session_factory()

    snippets: list[MemorySnippet] = []

    try:
        async def _do():
            async with factory() as session:
                # 简版：按 workspace 过滤，按 activation_count desc + created_at desc 取 top
                # 真正语义检索需 pgvector，此为兜底实现
                stmt = (
                    select(UserMemoryModel)
                    .where(UserMemoryModel.workspace_id == workspace_id)
                    .order_by(
                        UserMemoryModel.activation_count.desc(),
                        UserMemoryModel.created_at.desc(),
                    )
                    .limit(top_k * 3)
                )
                # 关键词过滤以提高相关性
                if query.strip():
                    like = f"%{query.strip().split()[0]}%"
                    stmt = stmt.where(UserMemoryModel.content.ilike(like))
                stmt = stmt.limit(top_k)
                rows = (await session.execute(stmt)).scalars().all()

                # 更新激活计数与时间
                for r in rows:
                    r.activation_count = (r.activation_count or 0) + 1
                    r.last_activated_at = datetime.now(timezone.utc)
                await session.commit()

                return [
                    MemorySnippet(
                        id=str(r.id),
                        memory_type=r.memory_type,
                        content=r.content,
                        confidence=r.confidence,
                    )
                    for r in rows
                ]

        snippets = await asyncio.wait_for(_do(), timeout=MEMORY_RETRIEVAL_TIMEOUT_MS / 1000)
    except asyncio.TimeoutError:
        logger.warning("Memory retrieval timed out after %dms", MEMORY_RETRIEVAL_TIMEOUT_MS)
    except Exception as e:
        logger.warning("Memory retrieval failed: %s", e)

    return snippets


async def list_memories(workspace_id: str = "default") -> list[UserMemoryModel]:
    """供前端「我的记忆」管理页：返回全部记忆条目。"""
    from ..persistence.session import get_session_factory
    factory = get_session_factory()
    async with factory() as session:
        stmt = (
            select(UserMemoryModel)
            .where(UserMemoryModel.workspace_id == workspace_id)
            .order_by(UserMemoryModel.created_at.desc())
        )
        return list((await session.execute(stmt)).scalars().all())


async def delete_memory(memory_id: str, workspace_id: str = "default") -> bool:
    from ..persistence.session import get_session_factory
    factory = get_session_factory()
    async with factory() as session:
        mem = await session.get(UserMemoryModel, uuid.UUID(memory_id))
        if not mem or mem.workspace_id != workspace_id:
            return False
        await session.delete(mem)
        await session.commit()
        return True


async def clear_all_memories(workspace_id: str = "default") -> int:
    from ..persistence.session import get_session_factory
    from sqlalchemy import delete as sql_delete
    factory = get_session_factory()
    async with factory() as session:
        stmt = sql_delete(UserMemoryModel).where(UserMemoryModel.workspace_id == workspace_id)
        result = await session.execute(stmt)
        await session.commit()
        return result.rowcount or 0