"""普通对话节点：进行普通多轮对话。"""
from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from app.bootstrap.container import get_llm_gateway
from app.platform.prompts.registry import prompt_registry
from app.shared.ports import LLMProvider
from app.shared.llm.dto import AgentLLMRequest
from app.modules.conversation.application.context_composer import ContextComposer, SimpleContextProfile
from app.modules.conversation.agent.state import ChatAgentState

from app.plugins.tools.builtin import ALL_TOOLS


def _get_chat_provider() -> LLMProvider | None:
    """Legacy injection seam retained for isolated graph tests."""

    return None


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


def _drop_orphaned_tool_messages(messages: list) -> tuple[list, int]:
    """移除没有对应 assistant tool_calls 的 ToolMessage。

    旧版确定性平台采集节点曾把工具结果直接写成 ToolMessage，导致后续轮次
    发送给 OpenAI-compatible API 时违反工具消息协议。这里同时防止上下文裁剪
    把合法工具调用的 assistant 前置消息裁掉。
    """
    cleaned: list = []
    pending_tool_call_ids: set[str] = set()
    dropped = 0
    for message in messages:
        if isinstance(message, AIMessage):
            pending_tool_call_ids = {
                str(call.get("id"))
                for call in (message.tool_calls or [])
                if isinstance(call, dict) and call.get("id")
            }
            cleaned.append(message)
            continue
        if isinstance(message, ToolMessage):
            tool_call_id = str(message.tool_call_id or "")
            if tool_call_id and tool_call_id in pending_tool_call_ids:
                cleaned.append(message)
                pending_tool_call_ids.discard(tool_call_id)
            else:
                dropped += 1
            continue
        pending_tool_call_ids.clear()
        cleaned.append(message)
    return cleaned, dropped


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

    final, dropped_orphaned_tools = _drop_orphaned_tool_messages(final)
    meta = {
        "kept": len(composed.messages),
        "dropped": composed.dropped,
        "budget": composed.budget,
        "totalTokens": composed.total_tokens(),
        "truncated": composed.truncated_message_ids,
        "droppedOrphanedTools": dropped_orphaned_tools,
    }
    return [SystemMessage(content=system_content)] + final, meta


async def chat_node(
    state: ChatAgentState,
    *,
    provider: LLMProvider | None = None,
) -> dict:
    provider = provider or _get_chat_provider()
    # 从 Prompt Registry 加载系统 Prompt
    try:
        rendered = prompt_registry.render("chat.system")
        system_content = rendered.messages[0].content
    except Exception:
        rendered = None
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
    if provider is not None:
        response = await provider.ainvoke(messages, ALL_TOOLS)
    else:
        normalized = await get_llm_gateway().invoke_with_tools(
            purpose="conversation.chat",
            request=AgentLLMRequest(
                messages=messages,
                tools=ALL_TOOLS,
                provider=rendered.provider if rendered else None,
                model=rendered.model if rendered else None,
            ),
        )
        response = AIMessage(
            content=normalized.content,
            tool_calls=[
                {
                    "name": call.name,
                    "args": call.arguments,
                    "id": call.id or f"call_{index}",
                    "type": "tool_call",
                }
                for index, call in enumerate(normalized.tool_calls)
            ],
        )
    return {"messages": [response], "composer_meta": composer_meta}
