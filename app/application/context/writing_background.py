"""WritingBackground：创作上下文环境（roadmap R7）。

收集已确认大纲、L2 记忆、对话背景和素材 RAG 内容，按要求优先级拼装。
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class WritingBackground:
    confirmed_outline: list[dict] | None = None
    active_memories: list[dict] | None = None
    dialog_background: str | None = None
    material_context: str | None = None
    platform_style_guide: str | None = None

    def to_context_text(self) -> str:
        """按优先级拼装 LLM 系统上下文块。

        顺序：当前指令 > 原文（由调用方传入）> 确认大纲 > 平台风格 > L2 记忆 > 对话背景 > 素材。
        """
        blocks: list[str] = []
        if self.confirmed_outline:
            ol_text = "\n".join(
                f"## {s.get('heading', '')}\n" + "\n".join(f"- {kp}" for kp in (s.get("keyPoints") or []))
                for s in self.confirmed_outline
            )
            blocks.append(f"【已确认的创作大纲】\n{ol_text}")
        if self.platform_style_guide:
            blocks.append(f"【平台风格指南】\n{self.platform_style_guide}")
        if self.active_memories:
            mem_text = "\n".join(
                f"- [{m.get('memory_type')}] {m.get('content')}" for m in self.active_memories
            )
            blocks.append(f"【用户长期偏好（已应用 {len(self.active_memories)} 条）】\n{mem_text}")
        if self.dialog_background:
            blocks.append(f"【对话背景】\n{self.dialog_background}")
        if self.material_context:
            blocks.append(f"【参考素材】\n{self.material_context}")
        if not blocks:
            return ""
        return "\n\n" + "\n\n".join(blocks)
