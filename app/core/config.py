from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from ..models import Topic, WorkflowConfig
from .prompts import DEFAULT_ANSWER_STYLE, DEFAULT_SYSTEM_PROMPT

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
ENV_PATH = ROOT_DIR / ".env"
OUTPUT_DIR = ROOT_DIR / "output"
COOKIE_PATH_DEFAULT = ROOT_DIR / ".secrets" / "zhihu.cookie"


def load_env_file() -> None:
    load_dotenv(ENV_PATH, override=False)


def get_required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"Missing required env: {name}")
    return value


def parse_positive_int(value: Any, fallback: int) -> int:
    try:
        parsed = int(value)
        return parsed if parsed > 0 else fallback
    except (TypeError, ValueError):
        return fallback


def is_truthy(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def get_default_topics() -> list[Topic]:
    return [
        Topic(id="algo", name="数据结构与算法", keywords=["数据结构", "算法", "二叉树", "链表", "动态规划", "leetcode"]),
        Topic(id="personal-site", name="个人站点", keywords=["个人站点", "独立站", "博客", "建站", "个人主页"]),
        Topic(id="podcast", name="播客", keywords=["播客", "podcast", "音频节目", "内容创作"]),
    ]


def get_workflow_config(overrides: dict[str, Any] | None = None) -> WorkflowConfig:
    overrides = overrides or {}
    max_push_count = min(parse_positive_int(overrides.get("maxPushCount", os.getenv("MAX_PUSH_COUNT")), 10), 10)
    sort_modes = [
        part.strip()
        for part in str(overrides.get("sortModes", os.getenv("SORT_MODES", "latest,answer_count"))).split(",")
        if part.strip()
    ]
    answer_style = overrides.get("answerStyle") or os.getenv("ANSWER_STYLE", DEFAULT_ANSWER_STYLE)
    system_prompt = overrides.get("systemPrompt") or os.getenv("SYSTEM_PROMPT", DEFAULT_SYSTEM_PROMPT)
    test_mode = is_truthy(overrides.get("testMode", os.getenv("TEST_MODE", "true")))
    skip_answer_generation = is_truthy(
        overrides.get("skipAnswerGeneration", os.getenv("SKIP_ANSWER_GENERATION", "false"))
    )
    user_agent = overrides.get("userAgent") or os.getenv(
        "HTTP_USER_AGENT",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
    )
    cta_text = (
        ""
        if test_mode
        else os.getenv("OFFICIAL_ACCOUNT_CTA", "更多专题内容，欢迎关注公众号：{{OFFICIAL_ACCOUNT_NAME}}").replace(
            "{{OFFICIAL_ACCOUNT_NAME}}", os.getenv("OFFICIAL_ACCOUNT_NAME", "你的公众号")
        )
    )
    return WorkflowConfig(
        maxPushCount=max_push_count,
        sortModes=sort_modes,
        answerStyle=answer_style,
        systemPrompt=system_prompt,
        testMode=test_mode,
        skipAnswerGeneration=skip_answer_generation,
        userAgent=user_agent,
        ctaText=cta_text,
        outputDir=str(Path(os.getenv("OUTPUT_DIR", "./output")).resolve()),
    )
