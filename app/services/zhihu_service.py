from __future__ import annotations

import json
import os
import re
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

import httpx

from ..config.loader import get_settings
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


def extract_zhihu_title_from_html(html: str) -> str | None:
    """从知乎 HTML 中尽量稳健地提取问题标题；这样页面标签结构变化时导入单题也不容易误判失败。"""

    patterns = [
        r"<h1[^>]*>(.*?)</h1>",
        r'<meta\s+property="og:title"\s+content="([^"]+)"',
        r'<meta\s+name="title"\s+content="([^"]+)"',
        r"<title[^>]*>(.*?)</title>",
        r'"title"\s*:\s*"([^"]+)"',
        r'"name"\s*:\s*"([^"]+)"',
    ]
    for pattern in patterns:
        match = re.search(pattern, html, re.I | re.S)
        if not match:
            continue
        title = clean_text(match.group(1)).replace(" - 知乎", "").strip()
        if title and not re.fullmatch(r"知乎问题\s*\d+", title):
            return title
    return None


def extract_zhihu_excerpt_from_html(html: str) -> str:
    """从知乎 HTML 中提取问题摘要；这样导入单题时即使没有搜索接口也能补齐部分展示信息。"""

    patterns = [
        r'<meta\s+name="description"\s+content="([^"]+)"',
        r'<meta\s+property="og:description"\s+content="([^"]+)"',
    ]
    for pattern in patterns:
        match = re.search(pattern, html, re.I | re.S)
        if match:
            return clean_text(match.group(1))
    return ""


def extract_zhihu_detail_from_html(html: str) -> str:
    """从知乎 HTML 中提取问题描述正文；这样链接导入即使没有命中 API 详情字段也能尽量补出提问补充。"""

    patterns = [
        r'"detail"\s*:\s*"([^"]+)"',
        r'"questionDetail"\s*:\s*"([^"]+)"',
        r'<meta\s+property="og:description"\s+content="([^"]+)"',
    ]
    for pattern in patterns:
        match = re.search(pattern, html, re.I | re.S)
        if match:
            detail = clean_text(match.group(1))
            if detail:
                return detail
    return ""


def extract_zhihu_topics_from_html(html: str) -> list[str]:
    """从知乎 HTML 中提取问题话题标签；这样页面可见标签能在结构化接口缺失时继续用于前端展示。"""

    candidates = re.findall(r'"topics"\s*:\s*\[(.*?)\]', html, re.I | re.S)
    for candidate in candidates:
        names = [clean_text(value) for value in re.findall(r'"name"\s*:\s*"([^"]+)"', candidate, re.I | re.S)]
        normalized = [name for name in names if name]
        if normalized:
            return normalized
    return []


def extract_zhihu_question_snapshot_from_html(html: str) -> dict[str, Any]:
    """从知乎 HTML 汇总问题快照字段；这样页面解析可以一次产出标题、摘要、描述、时间和标签的补充信息。"""

    date_match = re.search(r'"updated_time":\s*(\d{10})', html, re.I) or re.search(
        r'<meta\s+itemprop="dateModified"\s+content="([^"]+)"', html, re.I
    )
    answer_match = re.search(r'"answer_count":\s*(\d+)', html, re.I) or re.search(
        r'"answerCount":\s*(\d+)', html, re.I
    )
    return {
        "title": extract_zhihu_title_from_html(html),
        "excerpt": extract_zhihu_excerpt_from_html(html),
        "detail": extract_zhihu_detail_from_html(html),
        "answer_count": int(answer_match.group(1)) if answer_match else None,
        "updated_time": to_iso_time(date_match.group(1)) if date_match else None,
        "topics": extract_zhihu_topics_from_html(html),
    }


def get_zhihu_question_web_url(question_id: str) -> str:
    """生成知乎问题网页链接；这样内部只存问题 id 时也能提供前端可打开的原始地址。"""

    return f"https://www.zhihu.com/question/{question_id}"


def extract_zhihu_question_id(url: str) -> str | None:
    """从知乎问题链接中提取问题 id；这样前端粘贴不同格式的知乎 URL 时都能归一成同一个解析入口。"""

    normalized_url = str(url).strip()
    match = re.search(r"zhihu\.com/question/(\d+)", normalized_url, re.I)
    return match.group(1) if match else None


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
        answerStyle=topic.answer_style,
        systemPrompt=topic.system_prompt,
    )


def get_topic_retrieval_keywords(topic: Topic) -> list[str]:
    """返回主题本次检索词集合；这样 AI 扩词结果和静态兜底词都能走同一条知乎检索链路。"""

    raw_keywords = topic.expanded_hints or build_keyword_hints(topic)
    normalized = [str(keyword).strip() for keyword in raw_keywords if str(keyword).strip()]
    return unique_by(normalized, lambda item: item.lower())


