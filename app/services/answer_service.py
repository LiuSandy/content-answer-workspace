from __future__ import annotations

from openai import OpenAI

from ..infrastructure.llm.deepseek_client import DeepSeekAnswerGenerator
from ..models import QuestionItem
from .image_service import GeneratedImagePayload, ImageGenerationService

_answer_generator = DeepSeekAnswerGenerator()
_image_generation_service = ImageGenerationService()


def get_openai_client() -> OpenAI:
    """返回 DeepSeek 的 OpenAI 兼容客户端；这样旧函数名可以兼容现有导入同时复用新适配器。"""

    return _answer_generator.get_client()


async def generate_answer(
    item: QuestionItem,
    answer_style: str,
    cta_text: str,
    system_prompt: str,
    generation_prompt: str,
) -> str:
    """为单个问题生成回答；这样旧服务调用可以继续使用统一的 DeepSeek 回答生成器。"""

    return await _answer_generator.generate_answer(item, answer_style, cta_text, system_prompt, generation_prompt)


async def generate_answer_with_images(
    item: QuestionItem,
    answer_style: str,
    cta_text: str,
    system_prompt: str,
    generation_prompt: str,
) -> tuple[str, GeneratedImagePayload]:
    """为问题同时生成回答和真实图片；这样前端可以一次拿到正文和配图，而不需要额外手工补图。"""

    answer = await generate_answer(item, answer_style, cta_text, system_prompt, generation_prompt)
    try:
        images = await _image_generation_service.generate_images_for_answer(item, answer)
    except ValueError as error:
        if "Missing required env: IMAGE_" not in str(error):
            raise
        images = GeneratedImagePayload(images=[], imagePrompts=[])
    return answer, images
