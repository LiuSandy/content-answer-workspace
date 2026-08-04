"""Document API 路由；处理回答编辑器更新、AI 生成与精修（流式 SSE）和历史版本管理。"""
from __future__ import annotations

import logging
import uuid
from typing import Any, AsyncIterator

from fastapi import APIRouter, Request, Query, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ...application.document_service import DocumentService
from ...application.version_service import VersionService
from ...domain.dto import InlineRefineRequest, SelectionDTO
from ...persistence.session import get_db_session, get_session_factory
from ...persistence.models.content import SourceItem
from ...workflows.answer_generation import generate_answer_workflow
from ...workflows.inline_refinement import inline_refinement_workflow
from ...workflows.full_rewrite import full_rewrite_workflow
from ..sse_utils import sse_named_event, make_sse_response
from ...errors import AppError, DocumentConflictError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="", tags=["documents"])


def _run_failed_event(exc: Exception, fallback_message: str) -> str:
    """将工作流异常转换为 run.failed 事件负载。

    AppError 及其子类的 message 是特意写给用户看的业务提示（如选区不匹配、
    锁版本冲突），可以安全透出；其他未预期异常只暴露通用文案，避免把内部
    堆栈信息泄露给前端。
    """
    if isinstance(exc, AppError):
        return sse_named_event("run.failed", {"errorCode": exc.error_code, "message": str(exc)})
    return sse_named_event("run.failed", {"errorCode": "internal_error", "message": fallback_message})


class UpdateDocumentRequest(BaseModel):
    content: str
    expected_lock_version: int = Field(alias="expectedLockVersion")
    
    model_config = {"populate_by_name": True}


class FullRewriteRequest(BaseModel):
    instruction: str
    expected_lock_version: int = Field(alias="expectedLockVersion")
    platform: str | None = Field(None, alias="platform")
    style_rules: str | None = Field(None, alias="styleRules")
    word_count: int = Field(1000, alias="wordCount")
    
    model_config = {"populate_by_name": True}


class CreateCheckpointRequest(BaseModel):
    expected_lock_version: int = Field(alias="expectedLockVersion")
    platform: str | None = Field(None, alias="platform")
    style_rules: str | None = Field(None, alias="styleRules")
    word_count: int = Field(1000, alias="wordCount")
    instruction: str | None = Field(None, alias="instruction")
    
    model_config = {"populate_by_name": True}


class RestoreVersionRequest(BaseModel):
    expected_lock_version: int = Field(alias="expectedLockVersion")
    
    model_config = {"populate_by_name": True}


# ── REST API 端点 ────────────────────────────────────────────────────────────

@router.get("/api/source-items/{source_item_id}/document")
async def get_or_create_document(source_item_id: uuid.UUID) -> JSONResponse:
    """获取或初始化帖子的编辑器 Document。"""
    async for session in get_db_session():
        doc_service = DocumentService(session)
        doc = await doc_service.get_or_create_document(source_item_id)
        state = await doc_service.get_document_state(doc.id)
        return JSONResponse({"ok": True, "data": state.model_dump(mode="json", by_alias=True)})
    return JSONResponse({"ok": False, "error": "Internal database error"}, status_code=500)


@router.put("/api/documents/{document_id}")
async def update_document(
    document_id: uuid.UUID,
    req: UpdateDocumentRequest,
) -> JSONResponse:
    """自动保存：直接更新 current_content，携带 expectedLockVersion，防冲突。"""
    async for session in get_db_session():
        doc_service = DocumentService(session)
        try:
            doc = await doc_service.update_content(
                document_id=document_id,
                content=req.content,
                expected_lock_version=req.expected_lock_version,
            )
            state = await doc_service.get_document_state(doc.id)
            return JSONResponse({"ok": True, "data": state.model_dump(mode="json", by_alias=True)})
        except DocumentConflictError as e:
            return JSONResponse(
                {
                    "ok": False,
                    "error": {
                        "code": "document_conflict",
                        "message": str(e),
                        "expected": e.expected,
                        "actual": e.actual,
                    },
                },
                status_code=409,
            )
    return JSONResponse({"ok": False, "error": "Internal database error"}, status_code=500)


@router.get("/api/documents/{document_id}/versions")
async def list_versions(document_id: uuid.UUID) -> JSONResponse:
    """获取文档历史版本快照摘要列表。"""
    async for session in get_db_session():
        version_service = VersionService(session)
        versions = await version_service.list_versions(document_id)
        return JSONResponse(
            {
                "ok": True,
                "data": [v.model_dump(mode="json", by_alias=True) for v in versions],
            }
        )
    return JSONResponse({"ok": False, "error": "Internal database error"}, status_code=500)


