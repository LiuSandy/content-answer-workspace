from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from fastapi import APIRouter, Header, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from ...api.sse_utils import make_sse_response, sse_event, sse_named_event
from ...application.agent.graphs.analysis import get_analysis_graph
from ...application.agent.graphs.refinement import build_refinement_graph
from ...application.agent.collect_results import extract_collect_result
from ...application.agent.process_steps import tool_end_step, tool_start_step
from ...application.agent.session_adapter import InMemorySessionAdapter
from ...application.agent.state import AgentState
from ...application.agent.tools import ALL_TOOLS
from ...application.chat_conversation_run_service import (
    TERMINAL_STATUSES as CHAT_RUN_TERMINAL_STATUSES,
    ChatConversationRunService,
    ChatSseEvent,
)
from ...infrastructure.llm.deepseek_client import DeepSeekAnswerGenerator
from ...services.hotlist_service import fetch_hotlist
from ...services.session_service import update_session_title

router = APIRouter()

_answer_gen = DeepSeekAnswerGenerator()
_chat_run_service = ChatConversationRunService()
_CHAT_RUN_NOT_FOUND_MESSAGE = "对话运行不存在或已过期，请重新发送"

_ANALYSIS_SYSTEM_PROMPT = """
你是内容策略分析师。分析知乎热榜数据，严格按以下 JSON 格式输出：
{
  "topicDistribution": [{"field": "领域", "count": N, "examples": ["标题"]}],
  "contentOpportunities": [{"direction": "方向", "reason": "理由"}],
  "audienceMood": "情绪基调",
  "recommendations": [{"topic": "选题", "reason": "理由", "keywords": ["词"]}]
}
只返回 JSON，不要其他说明。
""".strip()


@router.get("/api/agent/tools")
async def list_agent_tools() -> JSONResponse:
    """返回当前已启用的 Agent 工具清单（名称+描述）；供聊天输入框的工具按钮只读展示。"""
    tools = [{"name": tool.name, "description": (tool.description or "").strip()} for tool in ALL_TOOLS]
    return JSONResponse({"ok": True, "data": tools})


class AgentChatRequest(BaseModel):
    sessionId: str
    questionId: str | None = None
    message: str
    currentAnswer: str | None = None

    model_config = {"populate_by_name": True}


@router.post("/api/agent/chat")
async def agent_chat(request: AgentChatRequest) -> JSONResponse:
    """接收 AI 精修或热榜分析请求；根据 questionId 是否存在路由到对应 Graph。"""
    initial_state: AgentState = {
        "session_id": request.sessionId,
        "question_id": request.questionId,
        "user_message": request.message,
        "current_answer": None,
        "hotlist_items": None,
        "reply": "",
        "answer_updated": False,
        "updated_answer": None,
        "operation_summary": "",
    }

    if request.questionId:
        session_svc = InMemorySessionAdapter(
            initial_answers={(request.sessionId, request.questionId): request.currentAnswer or ""}
        )
        graph = build_refinement_graph(session_svc)
        final_state = await graph.ainvoke(initial_state)
        updated_answer = session_svc.get_updated_answer(request.sessionId, request.questionId)
    else:
        graph = get_analysis_graph()
        final_state = await graph.ainvoke(initial_state)
        updated_answer = None

    return JSONResponse({
        "reply": final_state.get("reply", ""),
        "answerUpdated": final_state.get("answer_updated", False),
        "updatedAnswer": updated_answer,
        "operationSummary": final_state.get("operation_summary", ""),
    })


class ConversationRequest(BaseModel):
    sessionId: str
    message: str

    model_config = {"populate_by_name": True}


def set_chat_conversation_run_service(service: ChatConversationRunService) -> None:
    """替换路由使用的 chat run service；测试可以注入无后台执行的内存实例。"""

    global _chat_run_service
    _chat_run_service = service


@router.post("/api/agent/conversation")
async def agent_conversation(request: ConversationRequest, http_request: Request) -> JSONResponse:
    """对话页面专用接口；调用独立的 ConversationGraph，不影响精修/分析两个现有 Graph。"""

    graph = http_request.app.state.conversation_graph
    config = {"configurable": {"thread_id": request.sessionId}}
    existing_state = await graph.aget_state(config)
    is_first_message = not existing_state.values.get("messages")

    result = await graph.ainvoke(
        {"messages": [{"role": "user", "content": request.message}]},
        config=config,
    )
    reply = result["messages"][-1].content

    if is_first_message:
        update_session_title(request.sessionId, request.message[:20])

    return JSONResponse({"ok": True, "data": {"reply": reply}})


@router.post("/api/agent/conversation/runs")
async def create_conversation_run(request: ConversationRequest, http_request: Request) -> JSONResponse:
    try:
        run = await _chat_run_service.create_run(request.sessionId, request.message)
    except ValueError as error:
        return JSONResponse(
            {"ok": False, "error": {"message": str(error)}},
            status_code=400,
        )
    _chat_run_service.start_conversation_run(
        run.id,
        http_request.app.state.conversation_graph,
        update_session_title,
    )
    return JSONResponse({"ok": True, "data": {"runId": run.id, "status": run.status}})


