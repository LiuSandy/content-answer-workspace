from __future__ import annotations

import json
from typing import Any

DEFAULT_COLLECT_TOOLS = {
    "zhihu_search",
    "xiaohongshu_search",
    "xiaohongshu_feed",
    "bilibili_search",
    "bilibili_hot",
    "twitter_search",
    "twitter_feed",
    "twitter_user_posts",
    "reddit_search",
    "reddit_hot",
    "reddit_subreddit",
    "github_search_repos",
    "rss_fetch",
    "v2ex_hot",
    "v2ex_node",
}


def extract_collect_result(tool_name: str, raw_output: Any) -> dict[str, Any] | None:
    if tool_name not in DEFAULT_COLLECT_TOOLS:
        return None

    if not isinstance(raw_output, str):
        raw_output = getattr(raw_output, "content", "") or ""
    if not isinstance(raw_output, str) or not raw_output:
        return None

    try:
        parsed = json.loads(raw_output)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(parsed, dict):
        return None

    items = parsed.get("items") or []
    if not items:
        return None

    return {
        "platform": parsed.get("platform", "unknown"),
        "topic": parsed.get("topic", ""),
        "items": items,
    }
