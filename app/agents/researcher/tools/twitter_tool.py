"""Twitter/X 工具；通过 OpenCLI 搜索和读取推文，返回标准化采集卡片 JSON。
认证方式：Chrome 已登录 Twitter/X 且安装了 OpenCLI 扩展。"""

from __future__ import annotations

import json
import subprocess

import yaml
from langchain_core.tools import tool

_PLATFORM = "twitter"
_MAX_CHARS = 6000
_MAX_ITEMS = 20


def _run(args: list[str]) -> str:
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=30)
        output = result.stdout or result.stderr or ""
        if "AUTH_REQUIRED" in output:
            return f"[{_PLATFORM}] 需要登录：请在 Chrome 中打开 Twitter/X 并登录，然后重试。"
        return output[:_MAX_CHARS]
    except FileNotFoundError:
        return f"[{_PLATFORM}] opencli 未安装，请安装 OpenCLI Chrome 扩展后重试。"
    except subprocess.TimeoutExpired:
        return f"[{_PLATFORM}] 请求超时（30s）。"
    except Exception as e:  # noqa: BLE001
        return f"[{_PLATFORM}] 调用失败：{e}"


def _parse_yaml_list(raw: str) -> list[dict]:
    try:
        data = yaml.safe_load(raw)
        # opencli 格式：{ok, data: [...]} 或直接 [...]
        if isinstance(data, dict):
            inner = data.get("data") or []
            return inner if isinstance(inner, list) else []
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _normalize_tweet(item: dict) -> dict | None:
    """将 opencli twitter YAML 条目映射为统一输出格式。"""
    text = str(item.get("text") or "").strip()
    url = str(item.get("url") or "")
    author = str(item.get("author") or "")
    likes = item.get("likes") or 0
    views = item.get("views") or ""
    metric_parts = []
    if likes:
        metric_parts.append(f"{int(likes):,} 赞")
    if views:
        metric_parts.append(f"{views} 浏览")
    if not text and not url:
        return None
    title = text[:80] + ("…" if len(text) > 80 else "")
    excerpt = text[:200]
    return {
        "title": title,
        "url": url,
        "excerpt": excerpt,
        "metric": " · ".join(metric_parts),
        "author": f"@{author}" if author and not author.startswith("@") else author,
    }


def _to_result(topic: str, items: list[dict]) -> str:
    return json.dumps(
        {"platform": _PLATFORM, "topic": topic, "items": items[:_MAX_ITEMS]},
        ensure_ascii=False,
    )


def _error_result(topic: str, msg: str) -> str:
    return json.dumps({"platform": _PLATFORM, "topic": topic, "error": msg, "items": []}, ensure_ascii=False)


@tool
def twitter_search(query: str, limit: int = 10) -> str:
    """在 Twitter/X 搜索推文，返回推文内容、作者、点赞数等结构化结果。
    需要 Chrome 已登录 Twitter/X 且安装了 OpenCLI 扩展。"""
    raw = _run(["opencli", "twitter", "search", query, "-n", str(limit), "-f", "yaml"])
    entries = _parse_yaml_list(raw)
    if not entries:
        return _error_result(query, raw if raw.startswith(f"[{_PLATFORM}]") else "未找到相关推文")
    items = [n for entry in entries if (n := _normalize_tweet(entry))]
    return _to_result(query, items) if items else _error_result(query, "未找到相关推文")


@tool
def twitter_feed(limit: int = 20) -> str:
    """获取 Twitter/X 首页时间线推文，返回推文内容、作者、互动数等结构化结果。
    需要 Chrome 已登录 Twitter/X 且安装了 OpenCLI 扩展。"""
    raw = _run(["opencli", "twitter", "timeline", "-n", str(limit), "-f", "yaml"])
    entries = _parse_yaml_list(raw)
    if not entries:
        return _error_result("时间线", raw if raw.startswith(f"[{_PLATFORM}]") else "无法获取时间线")
    items = [n for entry in entries if (n := _normalize_tweet(entry))]
    return _to_result("时间线", items) if items else _error_result("时间线", "无法获取时间线")


@tool
def twitter_user_posts(username: str, limit: int = 20) -> str:
    """获取指定 Twitter/X 用户的最新推文列表。username 格式：@handle 或 handle。"""
    handle = username.lstrip("@")
    raw = _run(["opencli", "twitter", "tweets", handle, "-n", str(limit), "-f", "yaml"])
    entries = _parse_yaml_list(raw)
    if not entries:
        return _error_result(f"@{handle}", raw if raw.startswith(f"[{_PLATFORM}]") else "未找到推文")
    items = [n for entry in entries if (n := _normalize_tweet(entry))]
    return _to_result(f"@{handle}", items) if items else _error_result(f"@{handle}", "未找到推文")


@tool
def twitter_read(url_or_id: str) -> str:
    """读取单条推文及其回复线程。支持推文 URL 或 ID。"""
    return _run(["opencli", "twitter", "thread", url_or_id, "-f", "yaml"])
