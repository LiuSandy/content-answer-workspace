"""Human-in-the-loop 决策节点：检测工具结果中的约束冲突，决定是否请求用户选择。

通用机制：任何工具在返回中带 conflict 字段（请求量 > 实际满足量），本节点
生成一条 choice_request 消息并置 hitl_pending，作为本轮终态等待用户选择。
用户选择回传后，下一轮 Agent 结合 hitl_selection 与上下文快照继续执行。
"""
from __future__ import annotations

import json
import logging
import uuid

from langchain_core.messages import AIMessage

from ..state import ChatAgentState

logger = logging.getLogger(__name__)


def _find_conflict(messages: list) -> dict | None:
    """在最近的工具消息中查找带 conflict 字段的结果。

    返回工具数据里的 conflict 子对象，并补上 items（供上下文快照），或 None。
    """
    for m in reversed(messages or []):
        if not hasattr(m, "type") or m.type != "tool":
            continue
        content = getattr(m, "content", "")
        if not isinstance(content, str):
            continue
        try:
            data = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(data, dict) and data.get("conflict"):
            conflict = dict(data["conflict"])
            conflict.setdefault("topic", data.get("topic", ""))
            conflict.setdefault("items", data.get("items", []))
            return conflict
    return None


def _build_choice_message(conflict: dict) -> AIMessage:
    """根据冲突信息构造 choice_request 消息。

    conflict 为工具返回中的 conflict 子对象：
      {"requested": 5, "total_found": 1, "filtered_out": 4, "topic": "…", "items": […]}
    """
    requested = conflict.get("requested", 5)
    total_found = conflict.get("total_found", 0)
    filtered_out = conflict.get("filtered_out", 0)
    topic = conflict.get("topic") or conflict.get("reason") or ""

    payload = {
        "type": "choice_request",
        "question": (
            f"搜索到 {total_found} 条满足条件的结果（{requested} 条中），"
            f"有 {filtered_out} 条因不满足约束被排除。你想怎么处理？"
        ),
        "options": [
            {
                "id": "use_found",
                "label": f"就用这 {total_found} 条",
                "description": f"接受当前 {total_found} 条结果，不再追加",
            },
            {
                "id": "relax",
                "label": "放宽条件凑满",
                "description": f"放宽约束重新搜索，凑满 {requested} 条",
            },
            {
                "id": "change_keyword",
                "label": "换个关键词重试",
                "description": "换一个搜索词重新采集",
            },
        ],
        "context": {
            "topic": topic,
            "requested": requested,
            "total_found": total_found,
            "filtered_out": filtered_out,
            "results": conflict.get("items", [])[:requested],
        },
    }
    msg = AIMessage(content=json.dumps(payload, ensure_ascii=False))
    return msg


async def hitl_decision_node(state: ChatAgentState) -> dict:
    """检查最近的工具结果是否有冲突；有则发出选择请求并置 hitl_pending。"""
    messages = state.get("messages") or []
    conflict = _find_conflict(messages)
    if conflict is None:
        # 无冲突，正常结束
        return {"hitl_pending": False, "hitl_choice": None}

    msg = _build_choice_message(conflict)
    payload = json.loads(msg.content)
    return {
        "messages": [msg],
        "hitl_pending": True,
        "hitl_choice": payload,
    }
