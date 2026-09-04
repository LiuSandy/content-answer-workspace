"""Progress events exposed by the Writer Graph's direct document stream."""
from __future__ import annotations

from typing import Any

from langgraph.config import get_stream_writer


_LABELS = {
    "guard": "正在进行安全检查",
    "retrieve_memory": "正在召回写作偏好",
    "generate_plan": "正在制定创作计划",
    "assign_tasks": "创作计划已完成，正在分配任务",
    "research": "正在研究相关资料",
    "generate_outline": "正在生成文章大纲",
    "write": "正在根据大纲生成正文",
    "review": "正在进行质量评审",
    "memory": "正在整理创作偏好",
    "finalize": "正在保存最终文章",
}


def emit_progress(state: dict[str, Any], phase: str, status: str = "started", **data: Any) -> None:
    if not state.get("direct_stream"):
        return
    payload = {
        "phase": phase,
        "status": status,
        "label": _LABELS.get(phase, "正在处理创作任务"),
        **data,
    }
    get_stream_writer()({"event": "writer.progress", "data": payload})


__all__ = ["emit_progress"]
