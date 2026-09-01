from __future__ import annotations

from app.shared.ports import CollectorPort
from .platform_config_loader import PlatformConfigLoader
from .universal_collector import UniversalCollector
from .xiaohongshu_collector import XiaohongshuCollector
from .zhihu_collector import ZhihuCollector


class CollectorFactory:
    """根据平台和数据源创建采集策略；这样新增平台或模式时只注册采集器，不修改工作流逻辑。"""

    _collectors: dict[str, type[CollectorPort]] = {
        ZhihuCollector.platform: ZhihuCollector,
        XiaohongshuCollector.platform: XiaohongshuCollector,
    }

    @classmethod
    def create(cls, platform: str | None, source: str = "auto") -> CollectorPort:
        """返回指定平台和来源模式的采集器实例；source 支持 official/web/auto 三种模式。"""
        normalized_platform = (platform or "zhihu").strip().lower()
        normalized_source = (source or "auto").strip().lower()

        if normalized_source == "official":
            raise ValueError(f"official source is not supported for platform: {normalized_platform}")

        if normalized_source not in {"auto", "web"}:
            raise ValueError(f"Unsupported collection source: {normalized_source}")

        collector_class = cls._collectors.get(normalized_platform)
        if collector_class is not None:
            return collector_class()

        # fallback：尝试 YAML 平台配置（UniversalCollector）
        yaml_config = PlatformConfigLoader.load(normalized_platform)
        if yaml_config is not None:
            return UniversalCollector(yaml_config)

        supported = ", ".join(k for k in sorted(cls._collectors) if ":" not in k)
        raise ValueError(f"Unsupported platform: {normalized_platform}. Supported platforms: {supported}")
