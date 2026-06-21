from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from ..models import Topic, WorkflowConfig
from .prompts import DEFAULT_ANSWER_STYLE, DEFAULT_SYSTEM_PROMPT, GLOBAL_GENERATION_PROMPT, TOPIC_PROMPT_PRESETS

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
ENV_PATH = ROOT_DIR / ".env"
OUTPUT_DIR = ROOT_DIR / "output"
GENERATED_IMAGES_DIR = ROOT_DIR / "generated-images"
COOKIE_PATH_DEFAULT = ROOT_DIR / ".secrets" / "zhihu.cookie"
XIAOHONGSHU_COOKIE_PATH_DEFAULT = ROOT_DIR / ".secrets" / "xiaohongshu.cookie"
DEFAULT_PLATFORM = "zhihu"
MAX_PUSH_COUNT_LIMIT = 100


def load_env_file() -> None:
    """加载项目根目录的 .env；这样后端入口、CLI 和测试都能复用同一套环境变量来源。"""

    load_dotenv(ENV_PATH, override=False)


def get_required_env(name: str) -> str:
    """读取必填环境变量；这样模型调用等关键路径能在缺配置时尽早给出明确错误。"""

    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"Missing required env: {name}")
    return value


def parse_positive_int(value: Any, fallback: int) -> int:
    """把外部输入解析成正整数；这样前端或环境变量传错值时可以安全回落到默认配置。"""

    try:
        parsed = int(value)
        return parsed if parsed > 0 else fallback
    except (TypeError, ValueError):
        return fallback


def is_truthy(value: Any) -> bool:
    """判断外部配置是否为真值；这样布尔环境变量可以兼容常见的字符串写法。"""

    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def get_default_topics() -> list[Topic]:
    """提供后端默认主题；这样当前前端不传主题或恢复失败时仍能按知乎默认场景运行。"""

    return [
        Topic(
            id="algo",
            name="数据结构与算法",
            keywords=["数据结构", "算法", "二叉树", "链表", "动态规划", "leetcode"],
            answerStyle=TOPIC_PROMPT_PRESETS["algo"]["answer_style"],
            systemPrompt=TOPIC_PROMPT_PRESETS["algo"]["system_prompt"],
        ),
        Topic(
            id="personal-site",
            name="个人站点",
            keywords=["个人站点", "独立站", "博客", "建站", "个人主页"],
            answerStyle=TOPIC_PROMPT_PRESETS["personal-site"]["answer_style"],
            systemPrompt=TOPIC_PROMPT_PRESETS["personal-site"]["system_prompt"],
        ),
        Topic(
            id="podcast",
            name="播客",
            keywords=["播客", "podcast", "音频节目", "内容创作"],
            answerStyle=TOPIC_PROMPT_PRESETS["podcast"]["answer_style"],
            systemPrompt=TOPIC_PROMPT_PRESETS["podcast"]["system_prompt"],
        ),
    ]


def get_workflow_config(overrides: dict[str, Any] | None = None) -> WorkflowConfig:
    """合并环境变量和请求覆盖项生成工作流配置；这样采集和生成流程始终使用同一份规范化配置。"""

    overrides = overrides or {}
    platform = str(overrides.get("platform") or os.getenv("DEFAULT_PLATFORM", DEFAULT_PLATFORM)).strip().lower()
    source = str(overrides.get("source") or os.getenv("ZHIHU_SOURCE_MODE", "auto")).strip().lower()
    content_mode = str(overrides.get("contentMode") or os.getenv("CONTENT_MODE", "answer")).strip().lower()
    max_push_count = min(
        parse_positive_int(overrides.get("maxPushCount", os.getenv("MAX_PUSH_COUNT")), 10),
        MAX_PUSH_COUNT_LIMIT,
    )
    sort_modes = [
        part.strip()
        for part in str(overrides.get("sortModes", os.getenv("SORT_MODES", "latest,answer_count"))).split(",")
        if part.strip()
    ]
    answer_style = overrides.get("answerStyle") or os.getenv("ANSWER_STYLE", DEFAULT_ANSWER_STYLE)
    system_prompt = overrides.get("systemPrompt") or os.getenv("SYSTEM_PROMPT", DEFAULT_SYSTEM_PROMPT)
    generation_prompt = overrides.get("generationPrompt") or os.getenv("GENERATION_PROMPT", GLOBAL_GENERATION_PROMPT)
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
        platform=platform or DEFAULT_PLATFORM,
        source=source,
        contentMode=content_mode,
        maxPushCount=max_push_count,
        sortModes=sort_modes,
        answerStyle=answer_style,
        systemPrompt=system_prompt,
        generationPrompt=generation_prompt,
        testMode=test_mode,
        skipAnswerGeneration=skip_answer_generation,
        userAgent=user_agent,
        ctaText=cta_text,
        outputDir=str(Path(os.getenv("OUTPUT_DIR", "./output")).resolve()),
    )
