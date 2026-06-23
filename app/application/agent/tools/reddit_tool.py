"""Reddit 工具；通过 OpenCLI（首选）或 rdt-cli（备选）搜索和读取帖子。
Reddit 没有零配置路径，需要浏览器登录态（OpenCLI）或手动配置 Cookie（rdt-cli）。"""

from __future__ import annotations

import subprocess

from langchain_core.tools import tool

_PLATFORM = "reddit"
_MAX_CHARS = 6000


def _run(args: list[str]) -> str:
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=30)
        return (result.stdout or result.stderr or "无结果")[:_MAX_CHARS]
    except FileNotFoundError:
        return f"[{_PLATFORM}] CLI 未找到（{args[0]}），请检查 agent-reach 安装状态。"
    except subprocess.TimeoutExpired:
        return f"[{_PLATFORM}] 请求超时（30s）。"
    except Exception as e:  # noqa: BLE001
        return f"[{_PLATFORM}] 调用失败：{e}"


@tool
def reddit_search(query: str) -> str:
    """在 Reddit 搜索帖子（通过 OpenCLI 复用 Chrome 登录态）。
    需要 Chrome 已打开并登录 Reddit，且安装了 OpenCLI 扩展。"""
    return _run(["opencli", "reddit", "search", query, "-f", "yaml"])


@tool
def reddit_read(post_id: str) -> str:
    """读取 Reddit 帖子全文和评论（通过 OpenCLI）。post_id 从搜索结果中获取。"""
    return _run(["opencli", "reddit", "read", post_id, "-f", "yaml"])


@tool
def reddit_hot() -> str:
    """获取 Reddit 当前热门帖子。"""
    return _run(["opencli", "reddit", "hot", "-f", "yaml"])


@tool
def reddit_subreddit(name: str) -> str:
    """浏览指定 subreddit 的最新帖子。name 为 subreddit 名称（不含 r/）。"""
    return _run(["opencli", "reddit", "subreddit", name, "-f", "yaml"])
