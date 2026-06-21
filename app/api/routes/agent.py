from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ...application.agent.graphs.analysis import get_analysis_graph
from ...application.agent.graphs.refinement import build_refinement_graph
from ...application.agent.session_adapter import InMemorySessionAdapter
from ...application.agent.state import AgentState
from ...services.session_service import update_session_title

router = APIRouter()


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


@router.get("/api/agent/conversation/{session_id}/history")
async def agent_conversation_history(session_id: str, http_request: Request) -> JSONResponse:
    """读取指定会话的完整对话历史；供前端进入对话页面时首次渲染消息流。"""

    graph = http_request.app.state.conversation_graph
    config = {"configurable": {"thread_id": session_id}}
    state = await graph.aget_state(config)
    role_map = {"human": "user", "ai": "assistant", "system": "system"}
    messages = [
        {"role": role_map.get(message.type, "user"), "content": message.content}
        for message in state.values.get("messages", [])
    ]
    return JSONResponse({"ok": True, "data": {"messages": messages}})
