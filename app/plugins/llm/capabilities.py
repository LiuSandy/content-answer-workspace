"""Provider capability declarations used by gateway strategies."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

StructuredMethod = Literal["json_schema", "json_mode", "generic_parse"]


@dataclass(frozen=True, slots=True)
class LLMCapabilities:
    structured_methods: tuple[StructuredMethod, ...] = ("generic_parse",)
    tool_calling: bool = True
    streaming: bool = True
