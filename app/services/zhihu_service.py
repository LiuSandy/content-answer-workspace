from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from ..core.config import COOKIE_PATH_DEFAULT, get_default_topics, get_workflow_config, load_env_file
from ..models import QuestionItem, Topic, WorkflowResult, ZhihuSearchResponse


def unique_by(items: list[Any], key_fn) -> list[Any]:
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
    return f"https://www.zhihu.com/question/{question_id}"


def build_keyword_hints(topic: Topic) -> list[str]:
    raw_tokens = [
        token.strip().lower()
        for source in [topic.name, *topic.keywords]
        for token in re.split(r"[,，/\s、]+", str(source))
        if token.strip()
    ]
    topic_id = topic.id.lower()
    topic_name = topic.name.lower()

    if "algo" in topic_id or "算法" in topic_name or "数据结构" in topic_name:
        topic_specific = [
            "数据结构", "结构", "算法", "二叉树", "链表", "栈", "队列", "哈希", "哈希表",
            "堆", "图", "并查集", "动态规划", "dp", "回溯", "贪心", "递归", "排序",
            "查找", "时间复杂度", "空间复杂度", "复杂度", "leetcode", "刷题", "面试算法",
        ]
    elif "personal-site" in topic_id or "个人站点" in topic_name or "建站" in topic_name:
        topic_specific = [
            "个人网站", "个人站点", "独立站", "独立博客", "博客", "建站", "个人主页", "主页",
            "网站设计", "网页设计", "作品集网站", "portfolio", "导航页", "展示页", "站点推荐",
            "网站推荐", "站点展示", "好看的网站", "好看的个人网站", "好看的个人站点", "网站审美",
            "网站案例", "个人品牌网站", "开发者主页", "十年前做个人网站", "大家的个人网站",
            "有多少人有自己的个人网站",
        ]
    elif "podcast" in topic_id or "播客" in topic_name:
        topic_specific = [
            "播客", "podcast", "音频节目", "播客推荐", "播客创作", "做播客", "独立播客", "内容创作",
        ]
    else:
        topic_specific = []

    return unique_by(raw_tokens + topic_specific, lambda item: item)


def get_topic_preview(topic: Topic) -> Topic:
    return Topic(
        id=topic.id,
        name=topic.name,
        keywords=topic.keywords,
        expandedHints=build_keyword_hints(topic),
    )


def question_matches_keyword(question: QuestionItem, keyword_hints: list[str]) -> bool:
    haystack = clean_text(" ".join([question.title, question.excerpt, question.detail])).lower()
    return bool(haystack) and any(hint in haystack for hint in keyword_hints)


def to_iso_time(value: Any) -> str | None:
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
    try:
        return file_path.read_text("utf-8")
    except FileNotFoundError:
        return None


def load_zhihu_cookie() -> str | None:
    configured = os.getenv("ZHIHU_COOKIE_FILE", "").strip()
    cookie_path = Path(configured).resolve() if configured else COOKIE_PATH_DEFAULT
    content = read_optional_file(cookie_path)
    return content.strip() if content else None


def map_search_item(raw: dict[str, Any], topic_name: str) -> QuestionItem | None:
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
    cookie = load_zhihu_cookie()
    query = httpx.QueryParams({"q": topic.name}).get("q")
    url_base = os.getenv("ZHIHU_API_URL", "https://www.zhihu.com/api/v4/search_v3").strip()
    referer = os.getenv("ZHIHU_REFERER", f"https://www.zhihu.com/search?type=content&q={query}").strip()
    params = {
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
    if os.getenv("ZHIHU_X_ZSE_96", "").strip():
        headers["x-zse-96"] = os.getenv("ZHIHU_X_ZSE_96", "").strip()
    if cookie:
        headers["Cookie"] = cookie

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        response = await client.get(url_base, params=params, headers=headers)

    if response.status_code >= 400:
        raise ValueError(f"Zhihu request failed: {response.status_code} {response.reason_phrase}")

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
