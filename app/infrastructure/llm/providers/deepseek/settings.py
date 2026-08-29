"""DeepSeek connection and model settings.

All ``DEEPSEEK_*`` environment variables are read in this module so callers do
not duplicate vendor configuration across agents and services.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DeepSeekSettings:
    api_key: str
    base_url: str
    model: str
    topic_expansion_model: str

    @classmethod
    def from_env(cls) -> "DeepSeekSettings":
        api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
        model = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-pro").strip()
        if not model:
            model = "deepseek-v4-pro"
        return cls(
            api_key=api_key,
            base_url=(
                os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
                .strip()
                .rstrip("/")
            ),
            model=model,
            topic_expansion_model=(
                os.getenv("DEEPSEEK_TOPIC_EXPANSION_MODEL", "").strip() or model
            ),
        )


def load_deepseek_settings() -> DeepSeekSettings:
    """Load settings at provider construction time.

    This intentionally is not globally cached: the provider/client owns the
    runtime lifecycle, while tests may construct isolated providers with
    different environment values.
    """
    try:
        from app.config.runtime import load_env_file

        load_env_file()
    except Exception:
        pass
    return DeepSeekSettings.from_env()
