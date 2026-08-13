import uuid
from uuid import UUID
from datetime import datetime, timezone
import httpx
import difflib
import logging
import os

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, ConfigDict, Field

from app.domain.knowledge import KnowledgeDocumentStatus, SourceType, KnowledgeScope
from app.application.knowledge.document_service import DocumentService
from app.application.knowledge.indexing_service import IndexingService
from app.application.knowledge.trace_service import TraceService
from app.infrastructure.knowledge.storage import KnowledgeStorage
from app.infrastructure.knowledge.ssrf import SSRFError, fetch_url_safely
from app.infrastructure.knowledge.parsers import (
    HtmlCleanerParser,
    MinerUCloudParser,
    ParsedMarkdown,
    _estimate_pdf_confidence,
)
from app.core.config import get_knowledge_settings, is_truthy
from app.persistence.session import get_db_session, get_session_factory
from app.application.knowledge.ingestion_service import (
    SourceIngestionService,
    source_file_to_dict,
    wake_ingestion_runtime,
)
from app.infrastructure.knowledge.source_files import SourceFileStorage
from app.infrastructure.knowledge.pdf_pages import PdfPageWorkspace
from app.persistence.models.knowledge import KnowledgeIngestionJobModel, KnowledgeSourceFileModel

router = APIRouter(prefix="/api", tags=["knowledge"])

logger = logging.getLogger(__name__)

# 转换置信度阈值；候选稿确认界面低于此值需展示人工校对警告（复用检索层 KNOWLEDGE_EVIDENCE_THRESHOLD 的概念）
KNOWLEDGE_CONVERSION_CONFIDENCE_THRESHOLD = 0.7


def _parse_pdf_locally(file_bytes: bytes, title: str) -> str:
    """本地 PDF→Markdown：pymupdf4llm 优先，失败时回退逐页纯文本提取。

    上传与重新解析（reconvert）共用此函数，避免两处平行实现；
    异常详情只写日志，绝不拼进落库的 Markdown 正文。
    """
    import fitz
    try:
        import pymupdf4llm
        pdf_doc = fitz.open(stream=file_bytes, filetype="pdf")
        md_text = pymupdf4llm.to_markdown(pdf_doc)
        if md_text.strip():
            return f"# {title}\n\n{md_text}"
        return f"# {title}\n\n(PDF 中未提取到文本正文)"
    except Exception:
        logger.exception("pymupdf4llm 转换失败，回退逐页提取: %s", title)
    try:
        pdf_doc = fitz.open(stream=file_bytes, filetype="pdf")
        page_texts = [
            f"## Page {i + 1}\n\n{page.get_text().strip()}"
            for i, page in enumerate(pdf_doc)
            if page.get_text().strip()
        ]
        if page_texts:
            return f"# {title}\n\n" + "\n\n---\n\n".join(page_texts)
    except Exception:
        logger.exception("PDF 逐页提取也失败: %s", title)
    return f"# {title}\n\n(PDF 解析失败，请检查文件是否损坏后重试)"


def _decode_text_file(file_bytes: bytes) -> str:
    """解码文本类上传文件；UTF-8 优先，GBK 兜底。"""
    try:
        return file_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return file_bytes.decode("gbk", errors="replace")


def _count_pdf_pages(file_bytes: bytes) -> int:
    """探测 PDF 总页数；失败回退 0,置信度计算退化为仅看纯净度。"""
    try:
        import fitz
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        n = len(doc)
        doc.close()
        return n
    except Exception:
        return 0


async def _parse_pdf_to_markdown(file_bytes: bytes, filename: str, doc_id: str, settings) -> ParsedMarkdown:
    """统一 PDF 解析入口:MinerU 优先,失败或未配置时降级为本地提取。

    两条路径都基于已产出的 Markdown 与总页数估算置信度(而非硬编码 1.0)。
    """
    if settings.mineru_api_key:
        try:
            mineru_parser = MinerUCloudParser(
                api_key=settings.mineru_api_key,
                base_url=settings.mineru_api_base_url,
                model_version=settings.mineru_model_version,
                max_pages_per_chunk=settings.pdf_max_pages_per_chunk,
                max_bytes_per_chunk=settings.pdf_max_bytes_per_chunk,
            )
            return await mineru_parser.parse_pdf(file_bytes, doc_id, filename)
        except Exception:
            logger.exception("MinerU 解析失败,降级为本地 PDF 解析: %s", filename)

    md_text = _parse_pdf_locally(file_bytes, filename)
    confidence = _estimate_pdf_confidence(md_text, _count_pdf_pages(file_bytes))
    warnings = ["本地提取模式(MinerU 不可用或失败),识别质量有限"] if confidence < 0.7 else []
    return ParsedMarkdown(markdown=md_text, confidence=confidence, warnings=warnings)

