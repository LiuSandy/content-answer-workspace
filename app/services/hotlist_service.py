from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..infrastructure.zhihu.official_client import ZhihuOfficialClient
from ..models import HotlistItem, HotlistResponse
from .zhihu_service import clean_text


async def fetch_hotlist(limit: int = 30) -> HotlistResponse:
    """获取知乎热榜条目列表；这样热榜功能独立于主题采集流程，可以单独被路由调用。"""
    client = ZhihuOfficialClient()
    raw = await client.get_hotlist(limit=min(limit, 30))
    items = _map_hotlist(raw)
    return HotlistResponse(
        items=items,
        fetchedAt=datetime.now(timezone.utc).isoformat(),
    )


def _map_hotlist(raw: dict[str, Any]) -> list[HotlistItem]:
    """映射官方热榜响应到内部模型；这样官方字段变化只需修改此处。"""
    # 官方热榜响应格式: {"Code": 0, "Data": {"Total": N, "Items": [...]}}
    data = raw.get("Data") or raw.get("data") or {}
    entries = data.get("Items") or data.get("items") or []
    if not isinstance(entries, list):
        return []

    result: list[HotlistItem] = []
    for rank, entry in enumerate(entries, start=1):
        item = _map_entry(entry, rank)
        if item is not None:
            result.append(item)
    return result


def _map_entry(entry: dict[str, Any], rank: int) -> HotlistItem | None:
    """映射单条热榜条目；这样嵌套字段和缺失字段都能被容错处理。"""
    if not isinstance(entry, dict):
        return None

    title = clean_text(entry.get("Title") or entry.get("title") or "")
    if not title:
        return None

    url = entry.get("Url") or entry.get("url") or ""
    thumbnail_url = entry.get("ThumbnailUrl") or entry.get("thumbnail_url") or ""
    summary = clean_text(entry.get("Summary") or entry.get("summary") or "")
    heat = str(entry.get("Heat") or entry.get("heat") or "")

    return HotlistItem(
        rank=rank,
        title=title,
        url=url,
        thumbnailUrl=thumbnail_url,
        summary=summary,
        heat=heat,
    )
