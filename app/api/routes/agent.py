from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ...application.agent.graphs.analysis import get_analysis_graph
from ...application.agent.graphs.refinement import build_refinement_graph
from ...application.agent.session_adapter import InMemorySessionAdapter
from ...application.agent.state import AgentState

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