def _doc_to_dict(doc, source=None, job=None) -> dict:
    data = {
        "id": str(doc.id),
        "workspaceId": doc.workspace_id,
        "ownerId": doc.owner_id,
        "sourceType": doc.source_type,
        "title": doc.title,
        "sourceUrl": doc.source_url,
        "sourcePath": doc.source_path,
        "status": doc.status,
        "hasManualEdits": doc.has_manual_edits,
        "conversionConfidence": doc.conversion_confidence,
        "conversionError": doc.conversion_error,
        "activeIndexVersion": doc.active_index_version,
        "createdAt": doc.created_at.isoformat() if doc.created_at else None,
        "updatedAt": doc.updated_at.isoformat() if doc.updated_at else None,
    }
    if source:
        data["sourceFile"] = source_file_to_dict(source, job)
    return data

async def _run_indexing_task(document_id: UUID, workspace_id: str, owner_id: str) -> None:
    """在独立 session 中执行索引，不复用请求 session。"""
    try:
        factory = get_session_factory()
        settings = get_knowledge_settings()
        storage = KnowledgeStorage(settings.sources_dir, settings.documents_dir)
        scope = KnowledgeScope(workspace_id=workspace_id, owner_id=owner_id)
        async with factory() as session:
            svc = IndexingService(session, storage)
            res = await svc.index_document(document_id, scope)
            if not res.success:
                import logging
                logging.getLogger(__name__).error(f"Background indexing failed for doc {document_id}: {res.error}")
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception(f"Background indexing task exception for doc {document_id}: {e}")

def _get_document_service(session: AsyncSession = Depends(get_db_session)) -> DocumentService:
    settings = get_knowledge_settings()
    storage = KnowledgeStorage(settings.sources_dir, settings.documents_dir)
    return DocumentService(session, storage)

def _get_trace_service(session: AsyncSession = Depends(get_db_session)) -> TraceService:
    return TraceService(session)

class ImportUrlRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    url: str
    workspace_id: str = Field("default", alias="workspaceId")
    owner_id: str = Field("default", alias="ownerId")

class UpdateMarkdownRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    markdown: str
    workspace_id: str = Field("default", alias="workspaceId")

@router.post("/knowledge/documents")
async def upload_document(
    file: UploadFile = File(...),
    workspace_id: str = Form("default", alias="workspaceId"),
    owner_id: str = Form("default", alias="ownerId"),
    source_type: str | None = Form(None, alias="sourceType"),
    session: AsyncSession = Depends(get_db_session),
):
    filename = file.filename or "uploaded_file"
    settings = get_knowledge_settings()
    source_storage = SourceFileStorage(settings.source_files_dir)
    try:
        pending_path, _, content_hash = await source_storage.save_upload_stream(
            filename,
            file,
            settings.max_source_file_bytes,
            settings.source_file_buffer_bytes,
        )
    except ValueError as exc:
        if str(exc) != "file_too_large":
            raise
        raise HTTPException(
            status_code=413,
            detail=f"文件超过大小上限 {settings.max_source_file_bytes // (1024 * 1024)}MB",
        )
    outcome, source = await SourceIngestionService(session, settings).register_uploaded(
        pending_path, workspace_id, owner_id, content_hash=content_hash
    )
    wake_ingestion_runtime()
    return {
        "ok": True,
        "data": {"sourceFileId": str(source.id), "status": source.status, "outcome": outcome},
    }


@router.post("/knowledge/source-files/scan")
async def scan_source_files(
    workspace_id: str = Query("default", alias="workspaceId"),
    owner_id: str = Query("default", alias="ownerId"),
    session: AsyncSession = Depends(get_db_session),
):
    result = await SourceIngestionService(session).scan_pending(workspace_id, owner_id)
    wake_ingestion_runtime()
    return {
        "ok": True,
        "data": {
            "discovered": result.discovered,
            "queued": result.queued,
            "duplicates": result.duplicates,
            "failed": result.failed,
        },
    }


