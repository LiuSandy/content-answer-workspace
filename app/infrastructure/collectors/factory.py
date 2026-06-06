from __future__ import annotations

from ...domain.ports import CollectorPort
from .zhihu_collector import ZhihuCollector


class CollectorFactory:
    """根据平台创建采集策略；这样新增平台时只注册采集器，不需要改工作流分支逻辑。"""

    _collectors: dict[str, type[CollectorPort]] = {
        ZhihuCollector.platform: ZhihuCollector,
    }

    @classmethod
    def create(cls, platform: str | None) -> CollectorPort:
        """返回指定平台的采集器实例；这样 API 传入的 platform 能被稳定映射到具体策略。"""

        normalized = (platform or "zhihu").strip().lower()
        collector_class = cls._collectors.get(normalized)
        if collector_class is None:
            supported = ", ".join(sorted(cls._collectors))
            raise ValueError(f"Unsupported platform: {normalized}. Supported platforms: {supported}")
        return collector_class()
