from __future__ import annotations

import json
import os
import re
from datetime import datetime
from functools import lru_cache
from html import unescape
from pathlib import Path
from typing import Any
from urllib.parse import quote

from bs4 import BeautifulSoup

from app.platform.config.loader import get_settings
from app.platform.config.runtime import COOKIE_PATH_DEFAULT, load_env_file
from app.plugins.sources.fetchers.playwright_fetcher import PlaywrightFetcher
from app.shared.content import QuestionItem, Topic

TOPIC_HINTS_PATH = Path(__file__).resolve().parent.parent / "config" / "defaults" / "topic_hints.json"


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


def is_zhihu_block_text(value: str) -> bool:
    """识别知乎登录/安全验证占位文本；这样风控页不会被误当成真实问题内容。"""

    text = clean_text(value)
    blocked_markers = [
        "安全验证",
        "请您登录后查看更多专业优质内容",
        "请登录后查看更多",
        "知乎 - 有问题，就会有答案",
    ]
    return not text or any(marker in text for marker in blocked_markers)


def is_zhihu_challenge_html(html: str) -> bool:
    """识别知乎风控挑战页；这样 URL 导入可以触发浏览器兜底或返回明确错误。"""

    markers = ("zse-ck", "zh-zse-ck", "请求存在异常", "code\":40362", "请您登录后查看更多专业优质内容")
    return any(marker in html for marker in markers)


def is_placeholder_question(item: QuestionItem) -> bool:
    """判断问题对象是否仍只是 URL 兜底值；这样导入失败不会在前端伪装成成功。"""

    return (
        re.fullmatch(r"知乎问题\s*\d+", item.title.strip()) is not None
        and not item.excerpt.strip()
        and not item.detail.strip()
        and item.answer_count == 0
        and item.updated_time is None
    )


def _first_present(payload: dict[str, Any], *keys: str) -> Any:
    """按多个候选 key 读取第一个非空字段；这样可兼容知乎 API 与前端状态里的不同命名。"""

    for key in keys:
        value = payload.get(key)
        if value not in (None, ""):
            return value
    return None


def _parse_jsonish_text(value: str) -> Any:
    """解析 HTML 中的 JSON 或 JS 字符串片段；这样初始状态和转义字段都能转成结构化对象。"""

    text = unescape(str(value or "")).strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    try:
        return json.loads(f'"{text}"')
    except json.JSONDecodeError:
        return None


def _normalize_html_text(value: Any) -> str:
    """把普通字符串、HTML 字符串或 JSON 转义字符串归一成纯文本。"""

    if value in (None, ""):
        return ""
    parsed = _parse_jsonish_text(str(value))
    if isinstance(parsed, str):
        return clean_text(parsed)
    return clean_text(value)


def _normalize_topics(value: Any) -> list[str]:
    """把知乎不同来源的话题字段归一成名称列表。"""

    if not isinstance(value, list):
        return []
    topics: list[str] = []
    for topic in value:
        if isinstance(topic, dict):
            name = clean_text(topic.get("name") or topic.get("Name") or topic.get("title"))
        else:
            name = clean_text(topic)
        if name:
            topics.append(name)
    return unique_by(topics, lambda item: item)


def _snapshot_from_question_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """从知乎问题结构里抽取内部快照；这样 API payload 和页面 initialState 可以共享映射。"""

    topics = _normalize_topics(
        _first_present(payload, "topics", "topicList", "TopicList", "boundTopicIds")
    )
    answer_count = _first_present(payload, "answer_count", "answerCount", "answer_num", "answerNum")
    try:
        normalized_answer_count = int(answer_count) if answer_count not in (None, "") else None
    except (TypeError, ValueError):
        normalized_answer_count = None
    return {
        "title": _normalize_html_text(_first_present(payload, "title", "name", "questionTitle", "Title")),
        "excerpt": _normalize_html_text(
            _first_present(payload, "excerpt", "questionExcerpt", "description", "summary")
        ),
        "detail": _normalize_html_text(
            _first_present(payload, "detail", "questionDetail", "content", "description")
        ),
        "answer_count": normalized_answer_count,
        "updated_time": to_iso_time(
            _first_present(payload, "updated_time", "updatedTime", "updated", "created", "created_time", "createdTime")
        ),
        "topics": topics,
    }


