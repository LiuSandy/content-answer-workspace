"""Bilibili 工具；通过 opencli 搜索和热榜，返回标准化采集卡片 JSON。"""

from __future__ import annotations

import json
import subprocess

import yaml
from langchain_core.tools import tool

_PLATFORM = "bilibili"
_MAX_CHARS = 6000
_MAX_ITEMS = 20


def _run(args: list[str]) -> str:
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=30)
        output = result.stdout or result.stderr or ""
        if "AUTH_REQUIRED" in output:
            return f"[{_PLATFORM}] 需要登录：请在 Chrome 中打开 Bilibili 并登录，然后重试。"
        return output[:_MAX_CHARS]
    except FileNotFoundError:
        return ""
    except subprocess.TimeoutExpired:
        return f"[{_PLATFORM}] 请求超时（30s）。"
    except Exception as e:  # noqa: BLE001
        return f"[{_PLATFORM}] 调用失败：{e}"


def _parse_yaml(raw: str) -> list[dict] | dict | None:
    try:
        return yaml.safe_load(raw)
    except Exception:
        return None


def _to_result(topic: str, items: list[dict]) -> str:
    return json.dumps(
        {"platform": _PLATFORM, "topic": topic, "items": items[:_MAX_ITEMS]},
        ensure_ascii=False,
    )


def _error_result(topic: str, msg: str) -> str:
    return json.dumps({"platform": _PLATFORM, "topic": topic, "error": msg, "items": []}, ensure_ascii=False)


@tool
def bilibili_search(query: str, limit: int = 10) -> str:
    """在 Bilibili 搜索视频，返回标题、UP 主、播放量等结构化结果。
    需要 Chrome 已打开并登录 Bilibili，且安装了 OpenCLI 扩展。"""
    raw = _run(["opencli", "bilibili", "search", query, "-f", "yaml"])
    if not raw or raw.startswith(f"[{_PLATFORM}]"):
        return _error_result(query, raw or "无结果")

    data = _parse_yaml(raw)
    entries = data if isinstance(data, list) else []
    items = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        title = str(entry.get("title") or "")
        url = str(entry.get("url") or "")
        author = str(entry.get("author") or "")
        score = entry.get("score") or 0
        metric = f"{int(score):,} 播放" if score else ""
        if title:
            items.append({"title": title, "url": url, "excerpt": "", "metric": metric, "author": author})

    return _to_result(query, items) if items else _error_result(query, "未找到相关视频")


@tool
def bilibili_hot(limit: int = 10) -> str:
    """获取 Bilibili 当前热门视频排行榜，返回标题、UP 主、播放量结构化结果。"""
    raw = _run(["bili", "hot", "--yaml", "-n", str(limit)])
    if not raw or raw.startswith(f"[{_PLATFORM}]"):
        raw = _run(["opencli", "bilibili", "hot", "-f", "yaml"])
    if not raw or raw.startswith(f"[{_PLATFORM}]"):
        return _error_result("热门", raw or "无结果")

    data = _parse_yaml(raw)
    # bili hot --yaml: {ok, data: {items: [...]}}
    if isinstance(data, dict):
        entries = (data.get("data") or {}).get("items") or []
    elif isinstance(data, list):
        entries = data
    else:
        entries = []

    items = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        title = str(entry.get("title") or "")
        url = str(entry.get("url") or "")
        owner = entry.get("owner") or {}
        author = str(owner.get("name") or entry.get("author") or "")
        stats = entry.get("stats") or {}
        view = stats.get("view") or entry.get("score") or 0
        metric = f"{int(view):,} 播放" if view else ""
        if title:
            items.append({"title": title, "url": url, "excerpt": "", "metric": metric, "author": author})

    return _to_result("热门", items) if items else _error_result("热门", "未获取到热门视频")


@tool
def bilibili_video(bvid: str) -> str:
    """获取 Bilibili 视频详情（标题、简介、分P信息）。bvid 格式如 BV1xx411c7mD。"""
    try:
        result = subprocess.run(
            ["bili", "video", bvid], capture_output=True, text=True, timeout=30
        )
        return (result.stdout or result.stderr or "无结果")[:_MAX_CHARS]
    except FileNotFoundError:
        return f"[{_PLATFORM}] bili-cli 未安装，请运行 `pipx install bili-cli`。"
    except subprocess.TimeoutExpired:
        return f"[{_PLATFORM}] 请求超时（30s）。"
    except Exception as e:  # noqa: BLE001
        return f"[{_PLATFORM}] 调用失败：{e}"
