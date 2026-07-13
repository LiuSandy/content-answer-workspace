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


class CreateChatRequest(BaseModel):
    title: str = "新对话"


class SendMessageRequest(BaseModel):
    content: str


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

        # 保存用户消息
        async with session_factory() as session:
            chat_service = ChatService(session)
            user_msg = await chat_service.save_user_message(chat_id, req.content, run_id=run_id)

        # 2. 准备 LangGraph 运行配置
        config = {"configurable": {"thread_id": chat_id_str}}
        inputs = {
            "chat_id": chat_id_str,
            "user_message_id": str(user_msg.id),
            "user_message": req.content,
            "messages": [{"role": "user", "content": req.content}],
        }

        assistant_content_parts = []
        
        try:
            # 3. 运行图并捕捉事件
            # version="v2" 是 langgraph.astream_events 所需参数
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
                    await chat_service.save_assistant_message(
                        chat_id=chat_id,
                        message_type="text",
                        content=full_text,
                        run_id=run_id,
                    )
                elif response_payload:
                    # 结构化卡片或错误
                    await chat_service.save_assistant_message(
                        chat_id=chat_id,
                        message_type=response_payload.message_type,
                        content=response_payload.text_content,
                        payload=response_payload.structured,
                        run_id=run_id,
                    )

                    # 发送 source_list 状态事件给前端
                    if response_payload.message_type == "source_list":
                        yield sse_named_event("source.list.completed", response_payload.structured)
                    elif response_payload.message_type == "error":
                        yield sse_named_event("run.failed", response_payload.structured)

            yield sse_named_event("run.completed", {"runId": run_id})

        except Exception as e:
            logger.error("Chat agent stream execution failed: %s", e)
            err_data = {"error_code": "agent_failed", "message": str(e)}
            
            # 尝试写入错误消息到数据库
            try:
                async with session_factory() as session:
                    chat_service = ChatService(session)
                    await chat_service.save_assistant_message(
                        chat_id=chat_id,
                        message_type="error",
                        content=None,
                        payload=err_data,
                        run_id=run_id,
                    )
            except Exception as db_err:
                logger.error("Failed to save error message to database: %s", db_err)

            yield sse_named_event("run.failed", err_data)

    return make_sse_response(_event_generator())
