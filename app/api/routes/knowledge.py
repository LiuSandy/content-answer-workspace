from uuid import UUID
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query, BackgroundTasks
from pydantic import BaseModel, ConfigDict, Field

from app.domain.knowledge import KnowledgeDocumentStatus, SourceType
from app.application.knowledge.document_service import DocumentService

router = APIRouter(prefix="/api", tags=["knowledge"])


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
    # 第一版返回成功的数据包装
    return {
        "ok": True,
        "data": {
            "documents": [],
            "total": 0,
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

    return {
        "ok": True,
        "data": {
            "id": "00000000-0000-0000-0000-000000000000",
            "title": filename,
            "sourceType": final_source_type,
            "status": initial_status.value,
            "workspaceId": workspace_id,
            "ownerId": owner_id,
        },
    }


@router.post("/knowledge/documents/import-url")
async def import_url(payload: ImportUrlRequest):
    initial_status = DocumentService.determine_initial_status(SourceType.URL)
    return {
        "ok": True,
        "data": {
            "id": "00000000-0000-0000-0000-000000000000",
            "title": payload.url,
            "sourceType": SourceType.URL.value,
            "sourceUrl": payload.url,
            "status": initial_status.value,
            "workspaceId": payload.workspace_id,
        },
    }


@router.get("/knowledge/documents/{document_id}")
async def get_document(document_id: UUID):
    return {
        "ok": True,
        "data": {
            "id": str(document_id),
            "title": "Document Title",
            "status": "available",
        },
    }


@router.get("/knowledge/documents/{document_id}/markdown")
async def get_document_markdown(document_id: UUID, is_candidate: bool = Query(False, alias="isCandidate")):
    return {
        "ok": True,
        "data": {
            "documentId": str(document_id),
            "markdown": "# Markdown Content\n\nSample content.",
            "isCandidate": is_candidate,
        },
    }


@router.put("/knowledge/documents/{document_id}/markdown")
async def update_document_markdown(document_id: UUID, payload: UpdateMarkdownRequest):
    return {
        "ok": True,
        "data": {
            "documentId": str(document_id),
            "updated": True,
        },
    }


@router.post("/knowledge/documents/{document_id}/confirm")
async def confirm_document(document_id: UUID):
    return {
        "ok": True,
        "data": {
            "documentId": str(document_id),
            "status": KnowledgeDocumentStatus.INDEXING.value,
        },
    }


@router.post("/knowledge/documents/{document_id}/reconvert")
async def reconvert_document(document_id: UUID):
    return {
        "ok": True,
        "data": {
            "documentId": str(document_id),
            "status": KnowledgeDocumentStatus.AWAITING_CONFIRMATION.value,
            "diff": "--- Original\n+++ Candidate\n- Old text\n+ New text",
        },
    }


@router.delete("/knowledge/documents/{document_id}")
async def delete_document(document_id: UUID):
    return {
        "ok": True,
        "data": {
            "documentId": str(document_id),
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
