"""Chat API 路由；处理 Chat 的增删改查和消息 SSE 流式调用。"""
from __future__ import annotations

import logging
import uuid
from typing import Any, AsyncIterator

from fastapi import APIRouter, Request, Query, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from langgraph.types import Command

from app.services.chat_service import ChatService
from app.agents._shared.runtime import run_agent_stream
from app.context import branch_thread_id, compose_run_inputs
from app.services.context.summary_updater import SummaryUpdater
from app.services.memory.extraction import run_memory_extraction
from app.infrastructure.database.session import get_db_session, get_session_factory
from app.api.streaming.sse import sse_named_event, make_sse_response
from app.config.runtime import AGENT_MAX_RECURSION, AGENT_RUN_TIMEOUT
from app.infrastructure.observability.context import reset_log_context, set_log_context

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chats", tags=["chats"])


async def _default_summarizer(content: str) -> str:
    """确定性本地压缩兜底：保留开头概况与末尾最新内容，避免无 LLM 配置时写入空摘要。

    生产可注入更强的 LLM 摘要器（app.state.summary_generator）。
    """
    text = "\n".join(line for line in content.splitlines() if line.strip())
    if len(text) <= 1400:
        return text
    head = text[:200].rstrip()
    tail = text[-1000:].lstrip()
    return f"{head}\n……（中间 {len(text) - 1200} 字符已压缩）\n{tail}"


def _get_summarizer(request: Request):
    return getattr(request.app.state, "summary_generator", None) or _default_summarizer


async def _update_branch_summary(session_factory, request: Request, chat_id, branch_root, leaf_message_id) -> None:
    """尽力更新分支滚动摘要（CAS）。任何失败只记日志，不阻断对话。"""
    if branch_root is None:
        return
    try:
        summarizer = _get_summarizer(request)
        async with session_factory() as session:
            chat_service = ChatService(session)
            full_path = await chat_service.get_message_path(chat_id, leaf_message_id)
            updater = SummaryUpdater(session, summarizer)
            existing = await updater.get(chat_id, branch_root)
            expected = existing.version if existing else 0
            await updater.update_incremental(chat_id, branch_root, full_path, expected_version=expected)
    except Exception as e:  # noqa: BLE001 - 摘要失败不阻断对话
        logger.warning("Branch summary update failed for chat %s: %s", chat_id, e)


def _branch_root_of(history_path: list) -> uuid.UUID | None:
    """分支根 = 分支路径的最早消息（get_message_path 已按时间升序返回）。"""
    return history_path[0].id if history_path else None


def _schedule_memory_extraction(user_message: str, assistant_text: str, run_id: str) -> None:
    """fire-and-forget 后台沉淀长期记忆（R5），不阻断 SSE 响应流。"""
    try:
        conversation = [
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": assistant_text},
        ]
        import asyncio as _asyncio
        _asyncio.create_task(
            run_memory_extraction(conversation, idempotency_key=run_id)
        )
    except Exception:  # noqa: BLE001
        pass


def build_langgraph_history(
    messages: list,
    current_user_message_id: str | None = None,
) -> list[dict]:
    """把 DB 历史消息转成 LangGraph 输入，排除刚保存的当前用户消息。

    当 leaf_message_id 为 None 时，get_message_path 会把最新消息（即刚保存的
    当前用户消息）当作叶子，历史路径因此包含它；这里按 id 排除，确保当前
    用户指令在每次图运行中只出现一次（由调用方在 messages 末尾追加一次）。
    """
    current_id = current_user_message_id
    history: list[dict] = []
    for m in messages:
        if current_id and str(m.id) == current_id:
            continue
        history.append({"role": m.role, "content": m.content or ""})
    return history


