from __future__ import annotations

import json
import os
import re
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

import httpx

from ..core.config import COOKIE_PATH_DEFAULT, get_default_topics, get_workflow_config, load_env_file
from ..models import QuestionItem, Topic, WorkflowResult, ZhihuSearchResponse

TOPIC_HINTS_PATH = Path(__file__).resolve().parent.parent / "core" / "topic_hints.json"


def unique_by(items: list[Any], key_fn) -> list[Any]:
    """按指定键去重并保持原顺序；这样采集结果可以稳定裁剪且不会重复展示同一问题。"""

    seen: set[str] = set()
    result: list[Any] = []
    for item in items:
        key = key_fn(item)
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def clean_text(value: Any) -> str:
    """清理 HTML 和实体字符；这样知乎返回的标题、摘要和正文能变成适合展示与匹配的纯文本。"""

    text = str(value or "")
    text = re.sub(r"<[^>]+>", " ", text)
    text = (
        text.replace("&nbsp;", " ")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
        .replace("&amp;", "&")
    )
    return re.sub(r"\s+", " ", text).strip()


def get_zhihu_question_web_url(question_id: str) -> str:
    """生成知乎问题网页链接；这样内部只存问题 id 时也能提供前端可打开的原始地址。"""

    return f"https://www.zhihu.com/question/{question_id}"


@lru_cache(maxsize=1)
def load_topic_hint_profiles() -> list[dict[str, Any]]:
    """加载主题扩展词配置；这样匹配词可以通过配置维护，而不是继续写死在采集代码里。"""

    try:
        payload = json.loads(TOPIC_HINTS_PATH.read_text("utf-8"))
    except FileNotFoundError:
        return []
    profiles = payload.get("profiles", [])
    return profiles if isinstance(profiles, list) else []


def get_topic_specific_hints(topic: Topic) -> list[str]:
    """按主题匹配配置中的扩展词；这样新增主题规则只需要改配置文件而不需要增加 if/else。"""

    topic_id = topic.id.lower()
    topic_name = topic.name.lower()
    hints: list[str] = []
    for profile in load_topic_hint_profiles():
        match = profile.get("match", {}) if isinstance(profile, dict) else {}
        match_ids = [str(value).lower() for value in match.get("ids", [])]
        match_names = [str(value).lower() for value in match.get("names", [])]
        if any(value in topic_id for value in match_ids) or any(value in topic_name for value in match_names):
            hints.extend(str(value).strip().lower() for value in profile.get("hints", []) if str(value).strip())
    return hints


def build_keyword_hints(topic: Topic) -> list[str]:
    """为主题构建扩展匹配词；这样知乎搜索结果可以用更宽的语义范围过滤出相关问题。"""

    raw_tokens = [
        token.strip().lower()
        for source in [topic.name, *topic.keywords]
        for token in re.split(r"[,，/\s、]+", str(source))
        if token.strip()
    ]
    return unique_by(raw_tokens + get_topic_specific_hints(topic), lambda item: item)


def get_topic_preview(topic: Topic) -> Topic:
    """返回带扩展词的主题视图；这样前端和采集流程都能看到后端实际使用的匹配依据。"""

    return Topic(
        id=topic.id,
        name=topic.name,
        keywords=topic.keywords,
        expandedHints=build_keyword_hints(topic),
    )


def question_matches_keyword(question: QuestionItem, keyword_hints: list[str]) -> bool:
    """判断问题是否命中主题关键词；这样搜索接口混入的非相关内容可以在本地被过滤。"""

    haystack = clean_text(" ".join([question.title, question.excerpt, question.detail])).lower()
    return bool(haystack) and any(hint in haystack for hint in keyword_hints)


def to_iso_time(value: Any) -> str | None:
    """把知乎时间字段转成 ISO 字符串；这样前端展示和本地保存能使用统一时间格式。"""

    if value in (None, ""):
        return None
    try:
        if isinstance(value, (int, float)) or str(value).isdigit():
            numeric = int(value)
            timestamp = numeric if numeric > 1_000_000_000_000 else numeric * 1000
            return datetime.fromtimestamp(timestamp / 1000).isoformat()
        return datetime.fromisoformat(str(value)).isoformat()
    except Exception:
        return None