@router.get("/knowledge/source-files")
async def list_source_files(
    workspace_id: str = Query("default", alias="workspaceId"),
    session: AsyncSession = Depends(get_db_session),
):
    rows = await SourceIngestionService(session).list_sources(workspace_id)
    return {"ok": True, "data": {"sourceFiles": rows}}

@router.post("/knowledge/documents/import-url")
async def import_url(
    payload: ImportUrlRequest,
    doc_service: DocumentService = Depends(_get_document_service)
):
    try:
        # fetch_url_safely 内部逐跳校验重定向并限制响应体大小，见 ssrf 模块
        html = await fetch_url_safely(payload.url)
    except SSRFError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=422,
            detail=f"目标 URL 返回错误状态码: {e.response.status_code}",
        )
    except httpx.HTTPError:
        raise HTTPException(status_code=422, detail="无法访问目标 URL")


    doc = await doc_service.create_from_url(payload.url, payload.workspace_id, payload.owner_id)

    parser = HtmlCleanerParser()
    parsed_md = await parser.parse_html(html, str(doc.id), payload.url)
    await doc_service.save_candidate_markdown(
        doc.id, parsed_md.markdown, payload.workspace_id, confidence=parsed_md.confidence
    )
    
    doc = await doc_service.get_document(doc.id, payload.workspace_id)
    return {"ok": True, "data": _doc_to_dict(doc)}

@router.get("/knowledge/documents")
async def list_documents(
    workspace_id: str = Query("default", alias="workspaceId"),
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    doc_service: DocumentService = Depends(_get_document_service)
):
    docs, total = await doc_service.list_documents(workspace_id, status=status, limit=limit, offset=offset)
    sources = []
    if docs:
        sources = list((await doc_service.session.execute(
            select(KnowledgeSourceFileModel).where(
                KnowledgeSourceFileModel.knowledge_document_id.in_([doc.id for doc in docs])
            )
        )).scalars().all())
    source_by_doc = {source.knowledge_document_id: source for source in sources}
    latest_job_by_source = {}
    if sources:
        jobs = list((await doc_service.session.execute(
            select(KnowledgeIngestionJobModel)
            .where(KnowledgeIngestionJobModel.source_file_id.in_([source.id for source in sources]))
            .order_by(KnowledgeIngestionJobModel.created_at.desc())
        )).scalars().all())
        for job in jobs:
            latest_job_by_source.setdefault(job.source_file_id, job)
    return {
        "ok": True,
        "data": {
            "documents": [
                _doc_to_dict(
                    doc,
                    source_by_doc.get(doc.id),
                    latest_job_by_source.get(source_by_doc[doc.id].id) if doc.id in source_by_doc else None,
                )
                for doc in docs
            ],
            "total": total,
            "limit": limit,
            "offset": offset,
        }
    }

@router.get("/knowledge/documents/{document_id}")
async def get_document(
    document_id: UUID,
    workspace_id: str = Query("default", alias="workspaceId"),
    doc_service: DocumentService = Depends(_get_document_service)
):
    doc = await doc_service.get_document(document_id, workspace_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"ok": True, "data": _doc_to_dict(doc)}

@router.get("/knowledge/documents/{document_id}/markdown")
async def get_document_markdown(
    document_id: UUID,
    workspace_id: str = Query("default", alias="workspaceId"),
    is_candidate: bool = Query(False, alias="isCandidate"),
    doc_service: DocumentService = Depends(_get_document_service)
):
    markdown = await doc_service.get_markdown(document_id, workspace_id, is_candidate)
    return {
        "ok": True,
        "data": {
            "documentId": str(document_id),
            "markdown": markdown or "",
            "isCandidate": is_candidate,
        }
    }

