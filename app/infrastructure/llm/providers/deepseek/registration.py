"""DeepSeek provider registration boundary."""
from __future__ import annotations

from typing import Any, Callable

from .provider import DeepSeekProvider


def register_deepseek(registry: Any) -> None:
    """Register the only configured text LLM provider."""
    registry.register(DeepSeekProvider())


def build_deepseek_registry(registry_factory: Callable[[], Any]) -> Any:
    """Build the application registry without registering vendors elsewhere."""
    registry = registry_factory()
    register_deepseek(registry)
    return registry