def parse_json_response(response: httpx.Response, label: str) -> dict[str, Any]:
    """安全解析 HTTP JSON 响应；这样知乎风控返回 HTML 时能给出可诊断错误而不是静默失败。"""

    content_type = response.headers.get("content-type", "")
    text = response.text
    if "application/json" not in content_type.lower():
        preview = re.sub(r"\s+", " ", text[:300]).strip()
        raise ValueError(
            f"{label} returned non-JSON response: status={response.status_code} content-type={content_type or 'unknown'} body={preview}"
        )
    try:
        return response.json()
    except json.JSONDecodeError:
        preview = re.sub(r"\s+", " ", text[:300]).strip()
        raise ValueError(
            f"{label} returned invalid JSON: status={response.status_code} content-type={content_type} body={preview}"
        )


def read_optional_file(file_path: Path) -> str | None:
    """读取可选文本文件；这样 cookie 文件不存在时采集流程可以继续按无 cookie 模式尝试。"""

    try:
        return file_path.read_text("utf-8")
    except FileNotFoundError:
        return None


def load_zhihu_cookie() -> str | None:
    """加载知乎 cookie 内容；这样所有知乎请求都能复用统一的凭据读取规则。"""

    configured = os.getenv("ZHIHU_COOKIE_FILE", "").strip()
    cookie_path = Path(configured).resolve() if configured else COOKIE_PATH_DEFAULT
    content = read_optional_file(cookie_path)
    return content.strip() if content else None


def get_zhihu_signature_header() -> str | None:
    """读取知乎 x-zse-96 签名；这样采集前可以明确判断当前请求是否具备知乎接口所需凭据。"""

    value = os.getenv("ZHIHU_X_ZSE_96", "").strip()
    return value or None


def ensure_zhihu_request_credentials(cookie: str | None, signature: str | None) -> None:
    """校验知乎采集凭据；这样缺少 cookie 或签名时会返回可理解错误，而不是继续触发 400。"""

    missing = []
    if not cookie:
        missing.append("ZHIHU_COOKIE_FILE")
    if not signature:
        missing.append("ZHIHU_X_ZSE_96")
    if missing:
        raise ValueError(
            "知乎搜索接口需要有效的浏览器 Cookie 和 x-zse-96 签名；"
            f"当前缺少：{', '.join(missing)}。请在 .env 中配置 ZHIHU_COOKIE_FILE 和 ZHIHU_X_ZSE_96 后重启后端。"
        )


def map_search_item(raw: dict[str, Any], topic_name: str) -> QuestionItem | None:
    """把知乎原始搜索项映射为内部问题模型；这样外部响应结构变化不会直接污染工作流。"""

    object_data = raw.get("object") or {}
    if not isinstance(object_data, dict):
        return None

    raw_type = str(raw.get("type") or "").lower()
    object_type = str(object_data.get("type") or "").lower()
    if raw_type not in {"search_result", "answer", "question"} and object_type not in {"answer", "question"}:
        return None

    question = object_data.get("question") or {}
    if not isinstance(question, dict):
        return None

    question_id = question.get("id")
    title = clean_text(
        question.get("name")
        or question.get("title")
        or object_data.get("title")
        or object_data.get("excerpt")
    )
    if not question_id or not title:
        return None

    return QuestionItem(
        id=str(question_id),
        title=title,
        url=get_zhihu_question_web_url(str(question_id)),
        answerCount=int(question.get("answer_count") or object_data.get("answer_count") or 0),
        updatedTime=to_iso_time(object_data.get("updated_time") or object_data.get("created_time")),
        excerpt=clean_text(object_data.get("excerpt") or object_data.get("description") or ""),
        detail=clean_text(object_data.get("content") or ""),
        topic=topic_name,
    )


