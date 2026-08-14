"""Source Registry；根据 URL 或平台名路由到对应 ContentSource 适配器。"""
from __future__ import annotations

import logging

from app.contracts.errors import UnsupportedSourceError

logger = logging.getLogger(__name__)


class SourceRegistry:
    """维护已注册的 ContentSource 适配器，按 URL 或 platform 路由。"""

    def __init__(self) -> None:
        self._sources: dict[str, object] = {}  # key -> ContentSource

    def register(self, source: object) -> None:
        key = getattr(source, "key", str(source))
        self._sources[key] = source
        logger.info("Registered content source: %s", key)

    def get_for_url(self, url: str) -> object:
        """遍历适配器，返回第一个 can_handle_url() 为 True 的。"""
        for source in self._sources.values():
            if hasattr(source, "can_handle_url") and source.can_handle_url(url):
                return source
        raise UnsupportedSourceError(url)

    def get_for_collect(self, platform: str | None) -> object:
        """根据 platform 名返回适配器；platform 为 None 时返回第一个支持 collect 的。"""
        if platform:
            normalized = platform.strip().lower()
            if normalized in self._sources:
                return self._sources[normalized]
            raise UnsupportedSourceError(platform)
        # 返回第一个支持 collect 的适配器
        for source in self._sources.values():
            caps = getattr(source, "capabilities", set())
            if "collect" in caps:
                return source
        raise UnsupportedSourceError("no collect-capable source registered")

    def list_keys(self) -> list[str]:
        return list(self._sources.keys())


def build_default_registry() -> SourceRegistry:
    """构建包含所有默认适配器的 Registry；服务启动时调用。"""
    from .adapters.zhihu import ZhihuSource
    from .adapters.xiaohongshu import XiaohongshuSource
    from .adapters.universal import UniversalSource

    registry = SourceRegistry()
    registry.register(ZhihuSource())
    registry.register(XiaohongshuSource())
    registry.register(UniversalSource())
    return registry


# 全局单例（懒初始化：首次导入时构建）
source_registry = build_default_registry()
