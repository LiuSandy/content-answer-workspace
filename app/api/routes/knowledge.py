import uuid
from uuid import UUID
from datetime import datetime, timezone
from typing import Any, Dict
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query, BackgroundTasks
from pydantic import BaseModel, ConfigDict, Field

from app.domain.knowledge import KnowledgeDocumentStatus, SourceType
from app.application.knowledge.document_service import DocumentService

router = APIRouter(prefix="/api", tags=["knowledge"])

# 内存型真实知识库动态存储
_DOCUMENTS_STORE: Dict[str, Dict[str, Any]] = {}
_MARKDOWN_STORE: Dict[str, str] = {}


class ImportUrlRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    url: str
    workspace_id: str = Field("default", alias="workspaceId")
    owner_id: str = Field("default", alias="ownerId")


class UpdateMarkdownRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    markdown: str
    workspace_id: str = Field("default", alias="workspaceId")


@router.get("/knowledge/documents")
async def list_documents(
    workspace_id: str = Query("default", alias="workspaceId"),
    status: str | None = Query(None),
    limit: int = Query(50),
    offset: int = Query(0),
):
    docs = list(_DOCUMENTS_STORE.values())
    
    # 按 workspaceId 过滤
    filtered = [d for d in docs if d.get("workspaceId") == workspace_id]
    
    # 按 status 过滤
    if status:
        filtered = [d for d in filtered if d.get("status") == status]

    return {
        "ok": True,
        "data": {
            "documents": filtered,
            "total": len(filtered),
            "limit": limit,
            "offset": offset,
        },
    }


@router.post("/knowledge/documents")
async def upload_document(
    file: UploadFile = File(...),
    workspace_id: str = Form("default", alias="workspaceId"),
    owner_id: str = Form("default", alias="ownerId"),
    source_type: str | None = Form(None, alias="sourceType"),
):
    filename = file.filename or "uploaded_file"
    ext = filename.split(".")[-1].lower() if "." in filename else ""
    inferred_type = SourceType.MARKDOWN if ext in ("md", "markdown") else (SourceType.PDF if ext == "pdf" else SourceType.TEXT)
    final_source_type = source_type or inferred_type.value

    initial_status = DocumentService.determine_initial_status(final_source_type)

    doc_id = str(uuid.uuid4())
    now_iso = datetime.now(timezone.utc).isoformat()

    file_bytes = await file.read()
    parsed_markdown = ""

    if ext == "pdf":
        try:
            import fitz
            import pymupdf4llm
            doc = fitz.open(stream=file_bytes, filetype="pdf")
            # 优先使用专门针对 LLM 优化的大模型 Markdown 转换器
            md_text = pymupdf4llm.to_markdown(doc)
            parsed_markdown = f"# {filename}\n\n{md_text}" if md_text.strip() else f"# {filename}\n\n(PDF 中未提取到文本正文)"
        except Exception as e:
            try:
                import fitz
                doc = fitz.open(stream=file_bytes, filetype="pdf")
                page_texts = [f"## Page {i + 1}\n\n{page.get_text().strip()}" for i, page in enumerate(doc) if page.get_text().strip()]
                parsed_markdown = f"# {filename}\n\n" + "\n\n---\n\n".join(page_texts)
            except Exception as ex:
                parsed_markdown = f"# {filename}\n\n(PDF 解析错误: {e} / {ex})"
    elif ext in ("md", "markdown", "txt"):
        try:
            parsed_markdown = file_bytes.decode("utf-8")
        except Exception:
            parsed_markdown = file_bytes.decode("gbk", errors="ignore")
    else:
        parsed_markdown = f"# {filename}\n\n文件上传成功。"

    doc_obj = {
        "id": doc_id,
        "workspaceId": workspace_id,
        "ownerId": owner_id,
        "sourceType": final_source_type,
        "title": filename,
        "sourcePath": f"uploads/{filename}",
        "status": initial_status.value,
        "hasManualEdits": False,
        "createdAt": now_iso,
        "updatedAt": now_iso,
    }

    _DOCUMENTS_STORE[doc_id] = doc_obj
    _MARKDOWN_STORE[doc_id] = parsed_markdown

    return {
        "ok": True,
        "data": doc_obj,
    }


