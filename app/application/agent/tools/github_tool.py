"""GitHub 工具；通过 gh CLI 搜索仓库，返回标准化采集卡片 JSON。"""

from __future__ import annotations

import json
import subprocess

from langchain_core.tools import tool

_PLATFORM = "github"
_MAX_CHARS = 6000
_MAX_ITEMS = 20


def _to_result(topic: str, items: list[dict]) -> str:
    return json.dumps(
        {"platform": _PLATFORM, "topic": topic, "items": items[:_MAX_ITEMS]},
        ensure_ascii=False,
    )


def _error_result(topic: str, msg: str) -> str:
    return json.dumps({"platform": _PLATFORM, "topic": topic, "error": msg, "items": []}, ensure_ascii=False)


@tool
def github_search_repos(query: str, limit: int = 10) -> str:
    """在 GitHub 搜索仓库，返回仓库名、Star 数、简介等结构化结果。需要已安装并登录 gh CLI。"""
    try:
        result = subprocess.run(
            ["gh", "search", "repos", query, "--limit", str(limit),
             "--json", "fullName,description,stargazersCount,url"],
            capture_output=True, text=True, timeout=30,
        )
        raw = result.stdout or result.stderr or ""
        if not raw:
            return _error_result(query, "无结果")

        entries = json.loads(raw)
        if not isinstance(entries, list):
            return _error_result(query, "响应格式异常")

        items = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            name = str(entry.get("fullName") or "")
            url = str(entry.get("url") or "")
            excerpt = str(entry.get("description") or "")[:200]
            stars = entry.get("stargazersCount") or 0
            metric = f"⭐ {int(stars):,}" if stars else ""
            if name:
                items.append({"title": name, "url": url, "excerpt": excerpt, "metric": metric, "author": ""})

        return _to_result(query, items) if items else _error_result(query, "未找到相关仓库")

    except FileNotFoundError:
        return _error_result(query, "gh CLI 未安装，请先安装 GitHub CLI。")
    except subprocess.TimeoutExpired:
        return _error_result(query, "请求超时（30s）。")
    except json.JSONDecodeError:
        return _error_result(query, "响应解析失败。")
    except Exception as e:  # noqa: BLE001
        return _error_result(query, str(e))


@tool
def github_repo_info(owner_repo: str) -> str:
    """获取 GitHub 仓库详情（README 摘要、Star 数、最近 issue）。格式：owner/repo"""
    try:
        result = subprocess.run(
            ["gh", "repo", "view", owner_repo,
             "--json", "name,description,stargazersCount,url,readme,repositoryTopics"],
            capture_output=True, text=True, timeout=30,
        )
        return (result.stdout or result.stderr or "无结果")[:_MAX_CHARS]
    except FileNotFoundError:
        return f"[{_PLATFORM}] gh CLI 未安装，请先安装 GitHub CLI。"
    except subprocess.TimeoutExpired:
        return f"[{_PLATFORM}] 请求超时（30s）。"
    except Exception as e:  # noqa: BLE001
        return f"[{_PLATFORM}] 调用失败：{e}"
