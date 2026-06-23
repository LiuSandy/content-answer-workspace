"""V2EX 工具；通过 V2EX 公开 JSON API 获取热门话题和节点帖子，无需额外 CLI。"""

from __future__ import annotations

import json
import urllib.request

from langchain_core.tools import tool

_PLATFORM = "v2ex"
_MAX_CHARS = 6000
_TIMEOUT = 15


def _fetch_json(url: str) -> dict | list:
    """通过标准库发送 GET 请求并解析 JSON；避免额外依赖。"""
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


@tool
def v2ex_hot() -> str:
    """获取 V2EX 当前热门话题列表（标题、节点、回复数、链接）。"""
    try:
        data = _fetch_json("https://www.v2ex.com/api/topics/hot.json")
        if not isinstance(data, list):
            return f"[{_PLATFORM}] 响应格式异常。"
        lines = []
        for item in data[:20]:
            title = item.get("title", "")
            node = item.get("node", {}).get("title", "")
            replies = item.get("replies", 0)
            url = item.get("url", "")
            lines.append(f"- [{title}]({url}) · {node} · {replies} 条回复")
        return "\n".join(lines)[:_MAX_CHARS]
    except Exception as e:  # noqa: BLE001
        return f"[{_PLATFORM}] 获取热门失败：{e}"


@tool
def v2ex_node(node_name: str, limit: int = 20) -> str:
    """获取 V2EX 指定节点的最新帖子列表。node_name 为节点英文名（如 python、programming）。"""
    try:
        data = _fetch_json(f"https://www.v2ex.com/api/topics/show.json?node_name={node_name}")
        if not isinstance(data, list):
            return f"[{_PLATFORM}] 节点 '{node_name}' 不存在或无帖子。"
        lines = []
        for item in data[:limit]:
            title = item.get("title", "")
            replies = item.get("replies", 0)
            url = item.get("url", "")
            lines.append(f"- [{title}]({url}) · {replies} 条回复")
        return "\n".join(lines)[:_MAX_CHARS]
    except Exception as e:  # noqa: BLE001
        return f"[{_PLATFORM}] 获取节点失败：{e}"