@router.post("/api/documents/{document_id}/versions")
async def create_checkpoint(
    document_id: uuid.UUID,
    req: CreateCheckpointRequest,
) -> JSONResponse:
    """手动保存当前内容为一个历史版本快照。"""
    async for session in get_db_session():
        version_service = VersionService(session)
        try:
            version = await version_service.create_manual_checkpoint(
                document_id=document_id,
                expected_lock_version=req.expected_lock_version,
            )
            doc_service = DocumentService(session)
            state = await doc_service.get_document_state(document_id)
            return JSONResponse({"ok": True, "data": state.model_dump(mode="json", by_alias=True)})
        except DocumentConflictError as e:
            return JSONResponse(
                {"ok": False, "error": {"code": "document_conflict", "message": str(e)}},
                status_code=409,
            )
        except Exception:
            logger.exception("Document version operation failed")
            return JSONResponse({"ok": False, "error": "操作失败，请稍后重试"}, status_code=400)
    return JSONResponse({"ok": False, "error": "Internal database error"}, status_code=500)


@router.post("/api/documents/{document_id}/versions/{version_id}/restore")
async def restore_version(
    document_id: uuid.UUID,
    version_id: uuid.UUID,
    req: RestoreVersionRequest,
) -> JSONResponse:
    """恢复某一历史版本为当前最新内容。"""
    async for session in get_db_session():
        version_service = VersionService(session)
        try:
            await version_service.restore_version(
                document_id=document_id,
                version_id=version_id,
                expected_lock_version=req.expected_lock_version,
            )
            doc_service = DocumentService(session)
            state = await doc_service.get_document_state(document_id)
            return JSONResponse({"ok": True, "data": state.model_dump(mode="json", by_alias=True)})
        except DocumentConflictError as e:
            return JSONResponse(
                {"ok": False, "error": {"code": "document_conflict", "message": str(e)}},
                status_code=409,
            )
        except Exception:
            logger.exception("Document version operation failed")
            return JSONResponse({"ok": False, "error": "操作失败，请稍后重试"}, status_code=400)
    return JSONResponse({"ok": False, "error": "Internal database error"}, status_code=500)


# ── AI 流式创作与精修端点 (SSE) ──────────────────────────────────────────────────

@router.post("/api/source-items/{source_item_id}/document/generate")
async def generate_answer_stream(
    source_item_id: uuid.UUID,
    req: CreateCheckpointRequest,  # 复用以获取 expected_lock_version
) -> Any:
    """首次 AI 生成回答；通过 SSE 协议推送字符流，结束后写入历史。"""
    session_factory = get_session_factory()

    async def _event_generator() -> AsyncIterator[str]:
        # 1. 查找 source_item 详情
        async with session_factory() as session:
            source_item = await session.get(SourceItem, source_item_id)
            if not source_item:
                yield sse_named_event("run.failed", {"errorCode": "not_found", "message": "未找到对应的帖子"})
                return
            
            doc_service = DocumentService(session)
            doc = await doc_service.get_or_create_document(source_item_id)
            doc_id = doc.id
            platform = source_item.platform
            title = source_item.title
            content = source_item.content

        run_id = str(uuid.uuid4())
        yield sse_named_event("run.started", {"runId": run_id, "documentId": str(doc_id)})

        try:
            # 2. 调用 workflow
            async with session_factory() as session:
                async for chunk in generate_answer_workflow(
                    session=session,
                    source_item_id=source_item_id,
                    document_id=doc_id,
                    platform=req.platform or platform,
                    title=title,
                    content=content,
                    expected_lock_version=req.expected_lock_version,
                    style_rules=req.style_rules,
                    word_count=req.word_count,
                    instruction=req.instruction,
                ):
                    yield sse_named_event("document.delta", {"delta": chunk})

                # 3. 结束后拉取最新状态并发送 completed 事件
                doc_service = DocumentService(session)
                state = await doc_service.get_document_state(doc_id)
                yield sse_named_event("document.completed", state.model_dump(mode="json", by_alias=True))
                yield sse_named_event("run.completed", {"runId": run_id})

                # 4. Phase 2 反思循环：自评 < 0.75 自动定向修正（最多 3 轮）
                #    修正后内容落库为 inline_refinement AnswerVersion。
                try:
                    from ...application.workflows.reflect_refine import reflect_and_refine
                    from sqlalchemy import select as _select
                    from ..persistence.models.documents import AnswerDocument

                    current_content = state.current_content or ""
                    if current_content.strip():
                        result = await reflect_and_refine(
                            content=current_content,
                            document_id=doc_id,
                            version_id=None,
                            workspace_id="default",
                        )
                        # 修正后的内容落库为新 AnswerVersion（inline_refinement）
                        if result["final_content"] != current_content:
                            async with session_factory() as s2:
                                fresh = (await s2.execute(
                                    _select(AnswerDocument).where(AnswerDocument.id == doc_id)
                                )).scalar_one_or_none()
                                if fresh:
                                    ds = DocumentService(s2)
                                    try:
                                        await ds.create_version(
                                            document_id=doc_id,
                                            content=result["final_content"],
                                            version_type="inline_refinement",
                                            expected_lock_version=fresh.lock_version,
                                            instruction=result.get("forced_message") or "反思循环自动修正",
                                        )
                                    except Exception as cv_err:
                                        logger.warning("Reflection create_version failed: %s", cv_err)
                        yield sse_named_event("reflection.completed", {
                            "iterations": result["iterations"],
                            "converged": result["converged"],
                            "finalScore": result["scores"][-1].overall_score if result.get("scores") else None,
                            "forcedMessage": result["forced_message"],
                        })
                except Exception as refl_err:
                    logger.warning("Reflection loop failed (non-blocking): %s", refl_err)

        except Exception as e:
            logger.error("Answer generation stream failed: %s", e)
            yield _run_failed_event(e, "生成失败，请稍后重试")

    return make_sse_response(_event_generator())


