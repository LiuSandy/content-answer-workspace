"""Bilibili 工具；通过 bili-cli 调用 B 站搜索、热榜和视频详情。"""

from __future__ import annotations

import subprocess

from langchain_core.tools import tool

_PLATFORM = "bilibili"
_MAX_CHARS = 6000


def _run(args: list[str]) -> str:
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=30)
        return (result.stdout or result.stderr or "无结果")[:_MAX_CHARS]
    except FileNotFoundError:
        return f"[{_PLATFORM}] bili-cli 未安装，请运行 `pipx install bili-cli`。"
    except subprocess.TimeoutExpired:
        return f"[{_PLATFORM}] 请求超时（30s）。"
    except Exception as e:  # noqa: BLE001
        return f"[{_PLATFORM}] 调用失败：{e}"


@tool
def bilibili_search(query: str, limit: int = 5) -> str:
    """在 B 站搜索视频，返回标题、BV 号、UP 主、播放量等信息。"""
    return _run(["bili", "search", query, "--type", "video", "-n", str(limit)])


@tool
def bilibili_hot(limit: int = 10) -> str:
    """获取 B 站当前热门视频排行榜。"""
    return _run(["bili", "hot", "-n", str(limit)])


@tool
def bilibili_video(bvid: str) -> str:
    """获取 B 站视频详情（标题、简介、分P信息）。bvid 格式如 BV1xx411c7mD。"""
    return _run(["bili", "video", bvid])
