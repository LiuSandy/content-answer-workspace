"""Chat API 路由；处理 Chat 的增删改查和消息 SSE 流式调用。"""
from __future__ import annotations

import logging
import uuid
from typing import Any, AsyncIterator

from fastapi import APIRouter, Request, Query, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ...application.chat_service import ChatService
from ...persistence.session import get_db_session, get_session_factory
from ..sse_utils import sse_named_event, make_sse_response

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chats", tags=["chats"])


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

        # 格式化历史消息提供给 LangGraph
        langgraph_history = []
        for m in history_path:
            # 仅传递有文本内容的 user/assistant 消息以保持上下文紧凑
            langgraph_history.append({"role": m.role, "content": m.content or ""})

        # 2. 准备 LangGraph 运行配置
        # 使用当前用户消息 ID 作为 thread_id 隔离分支
        config = {"configurable": {"thread_id": f"{chat_id_str}_{user_msg.id}"}}
        inputs = {
            "chat_id": chat_id_str,
            "user_message_id": str(user_msg.id),
            "user_message": req.content,
            "messages": langgraph_history + [{"role": "user", "content": req.content}],
        }

        assistant_content_parts = []
        
        try:
            # 3. 运行图并捕捉事件
            # version="v2" 是 langgraph.astream_events 所需参数
            rag_payload: dict | None = None
            async for event in graph.astream_events(inputs, config, version="v2"):
                kind = event.get("event")
                name = event.get("name")

                if kind == "on_node_start":
                    if name == "route_intent":
                        yield sse_named_event("agent.status", {"status": "routing_intent"})
                    elif name == "chat":
                        yield sse_named_event("agent.status", {"status": "generating"})
                    elif name == "parse_url":
                        yield sse_named_event("tool.started", {"tool_type": "parse_url"})
                    elif name == "collect":
                        yield sse_named_event("tool.started", {"tool_type": "collect"})

                elif kind == "on_chain_end" and (event.get("metadata") or {}).get("langgraph_node") == "retrieve_knowledge":
                    # RAG 检索结束：透传命中来源给前端（受 RAG_SOURCE_DISPLAY 开关控制）
                    from app.core.config import is_rag_source_display_enabled
                    if is_rag_source_display_enabled():
                        node_state = (event.get("data") or {}).get("output")
                        if not isinstance(node_state, dict):
                            node_state = {}
                        built = _build_rag_payload(node_state)
                        if built is not None:
                            rag_payload = built
                            if built["sources"]:
                                yield sse_named_event("rag.sources", {
                                    "sources": built["sources"],
                                    "traceId": built["traceId"],
                                })
                            else:
                                yield sse_named_event("rag.fallback", {
                                    "reason": built["fallbackNotice"],
                                    "traceId": built["traceId"],
                                })

                elif kind == "on_chain_end" and (event.get("metadata") or {}).get("langgraph_node") == "task_plan":
                    # 复合任务规划执行结束：透传 plan 概要给前端展示卡片
                    node_state = (event.get("data") or {}).get("output")
                    if isinstance(node_state, dict) and node_state.get("task_plan_result"):
                        tp = node_state["task_plan_result"]
                        yield sse_named_event("task_plan.created", {
                            "planId": tp.get("planId"),
                            "goal": tp.get("goal"),
                            "status": tp.get("status"),
                            "preview": tp.get("preview"),
                        })

                elif kind == "on_chain_end" and (event.get("metadata") or {}).get("langgraph_node") == "multi_agent":
                    # 多 Agent 协作结束：透传 5 个子 Agent 状态给前端展示
                    node_state = (event.get("data") or {}).get("output")
                    if isinstance(node_state, dict) and node_state.get("multi_agent_result"):
                        ma = node_state["multi_agent_result"]
                        yield sse_named_event("multi_agent.status", {
                            "status": ma.get("status"),
                            "agents": ma.get("agents", []),
                            "finalContent": ma.get("finalContent"),
                        })

                elif kind == "on_chat_model_stream":
                    data = event.get("data", {})
                    chunk = data.get("chunk")
                    if chunk and hasattr(chunk, "content") and chunk.content:
                        delta = chunk.content
                        assistant_content_parts.append(delta)
                        yield sse_named_event("message.delta", {"delta": delta})

            # 4. 执行结束，获取图当前状态的快照以持久化
            state = await graph.aget_state(config)
            values = state.values or {}
            
            intent = values.get("intent")
            response_payload = values.get("response_payload")

            async with session_factory() as session:
                chat_service = ChatService(session)

                if intent == "chat" and assistant_content_parts:
                    # 普通对话，保存回复文本
                    full_text = "".join(assistant_content_parts)
                    msg_payload = {}
                    if rag_payload:
                        msg_payload["ragSources"] = rag_payload.get("sources") or []
                        msg_payload["ragFallback"] = rag_payload.get("fallbackNotice")
                        msg_payload["traceId"] = rag_payload.get("traceId")
                    await chat_service.save_assistant_message(
                        chat_id=chat_id,
                        message_type="text",
                        content=full_text,
                        payload=msg_payload if msg_payload else None,
                        parent_message_id=user_msg.id,
                        run_id=run_id,
                    )

                    # 检查大模型在此轮对话中是否运行了 zhihu_search 或 xiaohongshu_search 工具
                    # 若运行了，解析并将其持久化为 source_list 消息，从而支持前端结构化卡片与左键选中写作
                    messages_list = values.get("messages", [])
                    tool_items = []
                    tool_platform = None
                    tool_name = None

                    for m in reversed(messages_list):
                        if hasattr(m, "type") and m.type == "tool" and m.name in ("xiaohongshu_search", "zhihu_search"):
                            try:
                                import json
                                tool_data = json.loads(m.content)
                                if isinstance(tool_data, dict) and "items" in tool_data:
                                    tool_items = tool_data["items"]
                                    tool_platform = tool_data.get("platform", "xiaohongshu")
                                    tool_name = m.name
                                    break
                            except Exception as e:
                                logger.warning("Failed to parse tool content: %s", e)

                    if tool_items:
                        try:
                            from datetime import datetime as _dt
                            from ...domain.dto import SourceItemDTO
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

                            await chat_service.save_assistant_message(
                                chat_id=chat_id,
                                message_type="source_list",
                                content="为您搜索采集到以下主题帖子：",
                                payload=payload_data,
                                parent_message_id=user_msg.id,
                                run_id=run_id,
                            )
                            # 在 SSE 流结束前，向前端追加产生一条 source_list 消息完成事件
                            yield sse_named_event("source.list.completed", payload_data)
                        except Exception as e:
                            logger.error("Failed to persist and yield source items from tool call: %s", e)
                elif intent == "task_plan":
                    # 复合任务：从 state 取结果并落库为结构化消息
                    tp_result = values.get("task_plan_result") or {}
                    await chat_service.save_assistant_message(
                        chat_id=chat_id,
                        message_type="text",
                        content=tp_result.get("preview") or "复合任务已完成",
                        payload={"taskPlanResult": tp_result},
                        parent_message_id=user_msg.id,
                        run_id=run_id,
                    )
                elif intent == "multi_agent":
                    # 多 Agent 协作：从 state 取结果并落库为结构化消息
                    ma_result = values.get("multi_agent_result") or {}
                    await chat_service.save_assistant_message(
                        chat_id=chat_id,
                        message_type="text",
                        content=ma_result.get("finalContent") or "多 Agent 协作已完成",
                        payload={"multiAgentResult": ma_result},
                        parent_message_id=user_msg.id,
                        run_id=run_id,
                    )
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

                    await chat_service.save_assistant_message(
                        chat_id=chat_id,
                        message_type=p_msg_type,
                        content=p_content,
                        payload=p_structured,
                        parent_message_id=user_msg.id,
                        run_id=run_id,
                    )

                    # 发送 source_list 状态事件给前端
                    if p_msg_type == "source_list":
                        yield sse_named_event("source.list.completed", p_structured)
                    elif p_msg_type == "error":
                        yield sse_named_event("run.failed", p_structured)

            yield sse_named_event("run.completed", {"runId": run_id})

        except Exception as e:
            logger.error("Chat agent stream execution failed: %s", e)
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

    return make_sse_response(_event_generator())