def _build_rag_payload(node_state: dict) -> dict | None:
    """从 retrieve_knowledge 节点输出构造 RAG 参考来源 payload。

    返回 None 表示该轮没有检索或检索无命中来源。
    payload 结构：
        sources: [{label, title, sourceType, sourceUrl, contentSnippet}]
        fallbackNotice: str | None
        traceId: str | None
    """
    retrieval = node_state.get("retrieval_result")
    trace_id = node_state.get("trace_id")
    if retrieval is None:
        return None

    has_evidence = getattr(retrieval, "has_evidence", False)
    sources = [
        {
            "label": s.get("label"),
            "title": s.get("title", "Unknown Document"),
            "sourceType": s.get("sourceType", "私有资料"),
            "sourceUrl": s.get("sourceUrl"),
            "contentSnippet": (s.get("text") or "")[:300],
        }
        for s in (getattr(retrieval, "sources", None) or [])
        if s.get("label")
    ]
    if has_evidence and sources:
        return {
            "sources": sources,
            "fallbackNotice": None,
            "traceId": trace_id,
        }
    if not has_evidence:
        return {
            "sources": [],
            "fallbackNotice": (
                getattr(retrieval, "fallback_reason", None)
                or "私有资料证据不足，使用了其他知识来源"
            ),
            "traceId": trace_id,
        }
    return None


def _current_turn_platform_tool_result(messages: list) -> tuple[list, str | None, str | None]:
    """读取当前用户轮次内最近的平台工具结果，绝不回收历史轮次结果。"""
    for message in reversed(messages):
        if getattr(message, "type", None) == "human":
            break
        if (
            getattr(message, "type", None) == "tool"
            and getattr(message, "name", None) in ("xiaohongshu_search", "zhihu_search")
        ):
            try:
                import json

                tool_data = json.loads(message.content)
            except (TypeError, json.JSONDecodeError) as exc:
                logger.warning("Failed to parse current-turn tool content: %s", exc)
                continue
            items = tool_data.get("items") if isinstance(tool_data, dict) else None
            if isinstance(items, list):
                return items, tool_data.get("platform", "xiaohongshu"), message.name
    return [], None, None


class CreateChatRequest(BaseModel):
    title: str = "新对话"


class SendMessageRequest(BaseModel):
    content: str
    parent_message_id: str | None = Field(default=None, alias="parentMessageId")

    model_config = {
        "populate_by_name": True,
    }


class RenameChatRequest(BaseModel):
    title: str


class SubmitChoiceRequest(BaseModel):
    messageId: str
    selection: str

    @field_validator("selection")
    @classmethod
    def _selection_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("selection must not be blank")
        return v

    model_config = {
        "populate_by_name": True,
    }


def _get_session_factory(request: Request):
    """优先使用 app.state 注入的 session 工厂（测试隔离用），否则用全局工厂。"""
    return getattr(request.app.state, "session_factory", None) or get_session_factory()


# ── REST API 端点 ────────────────────────────────────────────────────────────

@router.post("")
async def create_chat(req: CreateChatRequest, request: Request) -> JSONResponse:
    async for session in get_db_session():
        chat_service = ChatService(session)
        chat = await chat_service.create_chat(req.title)
        return JSONResponse(
            {
                "ok": True,
                "data": {
                    "chatId": str(chat.id),
                    "title": chat.title,
                    "createdAt": chat.created_at.isoformat(),
                },
            }
        )
    return JSONResponse({"ok": False, "error": "Internal database error"}, status_code=500)


@router.get("")
async def list_chats() -> JSONResponse:
    async for session in get_db_session():
        chat_service = ChatService(session)
        chats = await chat_service.list_chats()
        return JSONResponse(
            {
                "ok": True,
                "data": [
                    {
                        "chatId": str(c.id),
                        "title": c.title,
                        "updatedAt": c.updated_at.isoformat(),
                        "createdAt": c.created_at.isoformat(),
                    }
                    for c in chats
                ],
            }
        )
    return JSONResponse({"ok": False, "error": "Internal database error"}, status_code=500)


@router.get("/{chat_id}")
async def get_chat(chat_id: uuid.UUID) -> JSONResponse:
    async for session in get_db_session():
        chat_service = ChatService(session)
        chat = await chat_service.get_chat(chat_id)
        if not chat:
            return JSONResponse({"ok": False, "error": "Chat not found"}, status_code=404)
        return JSONResponse(
            {
                "ok": True,
                "data": {
                    "chatId": str(chat.id),
                    "title": chat.title,
                    "updatedAt": chat.updated_at.isoformat(),
                    "createdAt": chat.created_at.isoformat(),
                },
            }
        )
    return JSONResponse({"ok": False, "error": "Internal database error"}, status_code=500)


