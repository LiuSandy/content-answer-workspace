"""YouTube 工具；通过 yt-dlp 下载字幕并提取视频信息。"""

from __future__ import annotations

import subprocess

from langchain_core.tools import tool

_PLATFORM = "youtube"
_MAX_CHARS = 6000


def _run(args: list[str]) -> str:
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=60)
        return (result.stdout or result.stderr or "无结果")[:_MAX_CHARS]
    except FileNotFoundError:
        return f"[{_PLATFORM}] yt-dlp 未安装，请运行 `pip install yt-dlp`。"
    except subprocess.TimeoutExpired:
        return f"[{_PLATFORM}] 请求超时（60s）。"
    except Exception as e:  # noqa: BLE001
        return f"[{_PLATFORM}] 调用失败：{e}"


@tool
def youtube_fetch(url: str) -> str:
    """获取 YouTube 视频的标题、描述和字幕（优先中文，回落英文）。"""
    # 先获取标题和描述
    info = _run(["yt-dlp", "--print", "%(title)s\n%(description)s", "--no-download", url])
    # 再下载字幕到 /tmp
    subtitle = _run([
        "yt-dlp",
        "--write-auto-sub", "--sub-lang", "zh-Hans,zh,en",
        "--skip-download", "--convert-subs", "srt",
        "-o", "/tmp/yt_%(id)s.%(ext)s",
        "--print", "after_move:filepath",
        url,
    ])
    return f"{info}\n\n[字幕文件] {subtitle}"[:_MAX_CHARS]
