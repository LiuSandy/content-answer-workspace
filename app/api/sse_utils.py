from __future__ import annotations

import json
from collections.abc import AsyncIterator

from fastapi.responses import StreamingResponse


def sse_event(payload: dict) -> str:
    """将字典序列化为 SSE data 行格式。"""
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def sse_named_event(event: str, data: dict, event_id: int | None = None) -> str:
    """将事件序列化为标准 SSE id/event/data 格式；供可恢复 job 流使用。"""

    lines: list[str] = []
    if event_id is not None:
        lines.append(f"id: {event_id}")
    lines.append(f"event: {event}")
    lines.append(f"data: {json.dumps(data, ensure_ascii=False)}")
    return "\n".join(lines) + "\n\n"


def make_sse_response(gen: AsyncIterator[str]) -> StreamingResponse:
    """将异步生成器包装为 SSE StreamingResponse。"""
    return StreamingResponse(
        gen,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
