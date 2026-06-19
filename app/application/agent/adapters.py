from __future__ import annotations

from ...infrastructure.llm.deepseek_client import DeepSeekAnswerGenerator
from ...services.hotlist_service import fetch_hotlist


class DeepSeekLLMAdapter:
    """将 DeepSeekAnswerGenerator 适配为 LLMClientPort。"""

    def __init__(self) -> None:
        self._gen = DeepSeekAnswerGenerator()

    async def refine(self, instruction: str, current_answer: str) -> str:
        prompt = "\n".join([
            "请严格按照用户指令修改以下回答。",
            "只改动用户指定的部分，其余内容保持原样，不要自行发挥。",
            "",
            f"用户指令：{instruction}",
            "",
            "当前回答：",
            current_answer,
        ])
        return await self._gen.call_raw(
            system="你是专业的内容编辑助手。",
            user=prompt,
        )

    async def analyze(self, system_prompt: str, user_prompt: str) -> str:
        return await self._gen.call_raw(system=system_prompt, user=user_prompt)


class HotlistServiceAdapter:
    """将 hotlist_service 适配为 HotlistServicePort。"""

    async def fetch(self, limit: int) -> list[dict]:
        response = await fetch_hotlist(limit=limit)
        return [item.model_dump(by_alias=True) for item in response.items]
