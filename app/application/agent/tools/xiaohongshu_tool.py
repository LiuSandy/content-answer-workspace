"""小红书工具；通过 OpenCLI（复用 Chrome 浏览器登录态）搜索和读取笔记。
需要：① Chrome 已打开 ② 装了 OpenCLI 扩展 ③ 在 Chrome 中已登录小红书。

约束由工具层保证（不依赖 LLM 判断）：
  - 按发布时间从新到旧排序（published_at 降序）
  - 精确限制返回条数（top_n）
  - 按 URL 去重
"""

from __future__ import annotations

import json
import logging
import subprocess

logger = logging.getLogger(__name__)

import yaml
from langchain_core.tools import tool

_PLATFORM = "xiaohongshu"
_MAX_CHARS = 100000
_MAX_ITEMS = 20


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


def _parse_yaml_list(raw: str) -> list[dict]:
    """将 opencli YAML 输出解析为 dict 列表；解析失败返回空列表。"""
    try:
        # 剔除常见的 npm/cli 调试和更新提示等非 YAML 行
        clean_lines = []
        for line in raw.splitlines():
            if "Update available" in line or "npm install" in line or "Run:" in line:
                break
            clean_lines.append(line)
        cleaned_raw = "\n".join(clean_lines).strip()

        data = yaml.safe_load(cleaned_raw)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _normalize_item(item: dict) -> dict:
    """规范化小红书条目字段名，兼容 opencli 不同版本的输出差异。"""
    title = item.get("title") or item.get("name") or ""
    url = item.get("url") or item.get("link") or item.get("note_url") or ""
    excerpt = (item.get("desc") or item.get("content") or item.get("summary") or "")[:120]
    raw_likes = item.get("likes") or item.get("liked_count") or item.get("like_count") or 0
    likes = int(raw_likes) if str(raw_likes).isdigit() else 0
    author = str(item.get("author") or item.get("user") or item.get("username") or "")
    metric = f"{likes:,} 赞" if likes > 0 else ""
    published_at = str(item.get("published_at") or item.get("time") or item.get("lastUpdateTime") or "")
    return {
        "title": title,
        "url": url,
        "excerpt": excerpt,
        "metric": metric,
        "likes": likes,
        "author": author,
        "published_at": published_at,
    }


def _sort_by_recent(items: list[dict]) -> list[dict]:
    """按 published_at 从新到旧排序；无有效时间的条目排最后。"""
    def _key(it: dict) -> str:
        return it.get("published_at") or ""

    return sorted(items, key=_key, reverse=True)


def _dedupe(items: list[dict]) -> list[dict]:
    """按 URL 去重；无 URL 的条目直接丢弃（无法可靠去重）。"""
    seen: set[str] = set()
    unique: list[dict] = []
    for it in items:
        key = it.get("url") or ""
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(it)
    return unique


@tool
def xiaohongshu_search(query: str, limit: int = 5, min_likes: int = 0) -> str:
    """在小红书搜索笔记，返回结构化 JSON，每条包含标题、链接、摘要、点赞数、作者和发布时间。
    结果按发布时间从新到旧排序、去重，只保留点赞数 >= min_likes 的，并精确返回 limit 条。
    若满足条件的不足 limit 条，返回所有满足的并标注 conflict 信息（total_found / filtered_out），
    交由 Agent 决定是否询问用户（human-in-the-loop）。
    需要 Chrome 已打开并登录小红书，且安装了 OpenCLI 扩展。"""
    raw = _run(["opencli", "xiaohongshu", "search", query, "-f", "yaml"])
    raw_items = _parse_yaml_list(raw)
    logger.debug(
        "Xiaohongshu search response parsed",
        extra={"result_count": len(raw_items), "min_likes": min_likes},
    )
    if not raw_items:
        logger.warning("[xiaohongshu_search] parse failed, raw_items is empty.")
        return json.dumps({"platform": _PLATFORM, "topic": query, "error": raw, "items": []}, ensure_ascii=False)

    top_n = max(1, min(int(limit), _MAX_ITEMS))
    items = [_normalize_item(i) for i in raw_items if i.get("title") or i.get("name")]
    items = _sort_by_recent(items)
    items = _dedupe(items)

    # 点赞过滤：优先用数值 likes，退化到从 metric 文本提取数字
    def _likes_num(it: dict) -> int:
        val = it.get("likes")
        if isinstance(val, int):
            return val
        raw_likes = (it.get("metric") or "0")
        digits = "".join(ch for ch in str(raw_likes) if ch.isdigit())
        return int(digits) if digits else 0

    if min_likes and min_likes > 0:
        passed = [it for it in items if _likes_num(it) >= min_likes]
        filtered_out = len(items) - len(passed)
        items = passed
    else:
        filtered_out = 0

    total_found = len(items)
    result = {"platform": _PLATFORM, "topic": query, "items": items[:top_n]}
    if total_found < top_n:
        result["conflict"] = {
            "requested": top_n,
            "total_found": total_found,
            "filtered_out": filtered_out,
            "reason": f"only {total_found} results meet the constraints (publish time sort + min_likes={min_likes or 0})",
        }
    return json.dumps(result, ensure_ascii=False)


@tool
def xiaohongshu_note(note_url: str) -> str:
    """读取小红书笔记正文和互动数据。note_url 须为搜索结果中的完整 URL（含 xsec_token）。"""
    return _run(["opencli", "xiaohongshu", "note", note_url, "-f", "yaml"])


@tool
def xiaohongshu_feed() -> str:
    """获取小红书首页推荐 feed，返回标题、链接、点赞数等结构化结果。"""
    raw = _run(["opencli", "xiaohongshu", "feed", "-f", "yaml"])
    raw_items = _parse_yaml_list(raw)
    if not raw_items:
        return json.dumps({"platform": _PLATFORM, "topic": "推荐", "error": raw or "无结果", "items": []}, ensure_ascii=False)
    items = [_normalize_item(i) for i in raw_items[:_MAX_ITEMS] if i.get("title") or i.get("name")]
    items = _sort_by_recent(items)
    items = _dedupe(items)
    return json.dumps({"platform": _PLATFORM, "topic": "推荐", "items": items}, ensure_ascii=False)
