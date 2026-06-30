"""V2EX 工具；通过 V2EX 公开 JSON API 获取热门话题和节点帖子，返回标准化采集卡片 JSON。"""

from __future__ import annotations

import json
import urllib.request

from langchain_core.tools import tool

_PLATFORM = "v2ex"
_TIMEOUT = 15
_MAX_ITEMS = 20


def _fetch_json(url: str) -> dict | list:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _to_result(topic: str, items: list[dict]) -> str:
    return json.dumps(
        {"platform": _PLATFORM, "topic": topic, "items": items[:_MAX_ITEMS]},
        ensure_ascii=False,
    )


def _error_result(topic: str, msg: str) -> str:
    return json.dumps({"platform": _PLATFORM, "topic": topic, "error": msg, "items": []}, ensure_ascii=False)


@tool
def v2ex_hot() -> str:
    """获取 V2EX 当前热门话题列表，返回标题、节点、回复数等结构化结果。"""
    try:
        data = _fetch_json("https://www.v2ex.com/api/topics/hot.json")
        if not isinstance(data, list):
            return _error_result("热门", "响应格式异常")
        items = []
        for item in data[:_MAX_ITEMS]:
            title = str(item.get("title") or "")
            url = str(item.get("url") or "")
            node = str((item.get("node") or {}).get("title") or "")
            replies = item.get("replies") or 0
            author = str((item.get("member") or {}).get("username") or "")
            metric = f"{replies} 条回复" if replies else ""
            if title:
                items.append({"title": title, "url": url, "excerpt": node, "metric": metric, "author": author})
        return _to_result("热门", items) if items else _error_result("热门", "无热门话题")
    except Exception as e:  # noqa: BLE001
        return _error_result("热门", str(e))


@tool
def v2ex_node(node_name: str, limit: int = 20) -> str:
    """获取 V2EX 指定节点的最新帖子，返回标题、回复数等结构化结果。
    node_name 为节点英文名（如 python、programming）。"""
    try:
        data = _fetch_json(f"https://www.v2ex.com/api/topics/show.json?node_name={node_name}")
        if not isinstance(data, list):
            return _error_result(node_name, f"节点 '{node_name}' 不存在或无帖子")
        items = []
        for item in data[:limit]:
            title = str(item.get("title") or "")
            url = str(item.get("url") or "")
            replies = item.get("replies") or 0
            author = str((item.get("member") or {}).get("username") or "")
            metric = f"{replies} 条回复" if replies else ""
            if title:
                items.append({"title": title, "url": url, "excerpt": "", "metric": metric, "author": author})
        return _to_result(node_name, items) if items else _error_result(node_name, "无帖子")
    except Exception as e:  # noqa: BLE001
        return _error_result(node_name, str(e))