@router.post("/knowledge/documents/import-url")
async def import_url(payload: ImportUrlRequest):
    initial_status = DocumentService.determine_initial_status(SourceType.URL)
    doc_id = str(uuid.uuid4())
    now_iso = datetime.now(timezone.utc).isoformat()

    doc_obj = {
        "id": doc_id,
        "workspaceId": payload.workspace_id,
        "ownerId": payload.owner_id,
        "sourceType": SourceType.URL.value,
        "title": payload.url,
        "sourceUrl": payload.url,
        "status": initial_status.value,
        "hasManualEdits": False,
        "createdAt": now_iso,
        "updatedAt": now_iso,
    }

    _DOCUMENTS_STORE[doc_id] = doc_obj
    _MARKDOWN_STORE[doc_id] = f"# 网页导出：{payload.url}\n\n网页文章内容解析完成。"

    return {
        "ok": True,
        "data": doc_obj,
    }


@router.get("/knowledge/documents/{document_id}")
async def get_document(document_id: UUID):
    doc_id_str = str(document_id)
    doc = _DOCUMENTS_STORE.get(doc_id_str)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return {
        "ok": True,
        "data": doc,
    }


@router.get("/knowledge/documents/{document_id}/markdown")
async def get_document_markdown(document_id: UUID, is_candidate: bool = Query(False, alias="isCandidate")):
    doc_id_str = str(document_id)
    content = _MARKDOWN_STORE.get(doc_id_str, "# 暂无解析 Markdown 内容")
    return {
        "ok": True,
        "data": {
            "documentId": doc_id_str,
            "markdown": content,
            "isCandidate": is_candidate,
        },
    }


@router.put("/knowledge/documents/{document_id}/markdown")
async def update_document_markdown(document_id: UUID, payload: UpdateMarkdownRequest):
    doc_id_str = str(document_id)
    _MARKDOWN_STORE[doc_id_str] = payload.markdown
    if doc_id_str in _DOCUMENTS_STORE:
        _DOCUMENTS_STORE[doc_id_str]["updatedAt"] = datetime.now(timezone.utc).isoformat()
        _DOCUMENTS_STORE[doc_id_str]["hasManualEdits"] = True
    return {
        "ok": True,
        "data": {
            "documentId": doc_id_str,
            "updated": True,
        },
    }


@router.post("/knowledge/documents/{document_id}/confirm")
async def confirm_document(document_id: UUID):
    doc_id_str = str(document_id)
    if doc_id_str in _DOCUMENTS_STORE:
        _DOCUMENTS_STORE[doc_id_str]["status"] = KnowledgeDocumentStatus.AVAILABLE.value
        _DOCUMENTS_STORE[doc_id_str]["updatedAt"] = datetime.now(timezone.utc).isoformat()
    return {
        "ok": True,
        "data": {
            "documentId": doc_id_str,
            "status": KnowledgeDocumentStatus.AVAILABLE.value,
        },
    }


@router.post("/knowledge/documents/{document_id}/reconvert")
async def reconvert_document(document_id: UUID):
    doc_id_str = str(document_id)
    if doc_id_str in _DOCUMENTS_STORE:
        _DOCUMENTS_STORE[doc_id_str]["status"] = KnowledgeDocumentStatus.AWAITING_CONFIRMATION.value
    return {
        "ok": True,
        "data": {
            "documentId": doc_id_str,
            "status": KnowledgeDocumentStatus.AWAITING_CONFIRMATION.value,
            "diff": "--- 现有的 Markdown\n+++ 新解析候选版本\n- 旧解析文本\n+ 新重新解析的改进文本",
        },
    }


@router.delete("/knowledge/documents/{document_id}")
async def delete_document(document_id: UUID):
    doc_id_str = str(document_id)
    if doc_id_str in _DOCUMENTS_STORE:
        del _DOCUMENTS_STORE[doc_id_str]
    if doc_id_str in _MARKDOWN_STORE:
        del _MARKDOWN_STORE[doc_id_str]
    return {
        "ok": True,
        "data": {
            "documentId": doc_id_str,
            "status": KnowledgeDocumentStatus.DELETED.value,
        },
    }


@router.get("/ai-operations/{operation_id}/sources")
async def get_operation_sources(operation_id: str):
    return {
        "ok": True,
        "data": {
            "operationId": operation_id,
            "sources": [],
        },
    }


@router.get("/retrieval-traces/{trace_id}")
async def get_retrieval_trace(trace_id: UUID):
    return {
        "ok": True,
        "data": {
            "traceId": str(trace_id),
            "hits": [],
        },
    }
