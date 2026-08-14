"""ContextComposer：在模型输入预算内组装对话上下文（roadmap R4）。

规则（接口决定）：
- 预算 = context_window - output_reserve_tokens - (system + rag + instruction + summary) 的 token 数。
- 消息按时间从旧到新裁剪：优先丢弃最旧消息，保留最近两轮（最后一轮 user/assistant 对）。
- 当前用户指令永不因裁剪丢失（单独注入，不计入可裁剪消息）。
- 超长单条消息截断到剩余预算。
- CJK 估算：1 个 CJK 字符 ≈ 1 token，其他字符 ≈ 0.25 token；确定性、可测试。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

# 最近保留轮数：最后一轮 user/assistant 必须完整保留
KEEP_RECENT_TURNS = 2


def estimate_tokens(text: str) -> int:
    """确定性 token 估算：CJK 字符按 1 token，其余按 0.25 token，向上取整。"""
    if not text:
        return 0
    cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff" or "\u3000" <= ch <= "\u303f")
    other = len(text) - cjk
    import math

    return cjk + math.ceil(other * 0.25)


@dataclass
class ComposedContext:
    """组装结果；budget 为预算内的总可用 token，dropped 为被裁剪的消息数。"""

    messages: list[dict[str, str]]
    system_prompt: str
    rag_context: str = ""
    current_instruction: str = ""
    summary: str | None = None
    budget: int = 0
    dropped: int = 0
    truncated_message_ids: list[str] = field(default_factory=list)
    kept_indices: list[int] = field(default_factory=list)

    def total_tokens(self) -> int:
        return estimate_tokens(self.system_prompt) + sum(
            estimate_tokens(m.get("content", "")) for m in self.messages
        ) + estimate_tokens(self.rag_context) + estimate_tokens(self.current_instruction)


class ContextProfile(Protocol):
    context_window: int | None
    output_reserve_tokens: int | None


@dataclass
class SimpleContextProfile:
    """可注入的最小 profile 实现，便于测试与默认值。"""

    context_window: int | None = 64000
    output_reserve_tokens: int | None = 4096


class ContextComposer:
    def __init__(self, profile: ContextProfile | None = None) -> None:
        self._profile = profile or SimpleContextProfile()

    def assemble(
        self,
        messages: list[dict[str, str]],
        system_prompt: str = "",
        rag_context: str = "",
        current_instruction: str = "",
        summary: str | None = None,
        message_ids: list[str] | None = None,
    ) -> ComposedContext:
        """在预算内组装消息。

        messages: [{"role", "content"}]，按时间升序。
        message_ids: 与 messages 等长的消息 id（用于报告截断明细），可为 None。
        current_instruction: 当前用户指令，永不裁剪。
        """
        window = self._profile.context_window or 64000
        reserve = self._profile.output_reserve_tokens or 0

        fixed = (
            estimate_tokens(system_prompt)
            + estimate_tokens(rag_context)
            + estimate_tokens(current_instruction)
            + estimate_tokens(summary or "")
        )
        budget = max(0, window - reserve - fixed)

        # 始终保留最近两轮（最后一轮 user 与其回复），其余可裁剪
        keep_count = min(len(messages), KEEP_RECENT_TURNS * 2)

        # 预算优先保障最近两轮（最后 user/assistant 对），再回填更早历史。
        # kept 记录 (原索引, 消息)，最后按索引还原原始顺序。
        kept: list[tuple[int, dict[str, str]]] = []
        dropped = 0
        available = budget

        recent_start = len(messages) - keep_count
        # 从新到旧处理 recent，保证最后一轮 user 消息最优先完整保留
        for offset in range(keep_count - 1, -1, -1):
            idx = recent_start + offset
            msg = messages[idx]
            cost = estimate_tokens(msg.get("content", ""))
            if available >= cost:
                kept.append((idx, msg))
                available -= cost
            elif available > 0:
                kept.append((idx, {**msg, "content": self._truncate(msg.get("content", ""), available)}))
                available = 0
            elif idx == len(messages) - 1:
                # 最后一轮 user 消息即使超预算也完整保留（当前指令的一部分）
                kept.append((idx, msg))
            else:
                kept.append((idx, {**msg, "content": ""}))

        # 更早历史按从新到旧回填：优先保留较新的旧消息，最旧的优先丢弃
        for idx in range(recent_start - 1, -1, -1):
            cost = estimate_tokens(messages[idx].get("content", ""))
            if available >= cost:
                kept.append((idx, messages[idx]))
                available -= cost
            else:
                dropped += 1

        kept.sort(key=lambda kv: kv[0])
        kept_messages = [m for _, m in kept]

        truncated_ids: list[str] = []
        kept_indices: list[int] = [i for i, _ in kept]
        if message_ids and len(message_ids) == len(messages):
            kept_idx = {i for i, _ in kept}
            truncated_ids = [
                mid for i, mid in enumerate(message_ids) if i not in kept_idx and mid
            ]

        return ComposedContext(
            messages=kept_messages,
            system_prompt=system_prompt,
            rag_context=rag_context,
            current_instruction=current_instruction,
            summary=summary,
            budget=budget,
            dropped=dropped,
            truncated_message_ids=truncated_ids,
            kept_indices=kept_indices,
        )

    @staticmethod
    def _truncate(text: str, max_tokens: int) -> str:
        if max_tokens <= 0:
            return ""
        cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
        # 按比例截断：优先保留头部
        ratio = max_tokens / max(1, estimate_tokens(text))
        cut = max(1, int(len(text) * min(ratio, 1.0)))
        return text[:cut]
