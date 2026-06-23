"""Twitter/X 工具；通过 twitter-cli 搜索和读取推文。
认证方式：设置环境变量 TWITTER_AUTH_TOKEN + TWITTER_CT0（从浏览器 Cookie 中提取）。"""

from __future__ import annotations

import subprocess

from langchain_core.tools import tool

_PLATFORM = "twitter"
_MAX_CHARS = 6000


def _run(args: list[str]) -> str:
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=30)
        return (result.stdout or result.stderr or "无结果")[:_MAX_CHARS]
    except FileNotFoundError:
        return f"[{_PLATFORM}] twitter-cli 未安装，请运行 `pipx install twitter-cli`。"
    except subprocess.TimeoutExpired:
        return f"[{_PLATFORM}] 请求超时（30s）。"
    except Exception as e:  # noqa: BLE001
        return f"[{_PLATFORM}] 调用失败：{e}"


@tool
def twitter_feed(limit: int = 20) -> str:
    """获取 Twitter/X 首页时间线推文（最稳定，需要配置认证）。"""
    return _run(["twitter", "feed", "-n", str(limit)])


@tool
def twitter_search(query: str, limit: int = 10) -> str:
    """在 Twitter/X 搜索推文（可能因 GraphQL 端点变化而不稳定，失败时改用 twitter_feed）。"""
    return _run(["twitter", "search", query, "-n", str(limit)])


@tool
def twitter_read(url_or_id: str) -> str:
    """读取单条推文及其回复线程。支持推文 URL 或 ID。"""
    return _run(["twitter", "tweet", url_or_id])


@tool
def twitter_user_posts(username: str, limit: int = 20) -> str:
    """获取指定 Twitter/X 用户的最新推文列表。username 格式：@handle 或 handle。"""
    handle = username.lstrip("@")
    return _run(["twitter", "user-posts", f"@{handle}", "-n", str(limit)])
