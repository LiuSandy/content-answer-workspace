"""分支 checkpoint 续跑输入组装（roadmap R4）。

thread_id 以「分支根消息」为稳定键：同一分支的后续运行复用同一 checkpoint，
只向图传入本轮增量（当前用户消息），避免 DB 历史与 checkpoint 消息双重累积。
缺失 checkpoint 的分支才从 DB 分支路径重建完整历史。
"""
from __future__ import annotations

import uuid
from typing import Any


def branch_thread_id(chat_id: str, branch_root_message_id: str) -> str:
    """分支稳定 thread_id：{chat_id}_{branch_root_message_id}。"""
    return f"{chat_id}_{branch_root_message_id}"


async def compose_run_inputs(
    graph: Any,
    chat_id: str,
    branch_root_message_id: str,
    branch_messages: list[dict[str, str]],
    current_user_message_id: str,
    current_user_message: str,
    extra: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """根据分支 checkpoint 是否存在，决定本轮图输入。

    返回 (inputs, config)。inputs 内 messages 遵循：
    - 已有 checkpoint：只含当前用户消息（增量），由 LangGraph 合并进既有分支；
    - 无 checkpoint：完整分支历史 + 当前用户消息。
    """
    config = {"configurable": {"thread_id": branch_thread_id(chat_id, branch_root_message_id)}}
    snapshot = await graph.aget_state(config)
    has_checkpoint = bool(snapshot and snapshot.values and snapshot.values.get("messages"))

    base: dict[str, Any] = {
        "chat_id": str(chat_id),
        "user_message_id": str(current_user_message_id),
        "user_message": current_user_message,
    }
    if extra:
        base.update(extra)

    if has_checkpoint:
        base["messages"] = [{"role": "user", "content": current_user_message}]
        base["resumed_from_checkpoint"] = True
    else:
        base["messages"] = branch_messages + [
            {"role": "user", "content": current_user_message}
        ]
        base["resumed_from_checkpoint"] = False

    return base, config
