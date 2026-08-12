"""知识库检索节点：执行 RAG 检索、落库 Trace 并将结果注入 State。"""
from __future__ import annotations
import logging
import time
from app.application.agent.state import ChatAgentState
from app.domain.knowledge import KnowledgeScope

logger = logging.getLogger(__name__)


async def retrieve_knowledge_node(state: ChatAgentState) -> dict:
    """执行混合检索，将 retrieval_result / trace_id / fallback_reason 写入 state。

    Trace 落库放在本节点而非 chat 节点：检索明细（命中、评分、降级原因）
    只有这里持有，chat 节点只消费最终上下文。
    """
    from app.persistence.session import get_session_factory
    from app.core.config import get_knowledge_settings
    from app.application.knowledge.retrieval_service import KnowledgeRetrievalService, RetrievalRequest
    from app.application.knowledge.trace_service import TraceService

    workspace_id = state.get("workspace_id", "default")
    owner_id = state.get("owner_id", "default")
    query = state.get("user_message", "")
    mode = state.get("knowledge_mode", "normal")

    scope = KnowledgeScope(workspace_id=workspace_id, owner_id=owner_id)
    settings = get_knowledge_settings()

    try:
        factory = get_session_factory()
        started = time.monotonic()
        async with factory() as session:
            svc = KnowledgeRetrievalService(session)
            request = RetrievalRequest(
                query=query,
                scope=scope,
                mode=mode,
                top_k_bm25=settings.bm25_top_k,
                top_k_vector=settings.vector_top_k,
                reranker_top_k=settings.reranker_top_k,
                evidence_threshold=settings.evidence_threshold,
                context_token_budget=settings.context_token_budget,
            )
            result = await svc.retrieve(request)

            trace_id: str | None = None
            try:
                trace_service = TraceService(session)
                trace = await trace_service.create_trace(
                    workspace_id=workspace_id,
                    owner_id=owner_id,
                    original_query=query,
                    rag_decision=True,
                    decision_reason=state.get("decision_reason") or "",
                    mode=mode,
                    chat_id=state.get("chat_id"),
                )
                if result.trace_hits:
                    await trace_service.record_hits(trace.id, result.trace_hits)
                await trace_service.finalize_trace(
                    trace.id,
                    latency_ms=int((time.monotonic() - started) * 1000),
                    fallback_reason=result.fallback_reason,
                    rewritten_query=result.rewritten_query,
                    index_version=result.index_version,
                    embedding_model=settings.embedding_model,
                    reranker_model=settings.reranker_model,
                )
                trace_id = str(trace.id)
            except Exception as trace_err:
                # Trace 是可观测性功能，落库失败不应阻断回答链路
                logger.warning("Retrieval trace persistence failed: %s", trace_err)

            return {
                "retrieval_result": result,
                "trace_id": trace_id,
                "fallback_reason": result.fallback_reason,
            }
    except Exception as e:
        logger.warning("Knowledge retrieval failed: %s", e)
        return {
            "retrieval_result": None,
            "trace_id": None,
            "fallback_reason": f"retrieval_error: {type(e).__name__}",
        }
