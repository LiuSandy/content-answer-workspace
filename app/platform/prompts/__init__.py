"""Prompt Registry 包；通过 prompt_registry 单例和 warmup() 函数使用。"""
from __future__ import annotations

from .registry import RenderedPrompt, PromptRegistry, prompt_registry, warmup
from .errors import (
    PromptDuplicateIdError,
    PromptNotFoundError,
    PromptRenderError,
    PromptVariableMissingError,
)

__all__ = [
    "PromptRegistry",
    "RenderedPrompt",
    "prompt_registry",
    "warmup",
    "PromptDuplicateIdError",
    "PromptNotFoundError",
    "PromptRenderError",
    "PromptVariableMissingError",
]