@router.get("/api/agent/conversation/runs/{run_id}")
async def get_conversation_run(run_id: str) -> JSONResponse:
    snapshot = _chat_run_service.get_run_snapshot(run_id)
    if snapshot is None:
        return _chat_run_not_found_response()
    return JSONResponse({"ok": True, "data": snapshot})


@router.get("/api/agent/conversation/runs/{run_id}/stream")
async def stream_conversation_run(
    run_id: str,
    last_event_id_query: int | None = Query(default=None, alias="lastEventId"),
    last_event_id_header: str | None = Header(default=None, alias="Last-Event-ID"),
) -> StreamingResponse:
    last_event_id = _parse_last_event_id(last_event_id_header, last_event_id_query)

    async def _gen() -> AsyncIterator[str]:
        if _chat_run_service.get_run(run_id) is None:
            yield sse_named_event(
                "chat_error",
                {"message": _CHAT_RUN_NOT_FOUND_MESSAGE},
            )
            return

        current_id = last_event_id
        while True:
            replayed = _chat_run_service.replay_events(run_id, current_id)
            for event in replayed:
                current_id = max(current_id, event.id)
                yield _format_chat_run_event(event)
                if event.event in {"done", "chat_error", "canceled"}:
                    return

            run = _chat_run_service.get_run(run_id)
            if run is None or run.status in CHAT_RUN_TERMINAL_STATUSES:
                return

            try:
                events = await _chat_run_service.wait_for_event(run_id, current_id, timeout=15.0)
            except asyncio.TimeoutError:
                yield sse_named_event("heartbeat", {})
                continue

            if not events:
                yield sse_named_event("heartbeat", {})

    return make_sse_response(_gen())


@router.delete("/api/agent/conversation/runs/{run_id}")
async def cancel_conversation_run(run_id: str) -> JSONResponse:
    try:
        run = await _chat_run_service.cancel_run(run_id)
    except KeyError:
        return _chat_run_not_found_response()
    return JSONResponse({"ok": True, "data": {"runId": run.id, "status": run.status}})


@router.get("/api/agent/conversation/{session_id}/history")
async def agent_conversation_history(session_id: str, http_request: Request) -> JSONResponse:
    """读取指定会话的完整对话历史；供前端进入对话页面时首次渲染消息流。"""

    graph = http_request.app.state.conversation_graph
    config = {"configurable": {"thread_id": session_id}}
    state = await graph.aget_state(config)
    messages = _build_history_messages(state.values.get("messages", []))
    return JSONResponse({"ok": True, "data": {"messages": messages}})


def _build_history_messages(raw_messages: list) -> list[dict]:
    """把 LangGraph 持久化的消息流重建成前端消息列表；
    单独定义是因为 ReAct 历史里混有工具调用与工具结果，需要把它们折叠成一条 tool 过程消息，
    并把采集工具结果附着到最终 assistant 消息，保证历史与实时渲染一致。"""

    result: list[dict] = []
    pending_steps: list[str] = []
    pending_collect_results: list[dict] = []

    def flush_pending_without_reply() -> None:
        """在没有最终回答时落入 pending 状态；采集结果优先成为 assistant 任务消息。"""
        nonlocal pending_steps, pending_collect_results
        if pending_collect_results:
            message: dict = {
                "role": "assistant",
                "content": "",
                "collectResults": pending_collect_results,
            }
            if pending_steps:
                message["steps"] = pending_steps
            result.append(message)
        elif pending_steps:
            result.append({"role": "tool", "content": "", "steps": pending_steps})
        pending_steps = []
        pending_collect_results = []

    def append_assistant(content: str) -> None:
        """追加 assistant 消息；如果有采集结果，把它们作为同一条任务消息的结构化数据。"""
        nonlocal pending_steps, pending_collect_results
        if pending_collect_results:
            message: dict = {
                "role": "assistant",
                "content": content,
                "collectResults": pending_collect_results,
            }
            if pending_steps:
                message["steps"] = pending_steps
            result.append(message)
        else:
            if pending_steps:
                result.append({"role": "tool", "content": "", "steps": pending_steps})
            pending_steps = []
            result.append({"role": "assistant", "content": content})
            return

        pending_steps = []
        pending_collect_results = []

    for message in raw_messages:
        mtype = getattr(message, "type", "")
        if mtype == "human":
            flush_pending_without_reply()
            result.append({"role": "user", "content": message.content})
        elif mtype == "tool":
            tool_name = getattr(message, "name", "")
            pending_steps.append(tool_end_step(tool_name))
            collect_result = extract_collect_result(tool_name, message)
            if collect_result is not None:
                pending_collect_results.append(collect_result)
        elif mtype == "ai":
            tool_calls = getattr(message, "tool_calls", None) or []
            if tool_calls:
                for call in tool_calls:
                    name = call.get("name", "") if isinstance(call, dict) else getattr(call, "name", "")
                    pending_steps.append(tool_start_step(name))
            elif message.content:
                append_assistant(message.content)
        # system 等其它类型不展示

    flush_pending_without_reply()
    return result


