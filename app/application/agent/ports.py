from __future__ import annotations

from typing import Protocol


class SessionServicePort(Protocol):
    """Node 依赖的 Session 数据访问接口。"""

    async def get_answer(self, session_id: str, question_id: str) -> str:
        """读取指定问题的当前回答，问题不存在时返回空字符串。"""
        ...

    async def update_answer(self, session_id: str, question_id: str, content: str) -> None:
        """覆盖写入指定问题的回答。"""
        ...


class LLMClientPort(Protocol):
    """Node 依赖的 LLM 调用接口。"""

    async def refine(self, instruction: str, current_answer: str) -> str:
        """按指令定向修改回答，返回修改后全文。"""
        ...

    async def analyze(self, system_prompt: str, user_prompt: str) -> str:
        """调用 LLM 分析，返回原始文本（通常为 JSON 字符串）。"""
        ...


class HotlistServicePort(Protocol):
    """Node 依赖的热榜数据接口。"""

    async def fetch(self, limit: int) -> list[dict]:
        """获取热榜，返回序列化后的 dict 列表。"""
        ...