def _merge_snapshot(base: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    """合并问题快照；只用非空新字段填补空字段，避免弱来源覆盖强来源。"""

    merged = dict(base)
    for key in ("title", "excerpt", "detail", "updated_time"):
        if not merged.get(key) and incoming.get(key):
            merged[key] = incoming[key]
    if merged.get("answer_count") is None and incoming.get("answer_count") is not None:
        merged["answer_count"] = incoming["answer_count"]
    if not merged.get("topics") and incoming.get("topics"):
        merged["topics"] = incoming["topics"]
    return merged


def _extract_balanced_object(text: str, start_index: int) -> str | None:
    """从 JS 片段中截取一个平衡的大括号对象；用于解析 window.__INITIAL_STATE__。"""

    depth = 0
    in_string = False
    escaped = False
    for index in range(start_index, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start_index:index + 1]
    return None


def _extract_embedded_json_objects(html: str) -> list[dict[str, Any]]:
    """提取知乎页面中常见的内嵌 JSON 对象；这样 URL 导入不只依赖 meta 标签。"""

    objects: list[dict[str, Any]] = []
    script_patterns = [
        r'<script[^>]+id=["\']js-initialData["\'][^>]*>(.*?)</script>',
        r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
    ]
    for pattern in script_patterns:
        for match in re.finditer(pattern, html, re.I | re.S):
            parsed = _parse_jsonish_text(match.group(1))
            if isinstance(parsed, dict):
                objects.append(parsed)

    state_match = re.search(r"window\.__INITIAL_STATE__\s*=", html)
    if state_match:
        start = html.find("{", state_match.end())
        if start >= 0:
            raw_object = _extract_balanced_object(html, start)
            parsed = _parse_jsonish_text(raw_object or "")
            if isinstance(parsed, dict):
                objects.append(parsed)
    return objects


def _iter_dicts(value: Any):
    """深度遍历嵌套 JSON 中的 dict；用于从知乎 initialState 中定位 question 实体。"""

    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _iter_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from _iter_dicts(child)


def extract_zhihu_question_snapshot_from_state(state: dict[str, Any], question_id: str | None = None) -> dict[str, Any]:
    """从知乎前端状态中提取问题快照；这样页面结构变化时仍可从 entities.questions 获取字段。"""

    snapshots: list[dict[str, Any]] = []
    for node in _iter_dicts(state):
        questions = node.get("questions")
        if isinstance(questions, dict):
            if question_id and isinstance(questions.get(question_id), dict):
                snapshots.append(_snapshot_from_question_payload(questions[question_id]))
            else:
                snapshots.extend(
                    _snapshot_from_question_payload(question)
                    for question in questions.values()
                    if isinstance(question, dict)
                )
        node_id = str(_first_present(node, "id", "questionId", "qid") or "")
        if (
            (question_id and node_id == question_id)
            or {"title", "answerCount"}.issubset(node.keys())
            or {"title", "answer_count"}.issubset(node.keys())
        ):
            snapshots.append(_snapshot_from_question_payload(node))

    merged = {
        "title": None,
        "excerpt": "",
        "detail": "",
        "answer_count": None,
        "updated_time": None,
        "topics": [],
    }
    for snapshot in snapshots:
        merged = _merge_snapshot(merged, snapshot)
        if merged.get("title") and (merged.get("excerpt") or merged.get("detail")):
            break
    return merged


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
        if title and not re.fullmatch(r"知乎问题\s*\d+", title) and not is_zhihu_block_text(title):
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
            excerpt = clean_text(match.group(1))
            return "" if is_zhihu_block_text(excerpt) else excerpt
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
            if detail and not is_zhihu_block_text(detail):
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


def extract_zhihu_question_snapshot_from_html(html: str, question_id: str | None = None) -> dict[str, Any]:
    """从知乎 HTML 汇总问题快照字段；这样页面解析可以一次产出标题、摘要、描述、时间和标签的补充信息。"""

    state_snapshot = {
        "title": None,
        "excerpt": "",
        "detail": "",
        "answer_count": None,
        "updated_time": None,
        "topics": [],
    }
    for state in _extract_embedded_json_objects(html):
        state_snapshot = _merge_snapshot(
            state_snapshot,
            extract_zhihu_question_snapshot_from_state(state, question_id),
        )

    date_match = re.search(r'"updated_time":\s*(\d{10})', html, re.I) or re.search(
        r'<meta\s+itemprop="dateModified"\s+content="([^"]+)"', html, re.I
    )
    answer_match = re.search(r'"answer_count":\s*(\d+)', html, re.I) or re.search(
        r'"answerCount":\s*(\d+)', html, re.I
    )
    regex_snapshot = {
        "title": extract_zhihu_title_from_html(html),
        "excerpt": extract_zhihu_excerpt_from_html(html),
        "detail": extract_zhihu_detail_from_html(html),
        "answer_count": int(answer_match.group(1)) if answer_match else None,
        "updated_time": to_iso_time(date_match.group(1)) if date_match else None,
        "topics": extract_zhihu_topics_from_html(html),
    }
    return _merge_snapshot(state_snapshot, regex_snapshot)


def extract_zhihu_search_items_from_html(
    html: str, topic_name: str, limit: int = 20
) -> list[QuestionItem]:
    """从知乎搜索页渲染后的 HTML 提取问题链接和标题，不依赖知乎内部搜索 API。"""

    soup = BeautifulSoup(html, "html.parser")
    items: list[QuestionItem] = []
    seen: set[str] = set()
    for anchor in soup.select('a[href*="/question/"]'):
        href = str(anchor.get("href") or "").strip()
        question_id = extract_zhihu_question_id(href)
        if not question_id or question_id in seen:
            continue

        title = clean_text(anchor.get_text(" ", strip=True))
        if not title or is_zhihu_block_text(title):
            continue

        container = anchor.find_parent(["article", "div", "li"])
        excerpt = ""
        if container is not None:
            container_text = clean_text(container.get_text(" ", strip=True))
            if container_text.startswith(title):
                excerpt = container_text[len(title):].strip()[:500]

        seen.add(question_id)
        items.append(
            QuestionItem(
                id=question_id,
                platform="zhihu",
                title=title,
                url=get_zhihu_question_web_url(question_id),
                answerCount=0,
                excerpt=excerpt,
                detail="",
                topic=topic_name,
            )
        )
        if len(items) >= max(1, min(20, limit)):
            break
    return items


def get_zhihu_question_web_url(question_id: str) -> str:
    """生成知乎问题网页链接；这样内部只存问题 id 时也能提供前端可打开的原始地址。"""

    return f"https://www.zhihu.com/question/{question_id}"


def extract_zhihu_question_id(url: str) -> str | None:
    """从知乎问题链接中提取问题 id；这样前端粘贴不同格式的知乎 URL 时都能归一成同一个解析入口。"""

    normalized_url = str(url).strip()
    match = re.search(
        r"(?:https?://(?:www\.)?zhihu\.com)?/question/(\d+)",
        normalized_url,
        re.I,
    )
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


def map_zhihu_question_detail_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """兼容旧调用方的字段映射；当前详情采集改为直接解析网页 HTML。"""

    return _snapshot_from_question_payload(payload)




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
    resolved = await fetch_question_details(item, user_agent, render_fallback=True)
    if is_placeholder_question(resolved):
        raise ValueError(
            "未能解析知乎问题内容：知乎返回了安全验证/异常访问页，或当前 Cookie 已失效。"
            "请在浏览器确认该链接可打开，并更新 ZHIHU_COOKIE_FILE 后重试。"
        )
    return resolved


def calculate_keyword_fetch_limit(total_limit: int, keyword_count: int) -> int:
    """计算每个检索词的抓取配额；这样扩展词都有机会贡献结果而不会被第一条检索词独占配额。"""

    keyword_count = max(1, keyword_count)
    total_limit = max(1, total_limit)
    per_keyword = max(1, total_limit // keyword_count)
    return min(20, max(5, per_keyword))


async def fetch_question_details(
    item: QuestionItem,
    user_agent: str,
    *,
    render_fallback: bool = False,
) -> QuestionItem:
    """通过 Playwright 渲染知乎问题页补齐详情，不调用知乎 JSON API。"""

    html = await PlaywrightFetcher(
        cookie_string=load_zhihu_cookie(),
        cookie_domain=".zhihu.com",
    ).fetch(
        item.url,
        {
            "User-Agent": user_agent,
            "Accept": "text/html,application/xhtml+xml",
            "Referer": "https://www.zhihu.com/",
        },
    )
    snapshot = extract_zhihu_question_snapshot_from_html(html, item.id)
    updates: dict[str, Any] = {}
    for key in ("title", "excerpt", "detail", "updated_time", "answer_count"):
        value = snapshot.get(key)
        if value not in (None, ""):
            updates[key] = value
    if snapshot.get("topics"):
        updates["topic"] = " / ".join(snapshot["topics"])

    return item.model_copy(update=updates) if updates else item


async def search_zhihu_for_keyword(
    topic: Topic, keyword: str, user_agent: str, limit: int = 12
) -> list[QuestionItem]:
    """通过 Playwright 渲染知乎搜索页并解析问题链接，不调用知乎 JSON API。"""

    search_url = f"https://www.zhihu.com/search?type=content&q={quote(keyword, safe='')}"
    html = await PlaywrightFetcher(
        cookie_string=load_zhihu_cookie(),
        cookie_domain=".zhihu.com",
    ).fetch(
        search_url,
        {
            "User-Agent": user_agent,
            "Accept": "text/html,application/xhtml+xml",
            "Referer": "https://www.zhihu.com/",
        },
    )
    items = extract_zhihu_search_items_from_html(html, topic.name, limit)
    if not items:
        page_text = clean_text(BeautifulSoup(html, "html.parser").get_text(" ", strip=True))
        if is_zhihu_challenge_html(html) or is_zhihu_block_text(page_text):
            raise ValueError(
                "知乎搜索页返回了安全验证或登录限制页面，请更新 ZHIHU_COOKIE_FILE 后重试。"
            )
        raise ValueError("知乎搜索页未解析到问题结果，可能是页面结构已变化。")

    keyword_hints = unique_by(
        [topic.name, *topic.keywords, *get_topic_retrieval_keywords(topic), keyword],
        lambda item: item.lower(),
    )
    filtered = [item for item in items if question_matches_keyword(item, keyword_hints)]
    return unique_by(filtered or items, lambda item: item.id)



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