def _chat_run_not_found_response() -> JSONResponse:
    return JSONResponse(
        {"ok": False, "error": {"message": _CHAT_RUN_NOT_FOUND_MESSAGE}},
        status_code=404,
    )


def _format_chat_run_event(event: ChatSseEvent) -> str:
    return sse_named_event(event.event, event.data, event.id)


def _parse_last_event_id(header_value: str | None, query_value: int | None) -> int:
    raw = header_value if header_value not in (None, "") else query_value
    if raw in (None, ""):
        return 0
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return 0


@router.post("/api/agent/conversation/stream")
async def agent_conversation_stream(request: ConversationRequest, http_request: Request) -> StreamingResponse:
    """对话页面流式接口；使用 LangGraph astream_events 逐 token 推送模型回复。"""

    async def _gen() -> AsyncIterator[str]:
        try:
            graph = http_request.app.state.conversation_graph
            config = {"configurable": {"thread_id": request.sessionId}}
            existing_state = await graph.aget_state(config)
            is_first_message = not existing_state.values.get("messages")
            full_reply = ""
            async for event in graph.astream_events(
                {"messages": [{"role": "user", "content": request.message}]},
                config=config,
                version="v2",
            ):
                kind = event["event"]
                if kind == "on_tool_start":
                    yield sse_event({"type": "tool_start", "text": tool_start_step(event.get("name", ""))})
                elif kind == "on_tool_end":
                    tool_name = event.get("name", "")
                    yield sse_event({"type": "tool_end", "text": tool_end_step(tool_name)})
                    collect_result = extract_collect_result(
                        tool_name,
                        (event.get("data") or {}).get("output", ""),
                    )
                    if collect_result is not None:
                        yield sse_event({"type": "collect_result", **collect_result})
                elif kind == "on_chat_model_stream":
                    chunk = event["data"].get("chunk")
                    if chunk and hasattr(chunk, "content") and chunk.content:
                        full_reply += chunk.content
                        yield sse_event({"type": "chunk", "text": chunk.content})

            if is_first_message:
                update_session_title(request.sessionId, request.message[:20])

            yield sse_event({"type": "done", "data": {"reply": full_reply}})
        except Exception as e:  # noqa: BLE001
            yield sse_event({"type": "error", "message": str(e)})

    return make_sse_response(_gen())


@router.post("/api/agent/chat/stream")
async def agent_chat_stream(request: AgentChatRequest) -> StreamingResponse:
    """精修/热榜分析流式接口；refinement 流式输出修改后的回答，analysis 流式输出分析 JSON。"""

    async def _gen() -> AsyncIterator[str]:
        try:
            if request.questionId:
                # 精修模式：流式输出修改后的回答文本
                current_answer = request.currentAnswer or ""
                instruction = request.message
                prompt = "\n".join([
                    "请严格按照用户指令修改以下回答。",
                    "只改动用户指定的部分，其余内容保持原样，不要自行发挥。",
                    "",
                    f"用户指令：{instruction}",
                    "",
                    "当前回答：",
                    current_answer,
                ])
                full_answer = ""
                async for chunk in _answer_gen.call_raw_stream(
                    system="你是专业的内容编辑助手。",
                    user=prompt,
                ):
                    full_answer += chunk
                    yield sse_event({"type": "chunk", "text": chunk})

                short = instruction[:30]
                yield sse_event({
                    "type": "done",
                    "data": {
                        "reply": "已按您的要求完成修改。",
                        "answerUpdated": True,
                        "updatedAnswer": full_answer.strip(),
                        "operationSummary": f"修改：{short}",
                    },
                })
            else:
                # 分析模式：先获取热榜，再流式输出分析
                hotlist_response = await fetch_hotlist(limit=30)
                items = [item.model_dump(by_alias=True) for item in hotlist_response.items]
                lines = [
                    f"{item['rank']}. {item['title']}（热度：{item['heat']}）\n   {item.get('summary', '')}"
                    for item in items
                ]
                user_prompt = f"以下是当前知乎热榜 {len(items)} 条内容：\n\n" + "\n".join(lines)
                full_reply = ""
                async for chunk in _answer_gen.call_raw_stream(
                    system=_ANALYSIS_SYSTEM_PROMPT,
                    user=user_prompt,
                ):
                    full_reply += chunk
                    yield sse_event({"type": "chunk", "text": chunk})

                yield sse_event({
                    "type": "done",
                    "data": {
                        "reply": full_reply.strip(),
                        "answerUpdated": False,
                        "updatedAnswer": None,
                        "operationSummary": "热榜分析",
                    },
                })
        except Exception as e:  # noqa: BLE001
            yield sse_event({"type": "error", "message": str(e)})

    return make_sse_response(_gen())
