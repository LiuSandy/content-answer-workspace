"""Kimi connection and model settings."""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class KimiSettings:
    api_key: str
    base_url: str
    model: str

    @classmethod
    def from_env(cls) -> "KimiSettings":
        return cls(
            api_key=os.getenv("KIMI_API_KEY", "").strip(),
            base_url=(
                os.getenv("KIMI_BASE_URL", "https://api.moonshot.cn/v1")
                .strip()
                .rstrip("/")
            ),
            model=os.getenv("KIMI_MODEL", "kimi-k2.5").strip() or "kimi-k2.5",
        )
