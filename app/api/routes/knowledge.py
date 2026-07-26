import uuid
from uuid import UUID
from datetime import datetime, timezone
import httpx
import difflib
import logging
import os

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, ConfigDict, Field

from app.domain.knowledge import KnowledgeDocumentStatus, SourceType, KnowledgeScope
from app.application.knowledge.document_service import DocumentService
from app.application.knowledge.indexing_service import IndexingService
from app.application.knowledge.trace_service import TraceService
from app.infrastructure.knowledge.storage import KnowledgeStorage
from app.infrastructure.knowledge.ssrf import SSRFError, fetch_url_safely
from app.infrastructure.knowledge.parsers import HtmlCleanerParser, MinerUCloudParser
from app.core.config import get_knowledge_settings, is_truthy
from app.persistence.session import get_db_session, get_session_factory

router = APIRouter(prefix="/api", tags=["knowledge"])

logger = logging.getLogger(__name__)

# 允许上传的文件扩展名白名单；其他类型既无解析器也不该落盘
ALLOWED_UPLOAD_EXTENSIONS = {"md", "markdown", "txt", "pdf"}


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

def _doc_to_dict(doc) -> dict:
    return {
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
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    workspace_id: str = Form("default", alias="workspaceId"),
    owner_id: str = Form("default", alias="ownerId"),
    source_type: str | None = Form(None, alias="sourceType"),
    doc_service: DocumentService = Depends(_get_document_service)
):
    filename = file.filename or "uploaded_file"
    ext = filename.split(".")[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件类型 .{ext}，仅支持: {', '.join(sorted(ALLOWED_UPLOAD_EXTENSIONS))}",
        )
    inferred_type = SourceType.MARKDOWN if ext in ("md", "markdown") else (SourceType.PDF if ext == "pdf" else SourceType.TEXT)
    final_source_type = source_type or inferred_type.value

    settings = get_knowledge_settings()
    # 多读 1 字节以检测超限，避免恰好等于上限时误判
    file_bytes = await file.read(settings.max_upload_bytes + 1)
    if len(file_bytes) > settings.max_upload_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"文件超过大小上限 {settings.max_upload_bytes // (1024 * 1024)}MB",
        )

    doc, created = await doc_service.create_from_upload(file_bytes, filename, final_source_type, workspace_id, owner_id)
    if not created:
        # 去重命中：直接返回已存在文档，绝不重新解析覆盖其候选稿/索引状态
        return {"ok": True, "data": _doc_to_dict(doc), "deduplicated": True}

    parsed_markdown = ""
    if ext == "pdf":
        if settings.mineru_api_key:
            try:
                mineru_parser = MinerUCloudParser(
                    api_key=settings.mineru_api_key,
                    base_url=settings.mineru_api_base_url,
                    model_version=settings.mineru_model_version,
                    max_pages_per_chunk=settings.pdf_max_pages_per_chunk,
                    max_bytes_per_chunk=settings.pdf_max_bytes_per_chunk,
                )
                pm = await mineru_parser.parse_pdf(file_bytes, str(doc.id), filename)
                parsed_markdown = pm.markdown
            except Exception:
                logger.exception("MinerU 解析失败，降级为本地 PDF 解析: %s", filename)
                parsed_markdown = _parse_pdf_locally(file_bytes, filename)
        else:
            parsed_markdown = _parse_pdf_locally(file_bytes, filename)
    else:
        parsed_markdown = _decode_text_file(file_bytes)

    await doc_service.save_candidate_markdown(doc.id, parsed_markdown, workspace_id)

    if final_source_type == SourceType.MARKDOWN.value or final_source_type == SourceType.MARKDOWN:
        background_tasks.add_task(_run_indexing_task, doc.id, workspace_id, owner_id)

    doc = await doc_service.get_document(doc.id, workspace_id)
    return {"ok": True, "data": _doc_to_dict(doc)}

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
    await doc_service.save_candidate_markdown(doc.id, parsed_md.markdown, payload.workspace_id)
    
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
    return {
        "ok": True,
        "data": {
            "documents": [_doc_to_dict(d) for d in docs],
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
    file_bytes = storage.read_source(doc.source_path)
    if file_bytes is None:
        raise HTTPException(status_code=404, detail="原始文件已不存在，无法重新解析")

    ext = doc.title.split(".")[-1].lower() if "." in doc.title else ""
    if ext == "pdf":
        parsed_markdown = _parse_pdf_locally(file_bytes, doc.title)
    else:
        parsed_markdown = _decode_text_file(file_bytes)

    old_markdown = await doc_service.get_markdown(document_id, workspace_id, is_candidate=False) or ""
    await doc_service.save_candidate_markdown(document_id, parsed_markdown, workspace_id)
    
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
    await doc_service.soft_delete(document_id, workspace_id)
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