@router.delete("/{chat_id}")
async def delete_chat(chat_id: uuid.UUID) -> JSONResponse:
    async for session in get_db_session():
        chat_service = ChatService(session)
        deleted = await chat_service.delete_chat(chat_id)
        if not deleted:
            return JSONResponse({"ok": False, "error": "Chat not found"}, status_code=404)
        return JSONResponse({"ok": True, "data": {"deleted": True}})
    return JSONResponse({"ok": False, "error": "Internal database error"}, status_code=500)


@router.put("/{chat_id}")
async def rename_chat(chat_id: uuid.UUID, req: RenameChatRequest) -> JSONResponse:
    """重命名对话标题。"""
    async for session in get_db_session():
        chat_service = ChatService(session)
        chat = await chat_service.get_chat(chat_id)
        if not chat:
            return JSONResponse({"ok": False, "error": "Chat not found"}, status_code=404)
        chat.title = req.title
        chat_id_str = str(chat.id)
        title = chat.title
        updated_at_str = chat.updated_at.isoformat() if chat.updated_at else ""
        created_at_str = chat.created_at.isoformat() if chat.created_at else ""
        await session.commit()
        return JSONResponse(
            {
                "ok": True,
                "data": {
                    "chatId": chat_id_str,
                    "title": title,
                    "updatedAt": updated_at_str,
                    "createdAt": created_at_str,
                },
            }
        )
    return JSONResponse({"ok": False, "error": "Internal database error"}, status_code=500)


@router.get("/{chat_id}/messages")
async def get_messages(chat_id: uuid.UUID) -> JSONResponse:
    async for session in get_db_session():
        chat_service = ChatService(session)
        messages = await chat_service.get_messages(chat_id)
        return JSONResponse(
            {
                "ok": True,
                "data": [
                    {
                        "messageId": str(m.id),
                        "role": m.role,
                        "messageType": m.message_type,
                        "content": m.content,
                        "payload": m.payload,
                        "runId": m.run_id,
                        "parentMessageId": str(m.parent_message_id) if m.parent_message_id else None,
                        "createdAt": m.created_at.isoformat(),
                    }
                    for m in messages
                ],
            }
        )
    return JSONResponse({"ok": False, "error": "Internal database error"}, status_code=500)


# ── HITL 人工选择提交 ─────────────────────────────────────────────────────────

