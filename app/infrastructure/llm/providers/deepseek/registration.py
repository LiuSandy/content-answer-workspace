"""DeepSeek provider registration boundary."""
from __future__ import annotations

from typing import Any

from .provider import DeepSeekProvider


def register_deepseek(registry: Any) -> None:
    """Register the DeepSeek text LLM provider."""
    registry.register(DeepSeekProvider())
