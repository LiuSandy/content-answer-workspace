from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

from app.platform.config.loader import get_settings
from .platform_config import AuthConfig, PaginationConfig, PlatformConfig

PLATFORMS_DIR = Path(__file__).parent / "platforms"


class PlatformConfigLoader:
    """从 YAML 文件加载并验证平台配置；同一进程内配置只读取一次。"""

    @staticmethod
    @lru_cache(maxsize=32)
    def load(platform: str) -> PlatformConfig | None:
        path = PLATFORMS_DIR / f"{platform}.yaml"
        if not path.exists():
            return None
        with path.open(encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        return PlatformConfigLoader._parse(raw)

    @staticmethod
    def _parse(raw: dict) -> PlatformConfig:
        auth = raw.get("auth", {})
        pagination = raw.get("pagination", {})
        return PlatformConfig(
            name=raw["name"],
            display_name=raw.get("display_name", raw["name"]),
            auth=AuthConfig(
                method=auth.get("method", "none"),
                env_var=auth.get("env_var"),
            ),
            search_url_template=raw["search"]["url_template"],
            fetcher=raw.get("fetcher", "http"),
            pagination=PaginationConfig(
                type=pagination.get("type", "page"),
                param=pagination.get("param", "page"),
                page_size=pagination.get("page_size", get_settings().collect.default_page_size),
            ),
            extraction_prompt=raw["extraction_prompt"],
        )