@router.post("/{chat_id}/choices")
async def submit_choice(
    chat_id: uuid.UUID,
    req: SubmitChoiceRequest,
    http_request: Request,
) -> Any:
    """用户提交 Human-in-the-loop 选择（spec §11.7）。

    校验 messageId 确为本 chat 的 choice_request 消息 → 幂等去重 →
    使用暂停时的分支 thread_id 与 Command(resume=...) 从 checkpoint 原位恢复，
    不重新执行意图识别或工具搜索。

    并发：同一 chat 同时最多 1 个续跑，被占用时返回 409。
    """
    chat_id_str = str(chat_id)
    graph = http_request.app.state.conversation_graph
    runtime = http_request.app.state.chat_runtime
    session_factory = _get_session_factory(http_request)

    async with session_factory() as session:
        chat_service = ChatService(session)
        if not await chat_service.get_chat(chat_id):
            return JSONResponse({"ok": False, "error": "Chat not found"}, status_code=404)

        choice_req = None
        for m in await chat_service.get_messages(chat_id):
            if m.message_type == "choice_request" and str(m.id) == req.messageId:
                choice_req = m
                break
        if choice_req is None:
            return JSONResponse({"ok": False, "error": "choice_request message not found"}, status_code=404)

        hitl_choice = choice_req.payload or {}
        allowed_options = {
            str(option.get("id"))
            for option in (hitl_choice.get("options") or [])
            if isinstance(option, dict) and option.get("id")
        }
        if allowed_options and req.selection not in allowed_options:
            return JSONResponse(
                {"ok": False, "error": "invalid choice selection"}, status_code=422
            )

        # 幂等：同一 choice_request + 同一 selection 已提交过则直接成功，不重复续跑
        existing = [
            m
            for m in await chat_service.get_messages(chat_id)
            if m.message_type == "hitl_selection"
            and m.parent_message_id == choice_req.id
            and (m.content or "").strip() == req.selection.strip()
        ]
        if existing:
            return JSONResponse({"ok": True, "data": {"ok": True, "alreadySubmitted": True}})

    # 每 chat 并发锁：已被占用则拒绝
    if not await runtime.try_acquire(chat_id_str):
        return JSONResponse(
            {
                "ok": False,
                "error": {
                    "code": "agent_busy",
                    "message": "该对话正在生成中，请稍后再试",
                },
            },
            status_code=409,
        )

    async with session_factory() as session:
        chat_service = ChatService(session)
        sel_msg = await chat_service.save_user_message(
            chat_id, req.selection, parent_message_id=choice_req.id, message_type="hitl_selection"
        )
        history_path = await chat_service.get_message_path(chat_id, choice_req.id)
        branch_root = _branch_root_of(history_path) or choice_req.id

    run_id = str(uuid.uuid4())
    inputs = Command(resume=req.selection)
    config = {"configurable": {"thread_id": branch_thread_id(chat_id_str, str(branch_root))}}
    config = {**config, "recursion_limit": AGENT_MAX_RECURSION}

    async def _generator() -> AsyncIterator[str]:
        parts: list[str] = []
        try:
            yield sse_named_event(
                "run.started", {"runId": run_id, "chatId": chat_id_str, "resumedFromChoice": True}
            )
            async for name, data in run_agent_stream(graph, inputs, config, timeout_seconds=AGENT_RUN_TIMEOUT):
                yield sse_named_event(name, data)
                if name == "message.delta":
                    parts.append(data["delta"])
            if parts:
                async with session_factory() as session:
                    await ChatService(session).save_assistant_message(
                        chat_id=chat_id,
                        message_type="text",
                        content="".join(parts),
                        payload=None,
                        parent_message_id=sel_msg.id,
                        run_id=run_id,
                    )
                await _update_branch_summary(session_factory, http_request, chat_id, branch_root, sel_msg.id)
            yield sse_named_event("run.completed", {"runId": run_id})
        finally:
            runtime.release(chat_id_str)

    return make_sse_response(_generator())


# ── SSE 实时流式对话 ──────────────────────────────────────────────────────────

