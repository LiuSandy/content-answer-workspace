from __future__ import annotations

import json
from collections.abc import AsyncIterator

from fastapi.responses import StreamingResponse


def sse_event(payload: dict) -> str:
    """将字典序列化为 SSE data 行格式。"""
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def make_sse_response(gen: AsyncIterator[str]) -> StreamingResponse:
    """将异步生成器包装为 SSE StreamingResponse。"""
    return StreamingResponse(
        gen,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