@router.post("/api/documents/{document_id}/refine")
async def refine_document_stream(
    document_id: uuid.UUID,
    req: InlineRefineRequest,
) -> Any:
    """局部精修（选区优化）；通过 SSE 协议推送替换文本，结束后合并写入历史。"""
    session_factory = get_session_factory()

    async def _event_generator() -> AsyncIterator[str]:
        run_id = str(uuid.uuid4())
        yield sse_named_event("run.started", {"runId": run_id, "documentId": str(document_id)})

        try:
            async with session_factory() as session:
                async for chunk in inline_refinement_workflow(
                    session=session,
                    document_id=document_id,
                    selection=req.selection,
                    instruction=req.instruction,
                    expected_lock_version=req.expected_lock_version,
                ):
                    yield sse_named_event("document.delta", {"delta": chunk})

                doc_service = DocumentService(session)
                state = await doc_service.get_document_state(document_id)
                yield sse_named_event("document.completed", state.model_dump(mode="json", by_alias=True))
                yield sse_named_event("run.completed", {"runId": run_id})

        except Exception as e:
            logger.error("Inline refinement stream failed: %s", e)
            yield _run_failed_event(e, "精修失败，请稍后重试")

    return make_sse_response(_event_generator())


@router.post("/api/documents/{document_id}/rewrite")
async def rewrite_document_stream(
    document_id: uuid.UUID,
    req: FullRewriteRequest,
) -> Any:
    """全文重写；根据新指令重新生成整个回答，通过 SSE 协议流式返回，结束后写入历史。"""
    session_factory = get_session_factory()

    async def _event_generator() -> AsyncIterator[str]:
        run_id = str(uuid.uuid4())
        yield sse_named_event("run.started", {"runId": run_id, "documentId": str(document_id)})

        try:
            async with session_factory() as session:
                async for chunk in full_rewrite_workflow(
                    session=session,
                    document_id=document_id,
                    instruction=req.instruction,
                    expected_lock_version=req.expected_lock_version,
                    platform=req.platform,
                    style_rules=req.style_rules,
                    word_count=req.word_count,
                ):
                    yield sse_named_event("document.delta", {"delta": chunk})

                doc_service = DocumentService(session)
                state = await doc_service.get_document_state(document_id)
                yield sse_named_event("document.completed", state.model_dump(mode="json", by_alias=True))
                yield sse_named_event("run.completed", {"runId": run_id})

        except Exception as e:
            logger.error("Full rewrite stream failed: %s", e)
            yield _run_failed_event(e, "重写失败，请稍后重试")

    return make_sse_response(_event_generator())


# ── 质量评分 API（Phase 2 反思循环） ──────────────────────────────────────────


@router.get("/api/documents/{document_id}/quality-scores")
async def get_quality_scores(document_id: uuid.UUID):
    """返回某文档的全部自评记录，按 iteration 排序。"""
    from sqlalchemy import select
    from ...persistence.models.quality_scores import QualityScoreModel
    from ...persistence.session import get_session_factory

    session_factory = get_session_factory()
    async with session_factory() as session:
        stmt = (
            select(QualityScoreModel)
            .where(QualityScoreModel.document_id == document_id)
            .order_by(QualityScoreModel.iteration)
        )
        rows = (await session.execute(stmt)).scalars().all()

    return {
        "ok": True,
        "data": [
            {
                "id": str(r.id),
                "iteration": r.iteration,
                "overallScore": r.overall_score,
                "dimensions": r.dimensions,
                "weaknessSummary": r.weakness_summary,
                "refinementInstruction": r.refinement_instruction,
                "converged": r.converged == "true",
                "createdAt": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
    }
