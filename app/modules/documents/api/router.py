"""Document API 路由；处理回答编辑器更新、AI 生成与精修（流式 SSE）和历史版本管理。"""
from __future__ import annotations

import logging
import uuid
from typing import Any, AsyncIterator

from fastapi import APIRouter, Request, Query, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.modules.documents.application.documents import DocumentService
from app.modules.documents.application.versions import VersionService
from app.modules.writing.application.outline import OutlineService, OutlineError
from app.modules.writing.application.review import evaluate_content, persist_creation_review
from app.shared.dto import InlineRefineRequest, SelectionDTO
from app.platform.database.session import get_db_session, get_session_factory
from app.modules.conversation.adapters.db.sources import SourceItem
from app.modules.writing.agent.nodes.answer_generation import generate_answer_workflow
from app.modules.writing.agent.nodes.inline_refinement import inline_refinement_workflow
from app.modules.writing.agent.nodes.full_rewrite import full_rewrite_workflow
from app.modules.writing.agent.graph import writer_graph
from app.platform.http.sse import sse_named_event, make_sse_response
from app.shared.errors import AppError, DocumentConflictError, LLMOutputError
from app.platform.observability.context import reset_log_context, set_log_context

logger = logging.getLogger(__name__)

router = APIRouter(prefix="", tags=["documents"])


async def _rewrite_creation_draft(content: str, instruction: str) -> str:
    """按评审指令重写内存草稿，不创建 AnswerVersion。"""
    from app.modules.writing.application.llm import get_writing_llm

    return await get_writing_llm().refine(
        instruction="保留已正确内容，只修复评审指出的问题。\n" + instruction,
        current_answer=content,
    )


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


class QualityReviewRequest(BaseModel):
    version_id: uuid.UUID | None = Field(None, alias="versionId")

    model_config = {"populate_by_name": True}


class QualityAdoptRequest(BaseModel):
    report_id: str = Field(alias="reportId")
    suggestion_id: str = Field(alias="suggestionId")
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


# ── 质检与逐条采纳（roadmap R3） ──────────────────────────────────────────────


@router.post("/api/documents/{document_id}/quality/review")
async def review_document_quality(
    document_id: uuid.UUID,
    req: QualityReviewRequest,
) -> JSONResponse:
    """对文档当前内容执行一次质检，返回报告与 reportId。"""
    from app.modules.writing.application.review import QualityService, QualityReviewError

    async for session in get_db_session():
        service = QualityService(session)
        try:
            result = await service.review(document_id, version_id=req.version_id)
            return JSONResponse(
                {
                    "ok": True,
                    "data": {
                        "reportId": result.report_id,
                        "sourceVersionId": result.source_version_id,
                        "report": result.report.model_dump(mode="json", by_alias=True),
                    },
                }
            )
        except QualityReviewError as e:
            return JSONResponse({"ok": False, "error": {"message": str(e)}}, status_code=400)
        except LLMOutputError as e:
            return JSONResponse(
                {"ok": False, "error": {"code": e.error_code, "message": str(e)}},
                status_code=502,
            )
    return JSONResponse({"ok": False, "error": "Internal database error"}, status_code=500)


@router.get("/api/documents/{document_id}/quality/reviews")
async def list_quality_reviews(document_id: uuid.UUID) -> JSONResponse:
    """返回某文档的自动创作报告，并兼容历史手动质检报告。"""
    from app.modules.writing.application.review import QualityService

    async for session in get_db_session():
        service = QualityService(session)
        rows = await service.list_creation_reviews(document_id)
        return JSONResponse({"ok": True, "data": rows})
    return JSONResponse({"ok": False, "error": "Internal database error"}, status_code=500)


