"""GitHub 工具；通过 gh CLI 搜索仓库和读取 issue/PR 信息。"""

from __future__ import annotations

import subprocess

from langchain_core.tools import tool

_PLATFORM = "github"
_MAX_CHARS = 6000


@tool
def github_search_repos(query: str, limit: int = 10) -> str:
    """在 GitHub 搜索仓库，返回仓库名、Star 数量、简介。"""
    try:
        result = subprocess.run(
            ["gh", "search", "repos", query, "--limit", str(limit),
             "--json", "name,fullName,description,stargazersCount,url"],
            capture_output=True, text=True, timeout=30,
        )
        output = result.stdout or result.stderr or "无结果"
        return output[:_MAX_CHARS]
    except FileNotFoundError:
        return f"[{_PLATFORM}] gh CLI 未安装，请先安装 GitHub CLI。"
    except subprocess.TimeoutExpired:
        return f"[{_PLATFORM}] 请求超时（30s）。"
    except Exception as e:  # noqa: BLE001
        return f"[{_PLATFORM}] 调用失败：{e}"


@tool
def github_repo_info(owner_repo: str) -> str:
    """获取 GitHub 仓库详情（README 摘要、Star 数、最近 issue）。格式：owner/repo"""
    try:
        result = subprocess.run(
            ["gh", "repo", "view", owner_repo,
             "--json", "name,description,stargazersCount,url,readme,repositoryTopics"],
            capture_output=True, text=True, timeout=30,
        )
        output = result.stdout or result.stderr or "无结果"
        return output[:_MAX_CHARS]
    except FileNotFoundError:
        return f"[{_PLATFORM}] gh CLI 未安装，请先安装 GitHub CLI。"
    except subprocess.TimeoutExpired:
        return f"[{_PLATFORM}] 请求超时（30s）。"
    except Exception as e:  # noqa: BLE001
        return f"[{_PLATFORM}] 调用失败：{e}"
