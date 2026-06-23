from __future__ import annotations

import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from ...application.agent.graphs.analysis import get_analysis_graph
from ...application.agent.graphs.refinement import build_refinement_graph
from ...application.agent.session_adapter import InMemorySessionAdapter
from ...application.agent.state import AgentState
from ...infrastructure.llm.deepseek_client import DeepSeekAnswerGenerator
from ...services.hotlist_service import fetch_hotlist
from ...services.session_service import update_session_title

router = APIRouter()

_answer_gen = DeepSeekAnswerGenerator()

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


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _make_sse_response(gen: AsyncIterator[str]) -> StreamingResponse:
    return StreamingResponse(
        gen,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


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
                if event["event"] == "on_chat_model_stream":
                    chunk = event["data"].get("chunk")
                    if chunk and hasattr(chunk, "content") and chunk.content:
                        full_reply += chunk.content
                        yield _sse({"type": "chunk", "text": chunk.content})

            if is_first_message:
                update_session_title(request.sessionId, request.message[:20])

            yield _sse({"type": "done", "data": {"reply": full_reply}})
        except Exception as e:  # noqa: BLE001
            yield _sse({"type": "error", "message": str(e)})

    return _make_sse_response(_gen())


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
                    yield _sse({"type": "chunk", "text": chunk})

                short = instruction[:30]
                yield _sse({
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
                    yield _sse({"type": "chunk", "text": chunk})

                yield _sse({
                    "type": "done",
                    "data": {
                        "reply": full_reply.strip(),
                        "answerUpdated": False,
                        "updatedAnswer": None,
                        "operationSummary": "热榜分析",
                    },
                })
        except Exception as e:  # noqa: BLE001
            yield _sse({"type": "error", "message": str(e)})

    return _make_sse_response(_gen())