@router.post("/{chat_id}/messages/stream")
async def send_message_stream(
    chat_id: uuid.UUID,
    req: SendMessageRequest,
    http_request: Request,
) -> Any:
    """用户发送消息，调用 LangGraph 意图路由与流式交互，并通过 SSE 实时推送回复。"""
    graph = http_request.app.state.conversation_graph
    session_factory = get_session_factory()

    async def _event_generator() -> AsyncIterator[str]:
        chat_id_str = str(chat_id)
        run_id = str(uuid.uuid4())

        # 1. 产生 run.started 事件
        yield sse_named_event("run.started", {"runId": run_id, "chatId": chat_id_str})

        # 解析 parent_message_id
        parent_id = None
        if req.parent_message_id:
            try:
                parent_id = uuid.UUID(req.parent_message_id)
            except ValueError:
                pass

        # 保存用户消息并获取历史路径
        async with session_factory() as session:
            chat_service = ChatService(session)
            
            # 若当前对话标题为默认的"新对话"，则自动以用户第一条提问的前20字作为标题
            chat = await chat_service.get_chat(chat_id)
            if chat and chat.title == "新对话":
                chat.title = req.content[:20]
                session.add(chat)
                
            user_msg = await chat_service.save_user_message(
                chat_id, req.content, parent_message_id=parent_id, run_id=run_id
            )
            history_path = await chat_service.get_message_path(chat_id, parent_id)
            branch_root = _branch_root_of(history_path) or user_msg.id
            # R4：读取分支级滚动摘要（尽力而为，缺失则本轮不注入）
            branch_summary = None
            try:
                updater = SummaryUpdater(session, _default_summarizer)
                bs = await updater.get(chat_id, branch_root)
                if bs and bs.summary:
                    branch_summary = bs.summary
            except Exception as e:  # noqa: BLE001
                logger.debug("Load branch summary failed: %s", e)

        # 格式化历史消息提供给 LangGraph
        langgraph_history = build_langgraph_history(history_path, str(user_msg.id))

        # R4：分支根稳定 thread_id + checkpoint 感知输入。
        # 已存在 checkpoint 的分支只传本轮增量，缺失时才从 DB 分支路径重建全量历史。
        extra: dict[str, Any] = {}
        if branch_summary:
            extra["branch_summary"] = branch_summary

        if hasattr(graph, "aget_state"):
            inputs, config = await compose_run_inputs(
                graph,
                chat_id_str,
                str(branch_root),
                langgraph_history,
                str(user_msg.id),
                req.content,
                extra=extra,
            )
        else:
            inputs = {
                "chat_id": chat_id_str,
                "user_message_id": str(user_msg.id),
                "user_message": req.content,
                **extra,
                "messages": langgraph_history + [{"role": "user", "content": req.content}],
            }
            config = {"configurable": {"thread_id": f"{chat_id_str}_{branch_root}"}}
        config = {**config, "recursion_limit": AGENT_MAX_RECURSION}

        assistant_content_parts = []
        summary_leaf: uuid.UUID | None = None
        assistant_text: str | None = None
        log_token = set_log_context(run_id=run_id, chat_id=chat_id_str)

        try:
            # 3. 运行图并捕捉事件（统一经 scheduling 封装：子图感知匹配 + 运行级超时）
            rag_payload: dict | None = None
            timeout_occurred = False
            async for name, data in run_agent_stream(graph, inputs, config, timeout_seconds=AGENT_RUN_TIMEOUT):
                if name in ("agent.status", "tool.started"):
                    yield sse_named_event(name, data)
                elif name in ("rag.sources", "rag.fallback"):
                    # RAG 检索结束：透传命中来源给前端（受 RAG_SOURCE_DISPLAY 开关控制）
                    from app.config.runtime import is_rag_source_display_enabled
                    if is_rag_source_display_enabled():
                        if name == "rag.sources":
                            rag_payload = {
                                "sources": data["sources"],
                                "fallbackNotice": None,
                                "traceId": data["traceId"],
                            }
                        else:
                            rag_payload = {
                                "sources": [],
                                "fallbackNotice": data["reason"],
                                "traceId": data["traceId"],
                            }
                        yield sse_named_event(name, data)
                elif name in ("task_plan.created", "multi_agent.status"):
                    yield sse_named_event(name, data)
                elif name == "message.delta":
                    assistant_content_parts.append(data["delta"])
                    yield sse_named_event("message.delta", data)
                elif name == "agent.error":
                    timeout_occurred = True
                    yield sse_named_event("agent.error", data)

            # 4. 执行结束，获取图当前状态的快照以持久化
            state = await graph.aget_state(config)
            values = state.values or {}
            
            intent = values.get("intent")
            response_payload = values.get("response_payload")

            async with session_factory() as session:
                chat_service = ChatService(session)

                if timeout_occurred:
                    # 运行超时：已有部分结果保留，另持久化一条稳定的错误终态消息
                    await chat_service.save_assistant_message(
                        chat_id=chat_id,
                        message_type="error",
                        content=None,
                        payload={
                            "error_code": "agent_timeout",
                            "message": "生成超时已自动停止，请换个说法重试",
                        },
                        parent_message_id=user_msg.id,
                        run_id=run_id,
                    )
                    return

                interrupts = [
                    item
                    for task in (getattr(state, "tasks", None) or [])
                    for item in (getattr(task, "interrupts", None) or [])
                ]
                hitl_choice = interrupts[0].value if interrupts else None

                if hitl_choice:
                    # Human-in-the-loop：本轮需要用户选择，保存 choice_request 消息并透传事件
                    await chat_service.save_assistant_message(
                        chat_id=chat_id,
                        message_type="choice_request",
                        content=hitl_choice.get("question", ""),
                        payload=hitl_choice,
                        parent_message_id=user_msg.id,
                        run_id=run_id,
                    )
                    yield sse_named_event("choice.requested", hitl_choice)
                    return
                elif intent == "chat" and assistant_content_parts:
                    # 普通对话，保存回复文本
                    full_text = "".join(assistant_content_parts)
                    msg_payload = {}
                    if rag_payload:
                        msg_payload["ragSources"] = rag_payload.get("sources") or []
                        msg_payload["ragFallback"] = rag_payload.get("fallbackNotice")
                        msg_payload["traceId"] = rag_payload.get("traceId")

                    # 确定性平台采集结果保存在独立 state 字段中，不写入 ToolMessage；
                    # 仍兼容读取普通 ReAct 工具调用产生的合法 ToolMessage。
                    messages_list = values.get("messages", [])
                    tool_items = []
                    tool_platform = None
                    tool_name = None

                    platform_result = values.get("platform_collect_result") or {}
                    if isinstance(platform_result, dict):
                        result_items = platform_result.get("items")
                        if isinstance(result_items, list):
                            tool_items = result_items
                            tool_platform = platform_result.get("platform")
                            tool_name = platform_result.get("tool_type")

                    if not tool_items:
                        tool_items, tool_platform, tool_name = _current_turn_platform_tool_result(
                            messages_list
                        )

                    if tool_items:
                        try:
                            from datetime import datetime as _dt
                            from app.contracts.dto import SourceItemDTO
                            dto_items = []
                            for i in tool_items:
                                ext_id = i.get("url") or i.get("link") or ""
                                published = None
                                raw_pub = i.get("published_at")
                                if raw_pub:
                                    try:
                                        published = _dt.fromisoformat(str(raw_pub).replace("Z", "+00:00"))
                                    except ValueError:
                                        published = None
                                metric = i.get("metric") or ""
                                likes_raw = i.get("likes") or 0
                                dto_items.append(
                                    SourceItemDTO(
                                        platform=tool_platform,
                                        external_id=ext_id,
                                        url=i.get("url") or i.get("link") or "",
                                        title=i.get("title") or "",
                                        content=i.get("excerpt") or i.get("summary") or "",
                                        author=i.get("author") or "",
                                        summary=i.get("excerpt") or i.get("summary") or "",
                                        metrics={"likes": metric or likes_raw},
                                        published_at=published,
                                    )
                                )

                            saved_items = await chat_service.save_source_items(chat_id, dto_items)

                            # 回填 ID
                            for dto, db_item in zip(dto_items, saved_items):
                                dto.id = db_item.id

                            serialized_items = []
                            for item in dto_items:
                                item_dict = item.model_dump(by_alias=True)
                                if item_dict.get("id"):
                                    item_dict["id"] = str(item_dict["id"])
                                if item_dict.get("publishedAt") is not None:
                                    item_dict["publishedAt"] = item_dict["publishedAt"].isoformat()
                                serialized_items.append(item_dict)

                            payload_data = {
                                "tool_type": tool_name,
                                "total_found": len(serialized_items),
                                "items": serialized_items
                            }

                            # 方案 1: 将采集到的卡片作为来源附件聚合在文本消息的 payload 中，避免产生平级分支覆盖冲突
                            msg_payload["sourceList"] = payload_data

                            # 在 SSE 流结束前，向前端追加产生一条 source_list 消息完成事件
                            yield sse_named_event("source.list.completed", payload_data)
                        except Exception as e:
                            logger.error("Failed to persist and yield source items from tool call: %s", e)

                    # 保存合并后的唯一助手消息 (方案 1: 单气泡聚合)
                    saved = await chat_service.save_assistant_message(
                        chat_id=chat_id,
                        message_type="text",
                        content=full_text,
                        payload=msg_payload if msg_payload else None,
                        parent_message_id=user_msg.id,
                        run_id=run_id,
                    )
                    summary_leaf = saved.id
                    assistant_text = full_text
                elif intent == "task_plan":
                    # 复合任务：从 state 取结果并落库为结构化消息
                    tp_result = values.get("task_plan_result") or {}
                    tp_saved = await chat_service.save_assistant_message(
                        chat_id=chat_id,
                        message_type="text",
                        content=tp_result.get("preview") or "复合任务已完成",
                        payload={"taskPlanResult": tp_result},
                        parent_message_id=user_msg.id,
                        run_id=run_id,
                    )
                    summary_leaf = tp_saved.id
                    assistant_text = tp_result.get("preview") or "复合任务已完成"
                elif intent == "multi_agent":
                    # 多 Agent 协作：从 state 取结果并落库为结构化消息
                    ma_result = values.get("multi_agent_result") or {}
                    ma_saved = await chat_service.save_assistant_message(
                        chat_id=chat_id,
                        message_type="text",
                        content=ma_result.get("finalContent") or "多 Agent 协作已完成",
                        payload={"multiAgentResult": ma_result},
                        parent_message_id=user_msg.id,
                        run_id=run_id,
                    )
                    summary_leaf = ma_saved.id
                    assistant_text = ma_result.get("finalContent") or "多 Agent 协作已完成"
                elif response_payload:
                    # 字典安全兼容处理：适配反序列化降级为 dict 的情况
                    if isinstance(response_payload, dict):
                        p_msg_type = response_payload.get("message_type", "text")
                        p_content = response_payload.get("text_content")
                        p_structured = response_payload.get("structured")
                    else:
                        p_msg_type = getattr(response_payload, "message_type", "text")
                        p_content = getattr(response_payload, "text_content", None)
                        p_structured = getattr(response_payload, "structured", None)

                    rp_saved = await chat_service.save_assistant_message(
                        chat_id=chat_id,
                        message_type=p_msg_type,
                        content=p_content,
                        payload=p_structured,
                        parent_message_id=user_msg.id,
                        run_id=run_id,
                    )
                    summary_leaf = rp_saved.id
                    assistant_text = p_content or ""

                    # 发送 source_list 状态事件给前端
                    if p_msg_type == "source_list":
                        yield sse_named_event("source.list.completed", p_structured)
                    elif p_msg_type == "error":
                        yield sse_named_event("run.failed", p_structured)

            # R4：尽力更新分支滚动摘要（下一轮注入 composer 上下文）
            if summary_leaf is not None:
                await _update_branch_summary(session_factory, http_request, chat_id, branch_root, summary_leaf)

            # R5：对话完成后后台沉淀长期记忆（幂等键=run_id，不阻断 SSE 响应）
            if assistant_text is not None:
                _schedule_memory_extraction(req.content, assistant_text, run_id)

            yield sse_named_event("run.completed", {"runId": run_id})

        except Exception as e:
            logger.exception("Chat agent stream execution failed")
            if type(e).__name__ == "GraphRecursionError" or "recursion" in str(e).lower():
                err_data = {
                    "error_code": "agent_recursion_limit",
                    "message": f"本轮处理步骤过多已自动停止（上限 {AGENT_MAX_RECURSION} 步）。请换个更明确的说法重试。",
                }
            else:
                err_data = {"error_code": "agent_failed", "message": "对话执行失败，请稍后重试"}
            
            # 尝试写入错误消息到数据库
            try:
                async with session_factory() as session:
                    chat_service = ChatService(session)
                    await chat_service.save_assistant_message(
                        chat_id=chat_id,
                        message_type="error",
                        content=None,
                        payload=err_data,
                        parent_message_id=user_msg.id,
                        run_id=run_id,
                    )
            except Exception as db_err:
                logger.error("Failed to save error message to database: %s", db_err)

            yield sse_named_event("run.failed", err_data)
        finally:
            reset_log_context(log_token)

    return make_sse_response(_event_generator())
