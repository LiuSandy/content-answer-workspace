"""Kimi provider registration boundary."""
from __future__ import annotations

from typing import Any

from .provider import KimiProvider


def register_kimi(registry: Any) -> None:
    registry.register(KimiProvider())
