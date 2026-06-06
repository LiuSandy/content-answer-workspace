from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ...core.config import get_workflow_config
from ...models import RegeneratePayload, RunPayload, SessionPayload
from ...services.answer_service import generate_answer
from ...services.zhihu_service import collect_questions

router = APIRouter(prefix="/api/workflow", tags=["workflow"])


@router.post("/collect")
async def collect(payload: RunPayload) -> JSONResponse:
    result = await collect_questions(payload.model_dump(by_alias=True))
    return JSONResponse({"ok": True, "data": result.model_dump(by_alias=True)})


@router.post("/generate-one")
async def generate_one(payload: RegeneratePayload) -> JSONResponse:
    config = get_workflow_config()
    answer = await generate_answer(
        payload.item,
        payload.answer_style or config.answer_style,
        config.cta_text,
        payload.system_prompt or config.system_prompt,
    )
    return JSONResponse({"ok": True, "data": {"answer": answer}})


@router.post("/generate")
async def generate(payload: SessionPayload) -> JSONResponse:
    config = get_workflow_config(
        {
            "answerStyle": payload.answer_style,
            "systemPrompt": payload.system_prompt,
        }
    )
    items = []
    for item in payload.items:
        answer = await generate_answer(
            item,
            payload.answer_style or config.answer_style,
            config.cta_text,
            payload.system_prompt or config.system_prompt,
        )
        items.append(item.model_copy(update={"answer": answer}))
    return JSONResponse({"ok": True, "data": {"items": [item.model_dump(by_alias=True) for item in items]}})
