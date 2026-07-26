from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from ..config.loader import get_settings, load_default_topics
from ..models import Topic, WorkflowConfig

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
ENV_PATH = ROOT_DIR / ".env"
OUTPUT_DIR = ROOT_DIR / "output"
GENERATED_IMAGES_DIR = ROOT_DIR / "generated-images"
COOKIE_PATH_DEFAULT = ROOT_DIR / ".secrets" / "zhihu.cookie"
XIAOHONGSHU_COOKIE_PATH_DEFAULT = ROOT_DIR / ".secrets" / "xiaohongshu.cookie"
DEFAULT_PLATFORM = get_settings().collect.default_platform
MAX_PUSH_COUNT_LIMIT = get_settings().collect.max_push_count_limit


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
    """提供后端默认主题；主题定义已外置到 default_topics.toml，这里只负责按 preset 组装成 Topic。"""

    topics: list[Topic] = []
    for entry in load_default_topics():
        topics.append(
            Topic(
                id=entry["id"],
                name=entry["name"],
                keywords=entry.get("keywords", []),
            )
        )
    return topics


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
    test_mode = is_truthy(overrides.get("testMode", os.getenv("TEST_MODE", "true")))
    skip_answer_generation = is_truthy(
        overrides.get("skipAnswerGeneration", os.getenv("SKIP_ANSWER_GENERATION", "false"))
    )
    user_agent = overrides.get("userAgent") or os.getenv(
        "HTTP_USER_AGENT",
        get_settings().http.user_agent,
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
        test_mode=test_mode,
        skipAnswerGeneration=skip_answer_generation,
        userAgent=user_agent,
        ctaText=cta_text,
        outputDir=str(Path(os.getenv("OUTPUT_DIR", "./output")).resolve()),
    )


from dataclasses import dataclass, field


@dataclass(frozen=True)
class KnowledgeSettings:
    sources_dir: Path = field(default_factory=lambda: (OUTPUT_DIR / "knowledge" / "sources").resolve())
    documents_dir: Path = field(default_factory=lambda: (OUTPUT_DIR / "knowledge" / "documents").resolve())
    embedding_dimensions: int = 1536
    parent_chunk_max_tokens: int = 1200
    child_chunk_max_tokens: int = 350
    child_chunk_overlap_tokens: int = 50
    bm25_top_k: int = 20
    vector_top_k: int = 20
    rrf_k: int = 60
    reranker_top_k: int = 8
    evidence_threshold: float = 0.55
    context_token_budget: int = 6000
    embedding_api_key: str = field(default_factory=lambda: os.getenv("EMBEDDING_API_KEY", os.getenv("OPENAI_API_KEY", "")), repr=False)
    embedding_base_url: str = field(default_factory=lambda: os.getenv("EMBEDDING_BASE_URL", os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")))
    embedding_model: str = field(default_factory=lambda: os.getenv("EMBEDDING_MODEL", "text-embedding-3-small"))
    # 单次 embedding 请求的批大小；默认 20 以兼容阿里云百炼等上限较低的服务
    embedding_batch_size: int = 20
    ocr_api_key: str = field(default_factory=lambda: os.getenv("OCR_API_KEY", os.getenv("OPENAI_API_KEY", "")), repr=False)
    ocr_base_url: str = field(default_factory=lambda: os.getenv("OCR_BASE_URL", os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")))
    ocr_model: str = field(default_factory=lambda: os.getenv("OCR_MODEL", "gpt-4o-mini"))
    reranker_api_key: str = field(default_factory=lambda: os.getenv("RERANKER_API_KEY", os.getenv("OPENAI_API_KEY", "")), repr=False)
    reranker_base_url: str = field(default_factory=lambda: os.getenv("RERANKER_BASE_URL", os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")))
    reranker_model: str = field(default_factory=lambda: os.getenv("RERANKER_MODEL", "gpt-4o-mini"))
    mineru_api_key: str = field(default_factory=lambda: os.getenv("MINERU_API_KEY", ""), repr=False)
    mineru_api_base_url: str = field(default_factory=lambda: os.getenv("MINERU_API_BASE_URL", "https://mineru.net/api/v4"))
    mineru_model_version: str = field(default_factory=lambda: os.getenv("MINERU_MODEL_VERSION", "vlm"))
    pdf_max_pages_per_chunk: int = 150
    pdf_max_bytes_per_chunk: int = 150 * 1024 * 1024
    # 单文件上传上限；防止超大文件全量读入内存造成 DoS
    max_upload_bytes: int = 50 * 1024 * 1024


def get_knowledge_settings() -> KnowledgeSettings:
    load_env_file()
    sources_dir = Path(os.getenv("KNOWLEDGE_SOURCES_DIR", OUTPUT_DIR / "knowledge" / "sources")).resolve()
    documents_dir = Path(os.getenv("KNOWLEDGE_DOCUMENTS_DIR", OUTPUT_DIR / "knowledge" / "documents")).resolve()
    embedding_dims = parse_positive_int(os.getenv("EMBEDDING_DIMENSIONS"), 1536)
    rrf_k = parse_positive_int(os.getenv("KNOWLEDGE_RRF_K"), 60)

    try:
        threshold = float(os.getenv("KNOWLEDGE_EVIDENCE_THRESHOLD", "0.55"))
        if threshold <= 0 or threshold >= 1:
            threshold = 0.55
    except ValueError:
        threshold = 0.55

    return KnowledgeSettings(
        sources_dir=sources_dir,
        documents_dir=documents_dir,
        embedding_dimensions=embedding_dims,
        rrf_k=rrf_k,
        evidence_threshold=threshold,
        parent_chunk_max_tokens=parse_positive_int(os.getenv("KNOWLEDGE_PARENT_CHUNK_MAX_TOKENS"), 1200),
        child_chunk_max_tokens=parse_positive_int(os.getenv("KNOWLEDGE_CHILD_CHUNK_MAX_TOKENS"), 350),
        context_token_budget=parse_positive_int(os.getenv("KNOWLEDGE_CONTEXT_TOKEN_BUDGET"), 6000),
        max_upload_bytes=parse_positive_int(os.getenv("KNOWLEDGE_MAX_UPLOAD_BYTES"), 50 * 1024 * 1024),
        embedding_batch_size=parse_positive_int(os.getenv("EMBEDDING_BATCH_SIZE"), 20),
    )

