from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from ...api.sse_utils import make_sse_response, sse_event
from ...application.workflow_service import WorkflowService, normalize_platform
from ...core.config import get_workflow_config, load_env_file
from ...infrastructure.llm.deepseek_client import DeepSeekAnswerGenerator
from ...models import PolishPayload, RegeneratePayload, SessionPayload
from ...services.image_service import GeneratedImagePayload, ImageGenerationService

router = APIRouter(prefix="/api/workflow", tags=["stream"])

_answer_generator = DeepSeekAnswerGenerator()
_image_service = ImageGenerationService()
workflow_service = WorkflowService()


@router.post("/generate-one/stream")
async def generate_one_stream(payload: RegeneratePayload) -> StreamingResponse:
    """流式生成单条回答；逐 token 推送，完成后以 done 事件携带完整问题对象。"""

    async def _gen() -> AsyncIterator[str]:
        try:
            load_env_file()
            platform = normalize_platform(payload.platform or payload.item.platform)
            item = payload.item.model_copy(update={"platform": platform})
            config = get_workflow_config(
                {
                    "platform": platform,
                    "answerStyle": payload.answer_style,
                    "systemPrompt": payload.system_prompt,
                    "generationPrompt": payload.generation_prompt,
                }
            )
            full_text = ""
            async for chunk in _answer_generator.generate_answer_stream(
                item,
                payload.answer_style or config.answer_style,
                config.cta_text,
                payload.system_prompt or config.system_prompt,
                payload.generation_prompt or config.generation_prompt,
                payload.content_constraint or None,
            ):
                full_text += chunk
                yield _sse({"type": "chunk", "text": chunk})

            try:
                images = await _image_service.generate_images_for_answer(item, full_text)
            except ValueError as e:
                if "Missing required env: IMAGE_" not in str(e):
                    raise
                images = GeneratedImagePayload(images=[], imagePrompts=[])

            final_item = item.model_copy(
                update={
                    "answer": full_text.strip(),
                    "images": images.get("images", []),
                    "image_prompts": images.get("imagePrompts", []),
                }
            )
            yield _sse({"type": "done", "data": {"item": final_item.model_dump(by_alias=True)}})
        except Exception as e:  # noqa: BLE001
            yield _sse({"type": "error", "message": str(e)})

    return _make_sse_response(_gen())


@router.post("/polish-one/stream")
async def polish_one_stream(payload: PolishPayload) -> StreamingResponse:
    """流式润色单条回答；逐 token 推送，完成后以 done 事件携带完整问题对象。"""

    async def _gen() -> AsyncIterator[str]:
        try:
            load_env_file()
            platform = normalize_platform(payload.platform or payload.item.platform)
            item = payload.item.model_copy(update={"platform": platform})
            config = get_workflow_config(
                {
                    "platform": platform,
                    "answerStyle": payload.answer_style,
                    "systemPrompt": payload.system_prompt,
                    "generationPrompt": payload.generation_prompt,
                }
            )
            full_text = ""
            async for chunk in _answer_generator.polish_answer_stream(
                item,
                payload.current_answer,
                payload.answer_style or config.answer_style,
                config.cta_text,
                payload.system_prompt or config.system_prompt,
                payload.generation_prompt or config.generation_prompt,
                payload.content_constraint or None,
            ):
                full_text += chunk
                yield _sse({"type": "chunk", "text": chunk})

            final_item = item.model_copy(update={"answer": full_text.strip()})
            yield _sse({"type": "done", "data": {"item": final_item.model_dump(by_alias=True)}})
        except Exception as e:  # noqa: BLE001
            yield _sse({"type": "error", "message": str(e)})

    return _make_sse_response(_gen())


@router.post("/generate/stream")
async def generate_stream(payload: SessionPayload) -> StreamingResponse:
    """批量流式生成回答；每条问题依次发 item_start → chunk* → item_done，全部完成后发 all_done。"""

    async def _gen() -> AsyncIterator[str]:
        try:
            load_env_file()
            platform = normalize_platform(payload.platform)
            config = get_workflow_config(
                {
                    "platform": platform,
                    "answerStyle": payload.answer_style,
                    "systemPrompt": payload.system_prompt,
                    "generationPrompt": payload.generation_prompt,
                }
            )
            done_items = []
            for raw_item in payload.items:
                item = raw_item.model_copy(
                    update={"platform": normalize_platform(raw_item.platform or platform)}
                )
                yield _sse({"type": "item_start", "itemId": item.id})
                full_text = ""
                async for chunk in _answer_generator.generate_answer_stream(
                    item,
                    payload.answer_style or config.answer_style,
                    config.cta_text,
                    payload.system_prompt or config.system_prompt,
                    payload.generation_prompt or config.generation_prompt,
                    payload.content_constraint or None,
                ):
                    full_text += chunk
                    yield _sse({"type": "chunk", "itemId": item.id, "text": chunk})

                try:
                    images = await _image_service.generate_images_for_answer(item, full_text)
                except ValueError as e:
                    if "Missing required env: IMAGE_" not in str(e):
                        raise
                    images = GeneratedImagePayload(images=[], imagePrompts=[])

                final_item = item.model_copy(
                    update={
                        "answer": full_text.strip(),
                        "images": images.get("images", []),
                        "image_prompts": images.get("imagePrompts", []),
                    }
                )
                done_items.append(final_item)
                yield _sse({"type": "item_done", "itemId": item.id, "item": final_item.model_dump(by_alias=True)})

            yield _sse({"type": "done", "data": {"items": [i.model_dump(by_alias=True) for i in done_items]}})
        except Exception as e:  # noqa: BLE001
            yield _sse({"type": "error", "message": str(e)})

    return _make_sse_response(_gen())