def question_matches_keyword(question: QuestionItem, keyword_hints: list[str]) -> bool:
    """判断问题是否命中主题关键词；这样搜索接口混入的非相关内容可以在本地被过滤。"""

    haystack = clean_text(" ".join([question.title, question.excerpt, question.detail])).lower()
    return bool(haystack) and any(str(hint).strip().lower() in haystack for hint in keyword_hints if str(hint).strip())


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


def build_zhihu_headers(
    user_agent: str,
    *,
    accept: str,
    referer: str,
    include_signature: bool,
    include_requested_with: bool = False,
) -> dict[str, str]:
    """构建知乎请求头；这样搜索、详情接口和网页抓取可以共享同一套凭据与浏览器伪装规则。"""

    cookie = load_zhihu_cookie()
    signature = get_zhihu_signature_header()
    headers = {
        "User-Agent": user_agent,
        "Accept": accept,
        "Referer": referer,
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    if cookie:
        headers["Cookie"] = cookie
    if include_requested_with:
        headers["X-Requested-With"] = os.getenv("ZHIHU_X_REQUESTED_WITH", "fetch")
    if include_signature:
        if os.getenv("ZHIHU_X_ZSE_93", "").strip():
            headers["x-zse-93"] = os.getenv("ZHIHU_X_ZSE_93", "").strip()
        if signature:
            headers["x-zse-96"] = signature
    return headers


def map_zhihu_question_detail_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """把知乎问题详情响应映射为内部字段；这样链接导入能优先使用结构化数据而不是依赖脆弱的页面标签。"""

    topics = [
        clean_text(topic.get("name"))
        for topic in payload.get("topics", [])
        if isinstance(topic, dict) and clean_text(topic.get("name"))
    ]
    return {
        "title": clean_text(payload.get("title") or ""),
        "excerpt": clean_text(payload.get("excerpt") or ""),
        "detail": clean_text(payload.get("detail") or ""),
        "answer_count": int(payload.get("answer_count") or 0),
        "updated_time": to_iso_time(payload.get("updated_time") or payload.get("created")),
        "topics": topics,
    }


async def fetch_question_detail_payload(question_id: str, user_agent: str) -> dict[str, Any] | None:
    """请求知乎结构化问题详情；这样导入问题时可以稳定拿到真实标题、摘要、描述和标签。"""

    cookie = load_zhihu_cookie()
    signature = get_zhihu_signature_header()
    if not cookie or not signature:
        return None

    detail_url = f"https://api.zhihu.com/questions/{question_id}"
    params = {"include": "answer_count,excerpt,detail,topics"}
    headers = build_zhihu_headers(
        user_agent,
        accept="*/*",
        referer=get_zhihu_question_web_url(question_id),
        include_signature=True,
        include_requested_with=True,
    )
    async with httpx.AsyncClient(
        timeout=get_settings().http.client_timeout_seconds, follow_redirects=True
    ) as client:
        response = await client.get(detail_url, params=params, headers=headers)
    if response.status_code >= 400:
        return None

    try:
        payload = parse_json_response(response, "Zhihu question detail API")
    except ValueError:
        return None
    return payload if isinstance(payload, dict) else None


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

    updates: dict[str, Any] = {}

    payload = await fetch_question_detail_payload(item.id, user_agent)
    if payload:
        detail_snapshot = map_zhihu_question_detail_payload(payload)
        if detail_snapshot.get("title"):
            updates["title"] = detail_snapshot["title"]
        if detail_snapshot.get("excerpt"):
            updates["excerpt"] = detail_snapshot["excerpt"]
        if detail_snapshot.get("detail"):
            updates["detail"] = detail_snapshot["detail"]
        if detail_snapshot.get("updated_time"):
            updates["updated_time"] = detail_snapshot["updated_time"]
        if detail_snapshot.get("answer_count") is not None:
            updates["answer_count"] = detail_snapshot["answer_count"]
        if detail_snapshot.get("topics"):
            updates["topic"] = " / ".join(detail_snapshot["topics"])

    headers = build_zhihu_headers(
        user_agent,
        accept="text/html,application/xhtml+xml",
        referer="https://www.zhihu.com/",
        include_signature=False,
    )
    async with httpx.AsyncClient(
        timeout=get_settings().http.client_timeout_seconds, follow_redirects=True
    ) as client:
        response = await client.get(item.url, headers=headers)
    if response.status_code < 400:
        html_snapshot = extract_zhihu_question_snapshot_from_html(response.text)
        if html_snapshot.get("title") and not updates.get("title"):
            updates["title"] = html_snapshot["title"]
        if html_snapshot.get("excerpt") and not updates.get("excerpt"):
            updates["excerpt"] = html_snapshot["excerpt"]
        if html_snapshot.get("detail") and not updates.get("detail"):
            updates["detail"] = html_snapshot["detail"]
        if html_snapshot.get("updated_time") and not updates.get("updated_time"):
            updates["updated_time"] = html_snapshot["updated_time"]
        if html_snapshot.get("answer_count") is not None and "answer_count" not in updates:
            updates["answer_count"] = html_snapshot["answer_count"]
        if html_snapshot.get("topics") and not updates.get("topic"):
            updates["topic"] = " / ".join(html_snapshot["topics"])

    return item.model_copy(update=updates) if updates else item


async def fetch_zhihu_question_by_url(url: str, user_agent: str, topic_name: str = "链接导入") -> QuestionItem:
    """通过知乎问题链接解析单个题目；这样用户可以跳过检索，直接把指定问题放进回答工作流。"""

    question_id = extract_zhihu_question_id(url)
    if not question_id:
        raise ValueError("当前仅支持知乎问题链接，格式示例：https://www.zhihu.com/question/123456789")

    normalized_url = get_zhihu_question_web_url(question_id)
    item = QuestionItem(
        id=question_id,
        url=normalized_url,
        title=f"知乎问题 {question_id}",
        topic=topic_name,
        answerCount=0,
        excerpt="",
        detail="",
    )
    return await fetch_question_details(item, user_agent)


def calculate_keyword_fetch_limit(total_limit: int, keyword_count: int) -> int:
    """计算每个检索词的抓取配额；这样扩展词都有机会贡献结果而不会被第一条检索词独占配额。"""

    keyword_count = max(1, keyword_count)
    total_limit = max(1, total_limit)
    per_keyword = max(1, total_limit // keyword_count)
    return min(20, max(5, per_keyword))


async def search_zhihu_for_keyword(topic: Topic, keyword: str, user_agent: str, limit: int = 12) -> list[QuestionItem]:
    """按单个关键词请求知乎搜索接口；这样批量检索时每个关键词都能复用相同的请求和解析逻辑。"""

    cookie = load_zhihu_cookie()
    signature = get_zhihu_signature_header()
    ensure_zhihu_request_credentials(cookie, signature)
    url_base = os.getenv("ZHIHU_API_URL", "https://api.zhihu.com/search_v3").strip()
    referer_query = httpx.QueryParams({"type": "content", "q": keyword})
    referer = os.getenv("ZHIHU_REFERER", f"https://www.zhihu.com/search?{referer_query}").strip()
    params = {
        "advert_count": "0",
        "gk_version": "gz-gaokao",
        "t": "general",
        "q": keyword,
        "correction": "1",
        "offset": "0",
        "limit": str(max(1, min(20, limit))),
        "filter_fields": "",
        "lc_idx": "0",
        "show_all_topics": "0",
        "search_source": "Normal",
    }
    headers = build_zhihu_headers(
        user_agent,
        accept="*/*",
        referer=referer,
        include_signature=True,
        include_requested_with=True,
    )

    async with httpx.AsyncClient(
        timeout=get_settings().http.client_timeout_seconds, follow_redirects=True
    ) as client:
        response = await client.get(url_base, params=params, headers=headers)

    if response.status_code >= 400:
        preview = re.sub(r"\s+", " ", response.text[:300]).strip()
        raise ValueError(
            f"Zhihu request failed: {response.status_code} {response.reason_phrase}; "
            f"url={response.url}; body={preview or 'empty'}"
        )

    payload = ZhihuSearchResponse.model_validate(parse_json_response(response, "Zhihu API"))
    keyword_hints = unique_by([topic.name, *topic.keywords, *get_topic_retrieval_keywords(topic), keyword], lambda item: item.lower())
    items = [
        item for item in
        (map_search_item(row, topic.name) for row in payload.data)
        if item and question_matches_keyword(item, keyword_hints)
    ]
    return unique_by(items, lambda item: item.id)


async def fetch_zhihu_results_for_topic(topic: Topic, user_agent: str, limit: int = 10) -> list[QuestionItem]:
    """按主题批量检索知乎问题；这样一个主题可以先扩展多个检索词，再聚合去重出候选问题。"""

    retrieval_keywords = get_topic_retrieval_keywords(topic)
    per_keyword_limit = calculate_keyword_fetch_limit(limit, len(retrieval_keywords))
    aggregated: list[QuestionItem] = []
    for keyword in retrieval_keywords:
        aggregated.extend(await search_zhihu_for_keyword(topic, keyword, user_agent, limit=per_keyword_limit))

    deduplicated = unique_by(aggregated, lambda item: item.id)[: max(limit, 1)]
    detailed: list[QuestionItem] = []
    for item in deduplicated:
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
        all_items.extend(await fetch_zhihu_results_for_topic(topic, config.user_agent, config.max_push_count))

    deduplicated = unique_by(all_items, lambda item: f"{item.topic}:{item.id}")[: config.max_push_count]
    if not deduplicated:
        raise ValueError("No matching questions fetched")

    return WorkflowResult(config=config, topics=topics, items=deduplicated)