@router.post("/api/documents/{document_id}/quality/adopt")
async def adopt_quality_suggestion(
    document_id: uuid.UUID,
    req: QualityAdoptRequest,
) -> JSONResponse:
    """逐条采纳质检建议，生成 inline_refinement 新版本并回填 quality_adopt 溯源。"""
    from app.modules.writing.application.review import QualityService, QualityReviewError

    async for session in get_db_session():
        service = QualityService(session)
        try:
            await service.adopt_suggestion(
                document_id=document_id,
                report_id=req.report_id,
                suggestion_id=req.suggestion_id,
                expected_lock_version=req.expected_lock_version,
            )
            doc_service = DocumentService(session)
            state = await doc_service.get_document_state(document_id)
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
        except QualityReviewError as e:
            return JSONResponse({"ok": False, "error": {"message": str(e)}}, status_code=400)
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
            current_outline = await OutlineService(session).get_current(doc_id)
            outline_sections = current_outline.outline if current_outline else None
            outline_operation_id = (
                uuid.UUID(current_outline.operation_id) if current_outline else None
            )

        run_id = str(uuid.uuid4())
        log_token = set_log_context(run_id=run_id, document_id=str(doc_id))
        yield sse_named_event("run.started", {"runId": run_id, "documentId": str(doc_id)})

        try:
            async with session_factory() as session:
                async for graph_event in writer_graph.astream(
                    {
                        "operation": "generate",
                        "direct_stream": True,
                        "goal": req.instruction or title,
                        "workspace_id": "default",
                        "owner_id": "default",
                        "session": session,
                        "source_item_id": source_item_id,
                        "document_id": doc_id,
                        "platform": req.platform or platform,
                        "title": title,
                        "content": content,
                        "expected_lock_version": req.expected_lock_version,
                        "style_rules": req.style_rules,
                        "word_count": req.word_count,
                        "instruction": req.instruction,
                        "outline": outline_sections,
                        "outline_operation_id": outline_operation_id,
                        "generate_workflow": generate_answer_workflow,
                        "evaluate_content": evaluate_content,
                        "persist_creation_review": persist_creation_review,
                        "rewrite_content": _rewrite_creation_draft,
                    },
                    stream_mode="custom",
                ):
                    yield sse_named_event(graph_event["event"], graph_event["data"])
            yield sse_named_event("run.completed", {"runId": run_id})

        except Exception as e:
            logger.exception("Answer generation graph failed")
            try:
                from app.modules.documents.adapters.db.models import AIOperation

                async with session_factory() as failure_session:
                    operation = (
                        await failure_session.execute(
                            select(AIOperation)
                            .where(
                                AIOperation.document_id == doc_id,
                                AIOperation.status == "running",
                            )
                            .order_by(AIOperation.created_at.desc())
                            .limit(1)
                        )
                    ).scalar_one_or_none()
                    if operation is not None:
                        operation.status = "failed"
                        operation.error_code = getattr(e, "error_code", "creation_review_failed")
                        operation.error_message = str(e)
                        await failure_session.commit()
            except Exception:
                logger.exception("Failed to persist Writer graph failure status")
            yield _run_failed_event(e, "生成失败，请稍后重试")
        finally:
            reset_log_context(log_token)

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
        log_token = set_log_context(run_id=run_id, document_id=str(document_id))
        yield sse_named_event("run.started", {"runId": run_id, "documentId": str(document_id)})

        try:
            async with session_factory() as session:
                async for graph_event in writer_graph.astream(
                    {
                        "operation": "inline_refine",
                        "direct_stream": True,
                        "goal": req.instruction,
                        "workspace_id": "default",
                        "owner_id": "default",
                        "session": session,
                        "document_id": document_id,
                        "selection": req.selection,
                        "instruction": req.instruction,
                        "expected_lock_version": req.expected_lock_version,
                        "refine_workflow": inline_refinement_workflow,
                    },
                    stream_mode="custom",
                ):
                    yield sse_named_event(graph_event["event"], graph_event["data"])
            yield sse_named_event("run.completed", {"runId": run_id})

        except Exception as e:
            logger.exception("Inline refinement stream failed")
            yield _run_failed_event(e, "精修失败，请稍后重试")
        finally:
            reset_log_context(log_token)

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
        log_token = set_log_context(run_id=run_id, document_id=str(document_id))
        yield sse_named_event("run.started", {"runId": run_id, "documentId": str(document_id)})

        try:
            async with session_factory() as session:
                async for graph_event in writer_graph.astream(
                    {
                        "operation": "full_rewrite",
                        "direct_stream": True,
                        "goal": req.instruction,
                        "workspace_id": "default",
                        "owner_id": "default",
                        "session": session,
                        "document_id": document_id,
                        "instruction": req.instruction,
                        "expected_lock_version": req.expected_lock_version,
                        "platform": req.platform,
                        "style_rules": req.style_rules,
                        "word_count": req.word_count,
                        "rewrite_workflow": full_rewrite_workflow,
                    },
                    stream_mode="custom",
                ):
                    yield sse_named_event(graph_event["event"], graph_event["data"])
            yield sse_named_event("run.completed", {"runId": run_id})

        except Exception as e:
            logger.exception("Full rewrite stream failed")
            yield _run_failed_event(e, "重写失败，请稍后重试")
        finally:
            reset_log_context(log_token)

    return make_sse_response(_event_generator())


# ── 质量评分 API（Phase 2 反思循环） ──────────────────────────────────────────


@router.get("/api/documents/{document_id}/quality-scores")
async def get_quality_scores(document_id: uuid.UUID):
    """返回某文档的全部自评记录，按 iteration 排序。"""
    from app.modules.writing.adapters.db.quality_scores import QualityScoreModel
    from app.platform.database.session import get_session_factory

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


# ── R6 观点采访与大纲 API ───────────────────────────────────────────────────────


class GenerateOutlineRequest(BaseModel):
    source_item_id: str = Field(alias="sourceItemId")
    expected_lock_version: int = Field(alias="expectedLockVersion")
    workspace_id: str = Field("default", alias="workspaceId")
    model_config = {"populate_by_name": True}


