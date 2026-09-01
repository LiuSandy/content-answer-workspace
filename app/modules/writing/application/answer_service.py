from __future__ import annotations

from app.modules.writing.application.answer_generator import AnswerGenerationService
from app.modules.acquisition.domain.workflow import QuestionItem
from app.modules.documents.application.images import GeneratedImagePayload, ImageGenerationService

_answer_generator = AnswerGenerationService()
_image_generation_service = ImageGenerationService()


async def generate_answer(
    item: QuestionItem,
    answer_style: str,
    cta_text: str,
    system_prompt: str,
    generation_prompt: str,
    content_constraint: str | None = None,
) -> str:
    """为单个问题生成回答；这样旧服务调用可以继续使用统一的 DeepSeek 回答生成器。"""

    return await _answer_generator.generate_answer(item, answer_style, cta_text, system_prompt, generation_prompt, content_constraint)


async def polish_answer(
    item: QuestionItem,
    current_answer: str,
    answer_style: str,
    cta_text: str,
    system_prompt: str,
    generation_prompt: str,
    content_constraint: str | None = None,
) -> str:
    """对已有回答进行润色改写；这样调用方不需要直接依赖 DeepSeek 适配器。"""

    return await _answer_generator.polish_answer(item, current_answer, answer_style, cta_text, system_prompt, generation_prompt, content_constraint)


async def generate_answer_with_images(
    item: QuestionItem,
    answer_style: str,
    cta_text: str,
    system_prompt: str,
    generation_prompt: str,
    content_constraint: str | None = None,
) -> tuple[str, GeneratedImagePayload]:
    """为问题同时生成回答和真实图片；这样前端可以一次拿到正文和配图，而不需要额外手工补图。"""

    answer = await generate_answer(item, answer_style, cta_text, system_prompt, generation_prompt, content_constraint)
    try:
        images = await _image_generation_service.generate_images_for_answer(item, answer)
    except ValueError as error:
        if "Missing required env: IMAGE_" not in str(error):
            raise
        images = GeneratedImagePayload(images=[], imagePrompts=[])
    return answer, images
