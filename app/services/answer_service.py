from __future__ import annotations

from openai import OpenAI

from ..infrastructure.llm.deepseek_client import DeepSeekAnswerGenerator
from ..models import QuestionItem

_answer_generator = DeepSeekAnswerGenerator()


def get_openai_client() -> OpenAI:
    """返回 DeepSeek 的 OpenAI 兼容客户端；这样旧函数名可以兼容现有导入同时复用新适配器。"""

    return _answer_generator.get_client()


async def generate_answer(item: QuestionItem, answer_style: str, cta_text: str, system_prompt: str) -> str:
    """为单个问题生成回答；这样旧服务调用可以继续使用统一的 DeepSeek 回答生成器。"""

    return await _answer_generator.generate_answer(item, answer_style, cta_text, system_prompt)
