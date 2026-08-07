"""普通对话节点：进行普通多轮对话。"""
from __future__ import annotations

import os
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI

from ....prompts.registry import prompt_registry
from ...context.composer import ContextComposer, SimpleContextProfile
from ..state import ChatAgentState

from ..tools import ALL_TOOLS


def _get_chat_llm() -> ChatOpenAI:
    llm = ChatOpenAI(
        api_key=os.getenv("DEEPSEEK_API_KEY", ""),
        base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").strip().rstrip("/"),
        model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
        streaming=True,
    )
    # 绑定对话中支持的工具
    return llm.bind_tools(ALL_TOOLS)


def _resolve_context_profile() -> SimpleContextProfile:
    """读取模型 profile 的 context_window / output_reserve_tokens；缺失时用默认值。"""
    try:
        entry = prompt_registry.get_model_profile("default")
        if entry and entry.context_window:
            return SimpleContextProfile(
                context_window=entry.context_window,
                output_reserve_tokens=entry.output_reserve_tokens or 4096,
            )
    except Exception:  # noqa: BLE001 - profile 缺失不阻断对话
        pass
    return SimpleContextProfile()


def _serialize_message(msg) -> dict:
    """把 LangChain message 转成 composer 可估算的 {role, content}。"""
    role = getattr(msg, "type", "assistant")
    if role == "human":
        role = "user"
    elif role == "system":
        role = "system"
    elif role == "tool":
        role = "tool"
    else:
        role = "assistant"
    return {"role": role, "content": msg.content or ""}


def _rebuild_message(role: str, content: str):
    if role == "user":
        return HumanMessage(content=content)
    if role == "system":
        return SystemMessage(content=content)
    if role == "tool":
        return ToolMessage(content=content, tool_call_id="composed")
    return AIMessage(content=content)


def _bound_messages(raw_messages: list, system_content: str, summary: str | None) -> tuple[list, dict]:
    """在模型输入预算内组装消息（roadmap R4）。

    预算内时原样透传 LangChain 消息对象（零行为变化）；超预算才裁剪最旧消息、
    截断最近消息。返回 (langchain_messages, composer_meta)。
    """
    if not raw_messages:
        return [SystemMessage(content=system_content)], {
            "kept": 0,
            "dropped": 0,
            "budget": 0,
            "totalTokens": 0,
        }

    composer = ContextComposer(_resolve_context_profile())
    serialized = [_serialize_message(m) for m in raw_messages]
    ids = [f"m{i}" for i in range(len(raw_messages))]
    composed = composer.assemble(
        serialized,
        system_prompt=system_content,
        summary=summary,
        message_ids=ids,
    )

    final: list = []
    for idx, item in zip(composed.kept_indices, composed.messages):
        original = raw_messages[idx]
        if (original.content or "") == item["content"]:
            final.append(original)
        else:
            final.append(_rebuild_message(item["role"], item["content"]))

    meta = {
        "kept": len(composed.messages),
        "dropped": composed.dropped,
        "budget": composed.budget,
        "totalTokens": composed.total_tokens(),
        "truncated": composed.truncated_message_ids,
    }
    return [SystemMessage(content=system_content)] + final, meta


_llm: ChatOpenAI | None = None


async def chat_node(state: ChatAgentState) -> dict:
    global _llm
    if _llm is None:
        _llm = _get_chat_llm()

    # 从 Prompt Registry 加载系统 Prompt
    try:
        rendered = prompt_registry.render("chat.system")
        system_content = rendered.messages[0].content
    except Exception:
        system_content = "你是一个内容创作助手，帮助用户从平台发现优质帖子，并为其创作高质量回答。"

    retrieval_result = state.get("retrieval_result")
    if retrieval_result and getattr(retrieval_result, "has_evidence", False):
        grounded_context = f"\n\n【私有资料上下文】\n{getattr(retrieval_result, 'context_text', '')}\n\n请在回答中使用 [S1]、[S2] 等标签引用对应资料，且只能引用上述资料中实际存在的内容。"
        system_content = system_content + grounded_context
    elif retrieval_result and not getattr(retrieval_result, "has_evidence", False):
        fallback_notice = "\n\n【提示】私有资料库中没有找到足够的相关证据，本回答将基于通用知识作答。"
        system_content = system_content + fallback_notice

    # Phase 4 长期记忆注入：spec 3.3 让 Agent 体现用户偏好
    applied = state.get("applied_memories") or []
    if applied:
        memories_block = "\n\n【用户长期偏好（已应用 {} 条记忆）】\n".format(len(applied))
        for i, m in enumerate(applied, 1):
            memories_block += f"[M{i}] ({m.get('memory_type')}) {m.get('content')}\n"
        memories_block += "\n请在回答中体现上述偏好；不要直接引用 [Mx] 标签。"
        system_content = system_content + memories_block

    # R4 分支滚动摘要注入：压缩后的历史上下文，供长对话续接
    branch_summary = state.get("branch_summary")
    if branch_summary:
        system_content = (
            system_content
            + f"\n\n【此前对话摘要（用于续接上下文，忽略其中的过时细节）】\n{branch_summary}\n"
        )

    messages, composer_meta = _bound_messages(list(state.get("messages", [])), system_content, branch_summary)
    response = await _llm.ainvoke(messages)
    return {"messages": [response], "composer_meta": composer_meta}
