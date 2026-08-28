"""Reddit 工具；通过 OpenCLI 搜索和读取帖子，返回标准化采集卡片 JSON。
需要 Chrome 已打开并登录 Reddit，且安装了 OpenCLI 扩展。"""

from __future__ import annotations

import json
import subprocess

import yaml
from langchain_core.tools import tool

_PLATFORM = "reddit"
_MAX_CHARS = 6000
_MAX_ITEMS = 20


def _run(args: list[str]) -> str:
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=30)
        output = result.stdout or result.stderr or ""
        if "AUTH_REQUIRED" in output:
            return f"[{_PLATFORM}] 需要登录：请在 Chrome 中打开 Reddit 并登录，然后重试。"
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
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _normalize_post(item: dict) -> dict | None:
    """将 opencli reddit YAML 条目映射为统一输出格式。"""
    title = str(item.get("title") or "").strip()
    url = str(item.get("url") or "")
    author = str(item.get("author") or "")
    score = item.get("score") or 0
    comments = item.get("comments") or 0
    subreddit = str(item.get("subreddit") or "")
    excerpt = str(item.get("selftext") or "")[:200]
    metric_parts = []
    if score:
        metric_parts.append(f"{int(score):,} 赞")
    if comments:
        metric_parts.append(f"{int(comments)} 评论")
    if not title:
        return None
    return {
        "title": title,
        "url": url,
        "excerpt": excerpt,
        "metric": " · ".join(metric_parts),
        "author": f"u/{author}" if author else subreddit,
    }


def _to_result(topic: str, items: list[dict]) -> str:
    return json.dumps(
        {"platform": _PLATFORM, "topic": topic, "items": items[:_MAX_ITEMS]},
        ensure_ascii=False,
    )


def _error_result(topic: str, msg: str) -> str:
    return json.dumps({"platform": _PLATFORM, "topic": topic, "error": msg, "items": []}, ensure_ascii=False)


@tool
def reddit_search(query: str) -> str:
    """在 Reddit 搜索帖子，返回标题、作者、评分等结构化结果。
    需要 Chrome 已打开并登录 Reddit，且安装了 OpenCLI 扩展。"""
    raw = _run(["opencli", "reddit", "search", query, "-f", "yaml"])
    entries = _parse_yaml_list(raw)
    if not entries:
        return _error_result(query, raw if raw.startswith(f"[{_PLATFORM}]") else "未找到相关帖子")
    items = [n for entry in entries if (n := _normalize_post(entry))]
    return _to_result(query, items) if items else _error_result(query, "未找到相关帖子")


@tool
def reddit_hot() -> str:
    """获取 Reddit 当前热门帖子，返回标题、评分、评论数等结构化结果。"""
    raw = _run(["opencli", "reddit", "hot", "-f", "yaml"])
    entries = _parse_yaml_list(raw)
    if not entries:
        return _error_result("热门", raw if raw.startswith(f"[{_PLATFORM}]") else "无法获取热门帖子")
    items = [n for entry in entries if (n := _normalize_post(entry))]
    return _to_result("热门", items) if items else _error_result("热门", "无法获取热门帖子")


@tool
def reddit_subreddit(name: str) -> str:
    """浏览指定 subreddit 的最新帖子，返回标题、评分、评论数等结构化结果。
    name 为 subreddit 名称（不含 r/）。"""
    raw = _run(["opencli", "reddit", "subreddit", name, "-f", "yaml"])
    entries = _parse_yaml_list(raw)
    if not entries:
        return _error_result(f"r/{name}", raw if raw.startswith(f"[{_PLATFORM}]") else "无帖子")
    items = [n for entry in entries if (n := _normalize_post(entry))]
    return _to_result(f"r/{name}", items) if items else _error_result(f"r/{name}", "无帖子")


@tool
def reddit_read(post_id: str) -> str:
    """读取 Reddit 帖子全文和评论。post_id 从搜索结果中获取。"""
    return _run(["opencli", "reddit", "read", post_id, "-f", "yaml"])