@router.put("/knowledge/documents/{document_id}/markdown")
async def update_document_markdown(
    document_id: UUID,
    payload: UpdateMarkdownRequest,
    background_tasks: BackgroundTasks,
    doc_service: DocumentService = Depends(_get_document_service)
):
    doc = await doc_service.get_document(document_id, payload.workspace_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
        
    if doc.status == KnowledgeDocumentStatus.AWAITING_CONFIRMATION.value:
        await doc_service.save_candidate_markdown(document_id, payload.markdown, payload.workspace_id)
    elif doc.status == KnowledgeDocumentStatus.AVAILABLE.value:
        await doc_service.save_active_markdown(document_id, payload.markdown, payload.workspace_id)
        background_tasks.add_task(_run_indexing_task, document_id, payload.workspace_id, doc.owner_id)
    else:
        # INDEXING / PENDING / FAILED 等状态不允许编辑，显式报错而非静默"成功"
        raise HTTPException(
            status_code=409,
            detail=f"文档当前状态（{doc.status}）不允许编辑 Markdown",
        )

    return {
        "ok": True,
        "data": {
            "documentId": str(document_id),
            "updated": True,
        }
    }

@router.post("/knowledge/documents/{document_id}/confirm")
async def confirm_document(
    document_id: UUID,
    background_tasks: BackgroundTasks,
    workspace_id: str = Query("default", alias="workspaceId"),
    doc_service: DocumentService = Depends(_get_document_service)
):
    try:
        doc = await doc_service.confirm_document(document_id, workspace_id)
    except ValueError as e:
        # 文档或候选稿不存在属于客户端可修复的错误，映射为 404 而非 500
        raise HTTPException(status_code=404, detail=str(e))
    source = (
        await doc_service.session.execute(
            select(KnowledgeSourceFileModel).where(
                KnowledgeSourceFileModel.knowledge_document_id == document_id,
                KnowledgeSourceFileModel.status == "recognized",
            )
        )
    ).scalar_one_or_none()
    if source:
        managed_files = SourceFileStorage(get_knowledge_settings().source_files_dir)
        moved = managed_files.move(source.current_relative_path, "archived", source.id)
        source.current_relative_path = str(moved)
        source.status = "archived"
        doc.source_path = str(managed_files.resolve_relative(moved))
        await doc_service.session.commit()
        jobs = list((await doc_service.session.execute(
            select(KnowledgeIngestionJobModel).where(
                KnowledgeIngestionJobModel.source_file_id == source.id
            )
        )).scalars().all())
        settings = get_knowledge_settings()
        for job in jobs:
            PdfPageWorkspace(settings.ingestion_work_dir, job.id).cleanup()
    background_tasks.add_task(_run_indexing_task, document_id, workspace_id, doc.owner_id)
    return {
        "ok": True,
        "data": {
            "documentId": str(document_id),
            "status": KnowledgeDocumentStatus.AVAILABLE.value,
        }
    }

@router.post("/knowledge/documents/{document_id}/reconvert")
async def reconvert_document(
    document_id: UUID,
    workspace_id: str = Query("default", alias="workspaceId"),
    doc_service: DocumentService = Depends(_get_document_service)
):
    doc = await doc_service.get_document(document_id, workspace_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
        
    # 读取原始上传文件用于重新解析
    if not doc.source_path:
        raise HTTPException(status_code=422, detail="该文档没有原始文件，无法重新解析")
    settings = get_knowledge_settings()
    storage = KnowledgeStorage(settings.sources_dir, settings.documents_dir)
    source = (
        await doc_service.session.execute(
            select(KnowledgeSourceFileModel).where(
                KnowledgeSourceFileModel.knowledge_document_id == document_id
            )
        )
    ).scalar_one_or_none()
    try:
        if source:
            managed = SourceFileStorage(settings.source_files_dir)
            file_bytes = managed.resolve_relative(source.current_relative_path).read_bytes()
        else:
            file_bytes = storage.read_source(doc.source_path)
    except (ValueError, OSError):
        raise HTTPException(status_code=422, detail="源文件路径无效，无法重新解析")
    if file_bytes is None:
        raise HTTPException(status_code=404, detail="原始文件已不存在，无法重新解析")

    ext = doc.title.split(".")[-1].lower() if "." in doc.title else ""
    if ext == "pdf":
        pm = await _parse_pdf_to_markdown(file_bytes, doc.title, str(doc.id), settings)
        parsed_markdown = pm.markdown
        confidence = pm.confidence
    else:
        parsed_markdown = _decode_text_file(file_bytes)
        confidence = 1.0

    old_markdown = await doc_service.get_markdown(document_id, workspace_id, is_candidate=False) or ""
    await doc_service.save_candidate_markdown(document_id, parsed_markdown, workspace_id, confidence=confidence)
    
    diff = "\n".join(difflib.unified_diff(
        old_markdown.splitlines(),
        parsed_markdown.splitlines(),
        fromfile="现有的 Markdown",
        tofile="新解析候选版本"
    ))
    
    return {
        "ok": True,
        "data": {
            "documentId": str(document_id),
            "status": KnowledgeDocumentStatus.AWAITING_CONFIRMATION.value,
            "diff": diff,
        }
    }

@router.delete("/knowledge/documents/{document_id}")
async def delete_document(
    document_id: UUID,
    workspace_id: str = Query("default", alias="workspaceId"),
    doc_service: DocumentService = Depends(_get_document_service)
):
    source = (
        await doc_service.session.execute(
            select(KnowledgeSourceFileModel).where(
                KnowledgeSourceFileModel.knowledge_document_id == document_id
            )
        )
    ).scalar_one_or_none()
    await doc_service.soft_delete(document_id, workspace_id)
    if source:
        jobs = list((await doc_service.session.execute(
            select(KnowledgeIngestionJobModel).where(
                KnowledgeIngestionJobModel.source_file_id == source.id
            )
        )).scalars().all())
        settings = get_knowledge_settings()
        for job in jobs:
            PdfPageWorkspace(settings.ingestion_work_dir, job.id).cleanup()
    return {
        "ok": True,
        "data": {
            "documentId": str(document_id),
            "status": KnowledgeDocumentStatus.DELETED.value,
        }
    }

@router.get("/ai-operations/{operation_id}/sources")
async def get_operation_sources(
    operation_id: str,
    workspace_id: str = Query("default", alias="workspaceId"),
    trace_service: TraceService = Depends(_get_trace_service)
):
    # operation_id 即 trace 主键；非法 UUID 返回 404 而非 500
    try:
        trace_uuid = UUID(operation_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Operation not found")

    # 返回简化来源（不含内部评分）；hits 已在 get_trace 中预加载
    trace = await trace_service.get_trace(trace_uuid, workspace_id)
    sources = []
    if trace:
        for hit in trace.hits:
            if not hit.included_in_context:
                continue
            sources.append({
                "chunkId": str(hit.chunk_id),
                "label": hit.citation_label,
                "text": hit.context_snapshot,
            })
    return {
        "ok": True,
        "data": {
            "operationId": operation_id,
            "sources": sources,
        }
    }

@router.get("/retrieval-traces/{trace_id}")
async def get_retrieval_trace(
    trace_id: UUID,
    workspace_id: str = Query("default", alias="workspaceId"),
    trace_service: TraceService = Depends(_get_trace_service)
):
    # Trace 含内部评分等调试信息，由服务端环境开关控制，
    # 而非请求参数——客户端可任意传参，不构成门禁
    if not is_truthy(os.getenv("KNOWLEDGE_TRACE_DEBUG", "true")):
        raise HTTPException(status_code=403, detail="Retrieval trace debug is disabled")
    trace = await trace_service.get_trace(trace_id, workspace_id)
    if not trace:
        raise HTTPException(status_code=404, detail="Retrieval trace not found")
    return {"ok": True, "data": trace}


class TestSearchRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    query: str
    workspace_id: str = Field("default", alias="workspaceId")
    owner_id: str = Field("default", alias="ownerId")
    mode: str = Field("normal")


@router.post("/knowledge/test-search")
async def test_knowledge_retrieval(
    payload: TestSearchRequest,
    session: AsyncSession = Depends(get_db_session)
):
    from app.application.knowledge.retrieval_service import KnowledgeRetrievalService, RetrievalRequest
    from app.domain.knowledge import KnowledgeScope

    settings = get_knowledge_settings()
    scope = KnowledgeScope(workspace_id=payload.workspace_id, owner_id=payload.owner_id)
    svc = KnowledgeRetrievalService(session)

    req = RetrievalRequest(
        query=payload.query,
        scope=scope,
        mode=payload.mode,
        top_k_bm25=settings.bm25_top_k,
        top_k_vector=settings.vector_top_k,
        reranker_top_k=settings.reranker_top_k,
        evidence_threshold=settings.evidence_threshold,
        context_token_budget=settings.context_token_budget,
    )

    result = await svc.retrieve(req)

    return {
        "ok": True,
        "data": {
            "query": payload.query,
            "rewrittenQuery": result.rewritten_query,
            "hasEvidence": result.has_evidence,
            "fallbackReason": result.fallback_reason,
            "contextText": result.context_text,
            "sources": result.sources,
            "traceHits": result.trace_hits,
            "indexVersion": result.index_version,
            "pipelineSteps": result.pipeline_steps,
        }
    }
