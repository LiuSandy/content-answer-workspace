from __future__ import annotations

from ..state import AgentState
from ..ports import HotlistServicePort


async def fetch_hotlist_node(state: AgentState, *, hotlist_svc: HotlistServicePort) -> dict:
    """获取热榜数据，写入 hotlist_items。复用现有 HotlistService，不重复实现采集逻辑。"""
    items = await hotlist_svc.fetch(limit=30)
    return {"hotlist_items": items}
