"""R5 记忆提取编排：普通对话完成后后台沉淀记忆。

- 幂等：idempotency_key（run_id）级别防重（进程内 set 并发守卫 + DB source 去重），
  同一 run 重复运行不重复写入。
- 显式记忆直接 active；隐式/工作习惯记忆初始 pending_confirmation，待用户确认。
- LLM 与 embedding provider 可注入，便于测试；任何失败静默降级不阻断对话。
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from sqlalchemy import select

from app.infrastructure.database.models.user_memories import UserMemoryModel
from .service import (
    _get_embedding_provider,
    _get_memory_llm,
    _parse_extraction_json,
)

logger = logging.getLogger(__name__)

# 进程内并发守卫：同一 run 的重复提取只执行一次
_running_keys: set[str] = set()


@dataclass
class ExtractionResult:
    extracted: int = 0
    saved: int = 0
    skipped: bool = False


async def _extract_once(
    llm,
    embedding_provider,
    conversation: list[dict[str, str]],
    idempotency_key: str,
    workspace_id: str,
) -> tuple[int, list[UserMemoryModel], bool]:
    """执行一次抽取并落库；返回 (解析条目数, 落库列表, 是否命中 run 级去重)。"""
    from app.prompts.registry import prompt_registry

    rendered = prompt_registry.render(
        "memory.extract", conversation=json.dumps(conversation, ensure_ascii=False)
    )
    msg = rendered.to_llm_request().messages
    system_prompt = msg[0].content if msg else ""
    user_prompt = msg[1].content if len(msg) > 1 else ""

    raw = await llm.analyze(system_prompt, user_prompt)
    items = _parse_extraction_json(raw)
    parsed = len(items)

    contents = [it["content"] for it in items]
    embeddings: list[list[float] | None] = [None] * len(items)
    if contents:
        try:
            vecs = await embedding_provider.embed(contents)
            from app.infrastructure.embeddings.provider import validate_embeddings
            validate_embeddings(contents, vecs, embedding_provider.dimensions)
            embeddings = [list(v) for v in vecs]
        except Exception as e:  # noqa: BLE001 - 向量化失败静默降级，仅存文本
            logger.warning("Memory embedding failed, persist without vectors: %s", e)

    from app.infrastructure.database.session import get_session_factory

    factory = get_session_factory()
    async with factory() as session:
        existing_run = (
            await session.execute(
                select(UserMemoryModel.id).where(
                    UserMemoryModel.source == f"run:{idempotency_key}"
                ).limit(1)
            )
        ).scalar_one_or_none()
        if existing_run is not None:
            return parsed, [], True

        saved: list[UserMemoryModel] = []
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
                source=f"run:{idempotency_key}",
            )
            session.add(mem)
            saved.append(mem)
        await session.commit()
        return parsed, saved, False


async def run_memory_extraction(
    conversation: list[dict[str, str]],
    idempotency_key: str,
    workspace_id: str = "default",
    llm=None,
    embedding_provider=None,
) -> ExtractionResult:
    """后台沉淀记忆入口；进程内并发守卫 + DB run 级去重。"""
    if not idempotency_key or idempotency_key in _running_keys:
        return ExtractionResult(skipped=True)

    _running_keys.add(idempotency_key)
    try:
        llm = llm or _get_memory_llm()
        provider = embedding_provider or _get_embedding_provider()
        parsed, saved, db_skipped = await _extract_once(
            llm, provider, conversation, idempotency_key, workspace_id
        )
        return ExtractionResult(extracted=parsed, saved=len(saved), skipped=db_skipped)
    except Exception as e:  # noqa: BLE001 - 记忆沉淀失败不阻断对话
        logger.warning("Memory extraction failed for run %s: %s", idempotency_key, e)
        return ExtractionResult(extracted=0, saved=0)
    finally:
        _running_keys.discard(idempotency_key)
