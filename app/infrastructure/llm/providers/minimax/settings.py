"""MiniMax connection and model settings."""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MiniMaxSettings:
    api_key: str
    base_url: str
    model: str

    @classmethod
    def from_env(cls) -> "MiniMaxSettings":
        return cls(
            api_key=os.getenv("MINIMAX_API_KEY", "").strip(),
            base_url=(
                os.getenv("MINIMAX_BASE_URL", "https://api.minimax.io/v1")
                .strip()
                .rstrip("/")
            ),
            model=os.getenv("MINIMAX_MODEL", "MiniMax-M3").strip() or "MiniMax-M3",
        )
