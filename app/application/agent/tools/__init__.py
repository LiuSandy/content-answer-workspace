"""Agent 工具注册入口；启动时读取 agent_reach_config.json，按平台开关动态追加工具到 ALL_TOOLS。

安全边界（spec §12）：任意代码执行工具 code_interpreter 默认不注册，仅当配置
code_interpreter.enabled=true 时才加入；未启用平台不注册。
"""

from __future__ import annotations

import json
from pathlib import Path

from .calculator import calculator
from .crawl4ai_tool import crawl4ai_fetch
from .datetime_tool import get_current_datetime
from .firecrawl_tool import firecrawl_scrape  # 备用：配置 FIRECRAWL_API_KEY 后加入 ALL_TOOLS
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

_AGENT_REACH_CONFIG = Path(__file__).resolve().parent.parent.parent.parent.parent / ".data" / "agent_reach_config.json"


def _load_platform_tool_map() -> dict:
    """懒加载各平台工具模块；避免在未启用时导入对应依赖。"""
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
    """在进程启动时读取配置，构建完整工具列表；配置文件不存在时只用基础工具。

    code_interpreter（任意代码执行）默认关闭，仅当 agent_reach_config.json
    显式设置 code_interpreter.enabled=true 时才注册（spec §12）。
    """
    tools = list(_BASE_TOOLS)
    try:
        config = json.loads(_AGENT_REACH_CONFIG.read_text(encoding="utf-8"))
        enabled_platforms: list[str] = config.get("enabledPlatforms", [])
        code_interpreter_enabled: bool = bool(
            (config.get("code_interpreter") or {}).get("enabled")
        )
    except (FileNotFoundError, json.JSONDecodeError):
        return tools

    if code_interpreter_enabled:
        from .code_interpreter import code_interpreter

        tools.append(code_interpreter)

    if not enabled_platforms:
        return tools

    platform_tool_map = _load_platform_tool_map()
    for platform in enabled_platforms:
        tools.extend(platform_tool_map.get(platform, []))

    return tools


ALL_TOOLS = _build_all_tools()
