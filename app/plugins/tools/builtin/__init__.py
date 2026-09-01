"""共享工具注册入口，按配置启用可选平台工具。"""

from __future__ import annotations

import json
from pathlib import Path

from . import xiaohongshu_tool, zhihu_tool
from .calculator import calculator
from .crawl4ai_tool import crawl4ai_fetch
from .datetime_tool import get_current_datetime
from .firecrawl_tool import firecrawl_scrape
from .news_search import news_search
from .web_fetch import web_fetch
from .web_search import web_search
from .zhihu_tool import zhihu_search

_BASE_TOOLS = [
    get_current_datetime,
    web_search,
    web_fetch,
    crawl4ai_fetch,
    news_search,
    calculator,
    zhihu_search,
]

_AGENT_REACH_CONFIG = (
    Path(__file__).resolve().parent.parent.parent.parent.parent
    / ".data"
    / "agent_reach_config.json"
)


def _load_platform_tool_map() -> dict:
    """懒加载可选平台工具，避免未启用平台引入额外依赖。"""
    from .bilibili_tool import bilibili_hot, bilibili_search, bilibili_video
    from .github_tool import github_repo_info, github_search_repos
    from .reddit_tool import reddit_hot, reddit_read, reddit_search, reddit_subreddit
    from .rss_tool import rss_fetch
    from .twitter_tool import twitter_feed, twitter_read, twitter_search, twitter_user_posts
    from .v2ex_tool import v2ex_hot, v2ex_node
    from .xiaohongshu_tool import xiaohongshu_feed, xiaohongshu_note, xiaohongshu_search
    from .youtube_tool import youtube_fetch

    return {
        "bilibili": [bilibili_search, bilibili_hot, bilibili_video],
        "youtube": [youtube_fetch],
        "twitter": [twitter_search, twitter_feed, twitter_user_posts, twitter_read],
        "xiaohongshu": [xiaohongshu_search, xiaohongshu_feed, xiaohongshu_note],
        "reddit": [reddit_search, reddit_hot, reddit_subreddit, reddit_read],
        "github": [github_search_repos, github_repo_info],
        "rss": [rss_fetch],
        "v2ex": [v2ex_hot, v2ex_node],
    }


def _build_all_tools() -> list:
    """构建启用工具列表；任意代码执行工具默认关闭。"""
    tools = list(_BASE_TOOLS)
    try:
        config = json.loads(_AGENT_REACH_CONFIG.read_text(encoding="utf-8"))
        enabled_platforms: list[str] = config.get("enabledPlatforms", [])
        code_interpreter_enabled = bool(
            (config.get("code_interpreter") or {}).get("enabled")
        )
    except (FileNotFoundError, json.JSONDecodeError):
        return tools

    if code_interpreter_enabled:
        from .code_interpreter import code_interpreter

        tools.append(code_interpreter)

    platform_tool_map = _load_platform_tool_map()
    for platform in enabled_platforms:
        tools.extend(platform_tool_map.get(platform, []))
    return tools


ALL_TOOLS = _build_all_tools()

__all__ = [
    "ALL_TOOLS",
    "firecrawl_scrape",
    "xiaohongshu_tool",
    "zhihu_tool",
]