async def fetch_question_details(item: QuestionItem, user_agent: str) -> QuestionItem:
    """补抓知乎问题详情页信息；这样搜索结果缺失或不准的标题、时间和回答数可以被修正。"""

    cookie = load_zhihu_cookie()
    headers = {
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml",
        "Referer": "https://www.zhihu.com/",
    }
    if cookie:
        headers["Cookie"] = cookie
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        response = await client.get(item.url, headers=headers)
    if response.status_code >= 400:
        return item
    html = response.text
    title_match = re.search(r'<meta\s+property="og:title"\s+content="([^"]+)"', html, re.I)
    date_match = re.search(r'"updated_time":\s*(\d{10})', html, re.I) or re.search(
        r'<meta\s+itemprop="dateModified"\s+content="([^"]+)"', html, re.I
    )
    answer_match = re.search(r'"answer_count":\s*(\d+)', html, re.I) or re.search(
        r'"answerCount":\s*(\d+)', html, re.I
    )
    return item.model_copy(
        update={
            "title": clean_text((title_match.group(1) if title_match else item.title).replace(" - 知乎", "")),
            "updated_time": to_iso_time(date_match.group(1)) if date_match else item.updated_time,
            "answer_count": int(answer_match.group(1)) if answer_match else item.answer_count,
        }
    )


async def fetch_zhihu_results_for_topic(topic: Topic, user_agent: str) -> list[QuestionItem]:
    """按单个主题请求知乎搜索接口；这样知乎平台策略可以复用完整的搜索、过滤和详情补全流程。"""

    cookie = load_zhihu_cookie()
    signature = get_zhihu_signature_header()
    ensure_zhihu_request_credentials(cookie, signature)
    url_base = os.getenv("ZHIHU_API_URL", "https://api.zhihu.com/search_v3").strip()
    referer_query = httpx.QueryParams({"type": "content", "q": topic.name})
    referer = os.getenv("ZHIHU_REFERER", f"https://www.zhihu.com/search?{referer_query}").strip()
    params = {
        "advert_count": "0",
        "gk_version": "gz-gaokao",
        "t": "general",
        "q": topic.name,
        "correction": "1",
        "offset": "0",
        "limit": "20",
        "filter_fields": "",
        "lc_idx": "0",
        "show_all_topics": "0",
        "search_source": "Normal",
    }
    headers = {
        "User-Agent": user_agent,
        "Accept": "*/*",
        "Referer": referer,
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "X-Requested-With": os.getenv("ZHIHU_X_REQUESTED_WITH", "fetch"),
    }
    if os.getenv("ZHIHU_X_ZSE_93", "").strip():
        headers["x-zse-93"] = os.getenv("ZHIHU_X_ZSE_93", "").strip()
    if signature:
        headers["x-zse-96"] = signature
    if cookie:
        headers["Cookie"] = cookie

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        response = await client.get(url_base, params=params, headers=headers)

    if response.status_code >= 400:
        preview = re.sub(r"\s+", " ", response.text[:300]).strip()
        raise ValueError(
            f"Zhihu request failed: {response.status_code} {response.reason_phrase}; "
            f"url={response.url}; body={preview or 'empty'}"
        )

    payload = ZhihuSearchResponse.model_validate(parse_json_response(response, "Zhihu API"))
    keyword_hints = build_keyword_hints(topic)
    items = [
        item for item in
        (map_search_item(row, topic.name) for row in payload.data)
        if item and question_matches_keyword(item, keyword_hints)
    ]
    items = unique_by(items, lambda item: item.id)[:12]
    detailed: list[QuestionItem] = []
    for item in items:
        detailed.append(await fetch_question_details(item, user_agent))
    return detailed


async def collect_questions(options: dict[str, Any] | None = None) -> WorkflowResult:
    """执行旧版知乎采集流程；这样历史导入仍能工作，同时新架构可以逐步迁移到采集器策略。"""

    load_env_file()
    options = options or {}
    config = get_workflow_config(options)
    topics = (
        [get_topic_preview(Topic.model_validate(topic)) for topic in options.get("topics", [])]
        if options.get("topics")
        else [get_topic_preview(topic) for topic in get_default_topics()]
    )

    all_items: list[QuestionItem] = []
    for topic in topics:
        all_items.extend(await fetch_zhihu_results_for_topic(topic, config.user_agent))

    deduplicated = unique_by(all_items, lambda item: f"{item.topic}:{item.id}")[: config.max_push_count]
    if not deduplicated:
        raise ValueError("No matching questions fetched")

    return WorkflowResult(config=config, topics=topics, items=deduplicated)
