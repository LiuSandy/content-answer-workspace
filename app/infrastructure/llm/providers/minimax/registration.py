"""MiniMax provider registration boundary."""
from __future__ import annotations

from typing import Any

from .provider import MiniMaxProvider


def register_minimax(registry: Any) -> None:
    registry.register(MiniMaxProvider())
