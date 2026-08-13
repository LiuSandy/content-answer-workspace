"""确定性平台采集节点；明确平台请求只调用一个对应搜索工具。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from langchain_core.messages import AIMessage

from ..state import ChatAgentState
from ..tools import ALL_TOOLS


@dataclass(frozen=True)
class _PlatformSearchSpec:
    tool_name: str
    query_argument: str
    supports_limit: bool = True
    sort_argument: str | None = None


_PLATFORM_SEARCH_SPECS = {
    "zhihu": _PlatformSearchSpec("zhihu_search", "keyword", sort_argument="sort"),
    "xiaohongshu": _PlatformSearchSpec("xiaohongshu_search", "query"),
    "bilibili": _PlatformSearchSpec("bilibili_search", "query"),
    "twitter": _PlatformSearchSpec("twitter_search", "query"),
    "reddit": _PlatformSearchSpec("reddit_search", "query", supports_limit=False),
    "github": _PlatformSearchSpec("github_search_repos", "query"),
}

_PLATFORM_LABELS = {
    "zhihu": "知乎",
    "xiaohongshu": "小红书",
    "bilibili": "B站",
    "twitter": "Twitter/X",
    "reddit": "Reddit",
    "github": "GitHub",
}


def _find_tool(tool_name: str):
    return next((tool for tool in ALL_TOOLS if getattr(tool, "name", None) == tool_name), None)


def has_platform_search_route(state: ChatAgentState | dict) -> bool:
    """只有平台、查询词和已启用专用工具都存在时才进入确定性路径。"""

    platform = str(state.get("intent_platform") or "").strip().lower()
    query = str(state.get("intent_query") or "").strip()
    spec = _PLATFORM_SEARCH_SPECS.get(platform)
    return bool(query and spec and _find_tool(spec.tool_name))


def _decode_tool_result(raw: Any, platform: str, query: str) -> tuple[str, dict[str, Any]]:
    if isinstance(raw, str):
        content = raw
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = {
                "platform": platform,
                "topic": query,
                "items": [],
                "error": raw or "平台工具返回了无法解析的结果",
                "error_code": "platform_invalid_response",
                "retryable": False,
            }
    elif isinstance(raw, dict):
        parsed = raw
        content = json.dumps(raw, ensure_ascii=False)
    else:
        parsed = {
            "platform": platform,
            "topic": query,
            "items": [],
            "error": "平台工具返回了无法解析的结果",
            "error_code": "platform_invalid_response",
            "retryable": False,
        }
        content = json.dumps(parsed, ensure_ascii=False)
    return content, parsed


async def platform_collect_node(state: ChatAgentState) -> dict:
    """调用一个已识别平台的搜索工具，并直接生成终态回复。"""

    platform = str(state.get("intent_platform") or "").strip().lower()
    query = str(state.get("intent_query") or "").strip()
    spec = _PLATFORM_SEARCH_SPECS.get(platform)
    tool = _find_tool(spec.tool_name) if spec else None
    label = _PLATFORM_LABELS.get(platform, platform or "平台")

    if not query or spec is None or tool is None:
        return {"messages": [AIMessage(content=f"{label}搜索工具当前未启用，无法执行本次检索。")]}

    arguments: dict[str, Any] = {spec.query_argument: query}
    if spec.supports_limit:
        try:
            requested_limit = int(state.get("intent_limit") or 10)
        except (TypeError, ValueError):
            requested_limit = 10
        arguments["limit"] = max(1, min(20, requested_limit))
    if spec.sort_argument:
        requested_sort = str(state.get("intent_sort") or "relevance")
        arguments[spec.sort_argument] = (
            requested_sort if requested_sort in {"relevance", "hot", "latest"} else "relevance"
        )

    try:
        raw = await tool.ainvoke(arguments)
        content, payload = _decode_tool_result(raw, platform, query)
    except Exception as exc:  # noqa: BLE001 - 平台边界统一转换为终态错误
        payload = {
            "platform": platform,
            "topic": query,
            "items": [],
            "error": str(exc),
            "error_code": "platform_tool_failed",
            "retryable": False,
        }
        content = json.dumps(payload, ensure_ascii=False)

    items = payload.get("items") if isinstance(payload.get("items"), list) else []
    error = str(payload.get("error") or "").strip()
    user_message = str(payload.get("message") or error).strip()
    if error and not items:
        response = f"{label}检索失败：{user_message}"
    elif not items:
        response = f"未在{label}检索到与“{query}”相关的结果。"
    else:
        response = f"已从{label}检索到 {len(items)} 条与“{query}”相关的结果。"

    return {
        "messages": [AIMessage(content=response)],
        "platform_collect_result": {
            "tool_type": spec.tool_name,
            "platform": platform,
            "items": items,
        },
    }
