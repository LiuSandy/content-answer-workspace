"""小红书工具；通过 OpenCLI（复用 Chrome 浏览器登录态）搜索和读取笔记。
需要：① Chrome 已打开 ② 装了 OpenCLI 扩展 ③ 在 Chrome 中已登录小红书。"""

from __future__ import annotations

import subprocess

from langchain_core.tools import tool

_PLATFORM = "xiaohongshu"
_MAX_CHARS = 6000


def _run(args: list[str]) -> str:
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=30)
        output = result.stdout or result.stderr or "无结果"
        if "AUTH_REQUIRED" in output:
            return f"[{_PLATFORM}] 需要登录：请在 Chrome 中打开小红书并登录，然后重试。"
        return output[:_MAX_CHARS]
    except FileNotFoundError:
        return f"[{_PLATFORM}] opencli 未安装，请安装 OpenCLI Chrome 扩展后重试。"
    except subprocess.TimeoutExpired:
        return f"[{_PLATFORM}] 请求超时（30s）。"
    except Exception as e:  # noqa: BLE001
        return f"[{_PLATFORM}] 调用失败：{e}"


@tool
def xiaohongshu_search(query: str) -> str:
    """在小红书搜索笔记，返回标题、作者、点赞数和链接（YAML 格式）。
    需要 Chrome 已打开并登录小红书，且安装了 OpenCLI 扩展。"""
    return _run(["opencli", "xiaohongshu", "search", query, "-f", "yaml"])


@tool
def xiaohongshu_note(note_url: str) -> str:
    """读取小红书笔记正文和互动数据。note_url 须为搜索结果中的完整 URL（含 xsec_token）。"""
    return _run(["opencli", "xiaohongshu", "note", note_url, "-f", "yaml"])


@tool
def xiaohongshu_feed() -> str:
    """获取小红书首页推荐 feed。"""
    return _run(["opencli", "xiaohongshu", "feed", "-f", "yaml"])