class UpdateOutlineRequest(BaseModel):
    sections: list[dict]
    viewpoint_answers: dict[str, str] | None = Field(None, alias="viewpointAnswers")
    expected_lock_version: int = Field(alias="expectedLockVersion")
    model_config = {"populate_by_name": True}


class ConfirmOutlineRequest(BaseModel):
    expected_lock_version: int = Field(alias="expectedLockVersion")
    model_config = {"populate_by_name": True}


def _outline_result(data) -> dict:
    return {
        "operationId": data.operation_id,
        "versionNumber": data.version_number,
        "basedOnOperationId": data.based_on_operation_id,
        "status": data.status,
        "viewpointQuestions": data.viewpoint_questions,
        "outline": data.outline,
    }


@router.post("/api/documents/{document_id}/outline/generate")
async def generate_outline(document_id: uuid.UUID, req: GenerateOutlineRequest):
    async for session in get_db_session():
        svc = OutlineService(session)
        try:
            result = await svc.generate(
                document_id,
                uuid.UUID(req.source_item_id),
                req.workspace_id,
                req.expected_lock_version,
            )
            return JSONResponse({"ok": True, "data": _outline_result(result)})
        except OutlineError as e:
            mapping = {"not_found": 404, "already_confirmed": 409}
            return JSONResponse(
                {"ok": False, "error": e.message},
                status_code=mapping.get(e.code, 400),
            )
        except DocumentConflictError:
            return JSONResponse(
                {"ok": False, "error": "Lock version conflict"},
                status_code=409,
            )


@router.get("/api/documents/{document_id}/outline/current")
async def get_current_outline(document_id: uuid.UUID):
    async for session in get_db_session():
        svc = OutlineService(session)
        result = await svc.get_current(document_id)
        if not result:
            return JSONResponse({"ok": True, "data": None})
        return JSONResponse({"ok": True, "data": _outline_result(result)})


@router.get("/api/documents/{document_id}/outline/versions")
async def list_outline_versions(document_id: uuid.UUID):
    async for session in get_db_session():
        results = await OutlineService(session).list_versions(document_id)
        return JSONResponse(
            {"ok": True, "data": [_outline_result(result) for result in results]}
        )


@router.post(
    "/api/documents/{document_id}/outline/versions/{operation_id}/activate"
)
async def activate_outline_version(
    document_id: uuid.UUID,
    operation_id: uuid.UUID,
    req: ConfirmOutlineRequest,
):
    async for session in get_db_session():
        try:
            result = await OutlineService(session).activate(
                document_id, operation_id, req.expected_lock_version
            )
            return JSONResponse({"ok": True, "data": _outline_result(result)})
        except OutlineError as error:
            return JSONResponse(
                {"ok": False, "error": error.message}, status_code=404
            )
        except DocumentConflictError:
            return JSONResponse(
                {"ok": False, "error": "Lock version conflict"}, status_code=409
            )


@router.put("/api/documents/{document_id}/outline/update")
async def update_outline(document_id: uuid.UUID, req: UpdateOutlineRequest):
    async for session in get_db_session():
        svc = OutlineService(session)
        try:
            result = await svc.update(
                document_id,
                req.sections,
                req.viewpoint_answers,
                req.expected_lock_version,
            )
            return JSONResponse({"ok": True, "data": _outline_result(result)})
        except OutlineError as e:
            return JSONResponse(
                {"ok": False, "error": e.message},
                status_code=404 if e.code == "not_found" else 400,
            )
        except DocumentConflictError:
            return JSONResponse(
                {"ok": False, "error": "Lock version conflict"},
                status_code=409,
            )


@router.post("/api/documents/{document_id}/outline/regenerate")
async def regenerate_outline(document_id: uuid.UUID, req: GenerateOutlineRequest):
    async for session in get_db_session():
        svc = OutlineService(session)
        try:
            result = await svc.regenerate(
                document_id,
                uuid.UUID(req.source_item_id),
                req.workspace_id,
                req.expected_lock_version,
            )
            return JSONResponse({"ok": True, "data": _outline_result(result)})
        except OutlineError as e:
            return JSONResponse(
                {"ok": False, "error": e.message},
                status_code=404 if e.code == "not_found" else 400,
            )
        except DocumentConflictError:
            return JSONResponse(
                {"ok": False, "error": "Lock version conflict"},
                status_code=409,
            )


@router.post("/api/documents/{document_id}/outline/confirm")
async def confirm_outline(document_id: uuid.UUID, req: ConfirmOutlineRequest):
    async for session in get_db_session():
        svc = OutlineService(session)
        try:
            result = await svc.confirm(document_id, req.expected_lock_version)
            return JSONResponse({"ok": True, "data": _outline_result(result)})
        except OutlineError as e:
            mapping = {"not_found": 404, "already_confirmed": 409}
            return JSONResponse(
                {"ok": False, "error": e.message},
                status_code=mapping.get(e.code, 400),
            )
        except DocumentConflictError:
            return JSONResponse(
                {"ok": False, "error": "Lock version conflict"},
                status_code=409,
            )
