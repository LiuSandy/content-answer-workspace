from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import JSONResponse, StreamingResponse

from ...api.sse_utils import make_sse_response, sse_named_event
from ...application.generation_job_service import GenerationJobService, SseJobEvent, TERMINAL_STATUSES
from ...models import RegeneratePayload

router = APIRouter(prefix="/api/workflow", tags=["generation-jobs"])
_generation_job_service = GenerationJobService()


def set_generation_job_service(service: GenerationJobService) -> None:
    """替换路由使用的 job service；测试可以注入无自动启动的内存实例。"""

    global _generation_job_service
    _generation_job_service = service


@router.post("/generate-one/jobs")
async def create_generate_one_job(payload: RegeneratePayload) -> JSONResponse:
    try:
        job = await _generation_job_service.create_generate_one_job(payload)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return JSONResponse({"ok": True, "data": {"jobId": job.id, "status": job.status}})


@router.get("/generate-one/jobs/{job_id}")
async def get_generate_one_job(job_id: str) -> JSONResponse:
    snapshot = _generation_job_service.get_job_snapshot(job_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="任务不存在或已过期，可重新生成")
    return JSONResponse({"ok": True, "data": snapshot})


@router.get("/generate-one/jobs/{job_id}/stream")
async def stream_generate_one_job(
    job_id: str,
    last_event_id_query: int | None = Query(default=None, alias="lastEventId"),
    last_event_id_header: str | None = Header(default=None, alias="Last-Event-ID"),
) -> StreamingResponse:
    if _generation_job_service.get_job(job_id) is None:
        raise HTTPException(status_code=404, detail="任务不存在或已过期，可重新生成")
    last_event_id = _parse_last_event_id(last_event_id_header, last_event_id_query)

    async def _gen() -> AsyncIterator[str]:
        current_id = last_event_id
        while True:
            replayed = _generation_job_service.replay_events(job_id, current_id)
            for event in replayed:
                current_id = max(current_id, event.id)
                yield _format_event(event)
                if event.event in {"done", "job_error", "canceled"}:
                    return

            job = _generation_job_service.get_job(job_id)
            if job is None or job.status in TERMINAL_STATUSES:
                return

            try:
                events = await _generation_job_service.wait_for_events(job_id, current_id, timeout=15.0)
            except TimeoutError:
                heartbeat = await _generation_job_service.heartbeat(job_id)
                yield sse_named_event("heartbeat", heartbeat)
                continue
            except asyncio.TimeoutError:
                heartbeat = await _generation_job_service.heartbeat(job_id)
                yield sse_named_event("heartbeat", heartbeat)
                continue

            if not events:
                continue

    return make_sse_response(_gen())


@router.delete("/generate-one/jobs/{job_id}")
async def cancel_generate_one_job(job_id: str) -> JSONResponse:
    try:
        job = await _generation_job_service.cancel_job(job_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="任务不存在或已过期，可重新生成") from error
    return JSONResponse({"ok": True, "data": {"jobId": job.id, "status": job.status}})


def _format_event(event: SseJobEvent) -> str:
    return sse_named_event(event.event, event.data, event.id)


def _parse_last_event_id(header_value: str | None, query_value: int | None) -> int:
    raw = header_value if header_value not in (None, "") else query_value
    if raw in (None, ""):
        return 0
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return 0
