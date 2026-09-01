"""Provider capability declarations used by gateway strategies."""

from __future__ import annotations

from dataclasses import dataclass
from app.shared.llm.dto import StructuredMethod


@dataclass(frozen=True, slots=True)
class LLMCapabilities:
    structured_methods: tuple[StructuredMethod, ...] = ("function_calling",)
    tool_calling: bool = True
    streaming: bool = True
