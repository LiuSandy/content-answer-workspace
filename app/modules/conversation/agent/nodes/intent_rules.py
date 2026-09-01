"""意图规则层：确定性关键词/正则判定，不依赖 LLM。

在调用 LLM 之前先用规则快速判定，命中即返回，减少 LLM 调用、保证可复现。
规则未命中时返回 None，交由 LLM 层补充判断。

优先级（后写的覆盖先写的）：
  1. 寒暄 → chat + off
  2. 严格知识模式 → chat + strict
  3. 平台采集 → collect + platform + query
  4. 单篇创作 → task_plan
  5. 多阶段创作 → multi_agent
  6. URL 解析 → parse_url
"""
from __future__ import annotations

import re

from typing import Any

# ── 寒暄/闲聊 ─────────────────────────────────────────────────────────────
_CHITCHAT_PHRASES = {
    "你好", "您好", "嗨", "哈喽", "在吗", "谢谢", "谢啦", "多谢", "感谢",
    "好的", "嗯", "嗯嗯", "行", "可以", "好的好的", "没问题", "拜拜", "再见",
    "hi", "hello", "hey", "thanks", "thank you", "ok", "okay", "bye",
    "早上好", "中午好", "晚上好", "辛苦了",
}

# ── 严格知识模式触发词 ────────────────────────────────────────────────────
_STRICT_MARKERS = (
    "只能根据我上传", "只许用私有", "只用我上传", "不要用通用知识",
    "仅依据我的资料", "只根据我的文件", "只能使用我上传", "只用我的文件",
    "strict", "only use my", "only use uploaded",
)

# ── 平台名与采集动作 ──────────────────────────────────────────────────────
_PLATFORM_ALIASES = {
    "zhihu": ("知乎", "zhihu"),
    "xiaohongshu": ("小红书", "xiaohongshu", "xhs"),
    "bilibili": ("bilibili", "哔哩哔哩", "B站", "b站"),
    "youtube": ("youtube", "油管", "youtu"),
    "twitter": ("twitter", "推特", "x 平台", "x平台"),
    "reddit": ("reddit", "红迪"),
    "github": ("github", "git hub"),
    "rss": ("rss",),
    "v2ex": ("v2ex",),
}

# 采集动作：表达"搜索/检索/采集/找帖子"
_COLLECT_VERBS = (
    "搜一下", "搜搜", "搜索", "检索", "采集", "帮我找", "找找", "看看有没有",
    "查一下", "查询", "爬取", "搜集", "看看", "找一些", "找点", "帮我搜",
    "有哪些", "有什么", "推荐一些", "整理一下", "热门讨论", "热门帖子",
    "有没有", "有没有好用的", "找", "search", "find", "collect", "fetch",
)

# 帖子类目标名词（与动词配合：搜…帖子/笔记/回答/话题）
_COLLECT_NOUNS = (
    "帖子", "笔记", "回答", "话题", "讨论", "内容", "视频", "文章",
    "作品", "帖子", "动态", "问题", "news", "post", "posts", "video",
)

# ── 创作触发词 ─────────────────────────────────────────────────────────────
# 单篇创作：写/创作/产出一篇(个/份)作品
_TASK_PLAN_MARKERS = (
    "写一篇", "写个", "创作一篇", "创作一个", "产出一篇", "产出一个",
    "生成一篇", "写一段", "写一个回答", "写一篇文章", "写一份",
    "出一篇", "写写", "帮我写", "帮忙写", "write an", "write a",
)

# 多阶段创作：调研+写作+评审等复合
_MULTI_AGENT_MARKERS = (
    "调研并", "分析报告", "行业报告", "深度报告", "研究报告", "整理一份报告",
    "策划并产出", "选题矩阵", "专栏系列", "调研一下并", "做一个完整",
    "出一份完整", "输出一份完整", "research and", "analyze and",
)

_URL_PATTERN = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)

_CHINESE_DIGITS = {
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}
_COUNT_PATTERN = re.compile(
    r"(?:(?:不要|别|不用)\s*太多\s*[，,、;；]?\s*)?"
    r"(?:(?:只要|最多|至多|不超过|返回|给我|来|要|找)\s*)?"
    r"(?P<count>\d{1,3}|[一二两三四五六七八九十]{1,3})\s*"
    r"(?:个|条|篇)(?:问题|回答|帖子|结果|内容|视频|笔记)?"
    r"(?:就行|即可|左右|以内)?"
)
_HOT_MARKERS = ("回答最多", "讨论最多", "最热门", "热门", "热榜", "高赞", "最热")
_LATEST_MARKERS = ("最近发布", "最新发布", "最新", "近期", "刚发布")


def extract_urls(message: str) -> list[str]:
    """提取消息中的 URL。"""
    return _URL_PATTERN.findall(message)


def detect_knowledge_mode(message: str, default: str = "normal") -> str:
    """规则判定知识模式；未命中返回 default。"""
    lowered = message.lower()
    if any(m in lowered for m in _STRICT_MARKERS):
        return "strict"
    return default


def _detect_platform(message: str) -> str | None:
    """检测消息提到的平台名。"""
    lowered = message.lower()
    for platform, aliases in _PLATFORM_ALIASES.items():
        for alias in aliases:
            if alias in message or alias in lowered:
                return platform
    return None


def _parse_requested_count(value: str) -> int | None:
    if value.isdigit():
        return int(value)
    if value == "十":
        return 10
    if "十" in value:
        tens_text, ones_text = value.split("十", 1)
        tens = _CHINESE_DIGITS.get(tens_text, 1) if tens_text else 1
        ones = _CHINESE_DIGITS.get(ones_text, 0) if ones_text else 0
        return tens * 10 + ones
    if len(value) == 1:
        return _CHINESE_DIGITS.get(value)
    return None


def _extract_search_constraints(message: str) -> tuple[int, str, bool, bool]:
    """Extract result count and ordering without mixing them into the query."""

    match = _COUNT_PATTERN.search(message)
    requested = _parse_requested_count(match.group("count")) if match else None
    limit = max(1, min(20, requested or 10))
    has_hot_sort = any(marker in message for marker in _HOT_MARKERS)
    has_latest_sort = any(marker in message for marker in _LATEST_MARKERS)
    if has_hot_sort:
        sort = "hot"
    elif has_latest_sort:
        sort = "latest"
    else:
        sort = "relevance"
    return limit, sort, match is not None, has_hot_sort or has_latest_sort


def _extract_query(message: str, platform: str | None, sort: str = "relevance") -> str:
    """从采集消息中粗提取搜索词：去掉平台名与常见动作/目标词后取剩余。

    规则层只做粗提取，精修由 LLM 层完成。失败返回空串。
    """
    message = _COUNT_PATTERN.sub(" ", message)
    message = re.sub(r"(?:不要|别|不用)\s*太多", " ", message)
    if platform:
        for alias in _PLATFORM_ALIASES.get(platform, ()):
            message = re.sub(re.escape(alias), " ", message, flags=re.IGNORECASE)
    for prefix in ("请您", "帮我", "帮忙", "麻烦", "请"):
        message = message.replace(prefix, " ")
    for verb in sorted(_COLLECT_VERBS, key=len, reverse=True):
        message = message.replace(verb, " ")
    for noun in sorted(_COLLECT_NOUNS, key=len, reverse=True):
        message = message.replace(noun, " ")
    for marker in (*_HOT_MARKERS, *_LATEST_MARKERS):
        message = message.replace(marker, " ")
    message = re.sub(r"[，,。？?！!；;：:、]", " ", message)
    for filler in (
        "请您", "帮我", "帮忙", "麻烦", "请", "一下", "重新", "关于",
        "只要", "需要", "然后", "就行", "即可",
    ):
        message = message.replace(filler, " ")
    message = re.sub(r"^\s*(?:在|上|里|中的|的)+", "", message)
    message = re.sub(r"(?:相关|中的|里的|上面的|的)+\s*$", "", message)
    query = " ".join(part for part in message.split() if part)
    if query:
        return query
    if sort == "hot":
        return "热门"
    if sort == "latest":
        return "最新"
    return ""


def detect_intent_by_rules(message: str) -> dict[str, Any] | None:
    """规则层意图判定；命中返回 dict，未命中返回 None。

    返回 dict 含 intent/knowledge_mode/platform/query/reason/confidence(1.0)。
    """
    stripped = message.strip()
    lowered = stripped.lower()

    # 1. URL 解析（最高优先：给了 URL 就是解析）
    urls = extract_urls(message)
    if urls and len(stripped.replace(urls[0], "").strip()) < 50:
        return {
            "intent": "parse_url",
            "knowledge_mode": detect_knowledge_mode(message),
            "platform": None,
            "query": None,
            "reason": "rule: url detected",
            "confidence": 1.0,
        }

    # 2. 寒暄（去掉常见标点再匹配）
    stripped_norm = stripped.rstrip("？！?!。.~～，, ")
    if stripped_norm in _CHITCHAT_PHRASES or lowered.rstrip("？！?!。.~～，, ") in _CHITCHAT_PHRASES:
        return {
            "intent": "chat",
            "knowledge_mode": "off",
            "platform": None,
            "query": None,
            "reason": "rule: chitchat",
            "confidence": 1.0,
        }

    # 3. 严格知识模式（不改变 intent，只影响 knowledge_mode，需继续判断 intent）
    knowledge_mode = detect_knowledge_mode(message)

    # 4. 多阶段创作（优先于单篇，因为"调研并写一篇"也含"写一篇"）
    if any(m in message for m in _MULTI_AGENT_MARKERS):
        return {
            "intent": "multi_agent",
            "knowledge_mode": knowledge_mode,
            "platform": _detect_platform(message),
            "query": None,
            "reason": "rule: multi-stage creation",
            "confidence": 1.0,
        }

    # 5. 单篇创作
    if any(m in message for m in _TASK_PLAN_MARKERS):
        return {
            "intent": "task_plan",
            "knowledge_mode": knowledge_mode,
            "platform": _detect_platform(message),
            "query": None,
            "reason": "rule: single-piece creation",
            "confidence": 1.0,
        }

    # 6. 平台采集
    platform = _detect_platform(message)
    if platform and any(v in message for v in _COLLECT_VERBS):
        limit, sort, limit_explicit, sort_explicit = _extract_search_constraints(message)
        query = _extract_query(message, platform, sort)
        return {
            "intent": "collect",
            "knowledge_mode": knowledge_mode,
            "platform": platform,
            "query": query or None,
            "limit": limit,
            "sort": sort,
            "_limit_explicit": limit_explicit,
            "_sort_explicit": sort_explicit,
            "reason": "rule: platform collection",
            "confidence": 1.0,
        }

    # 7. 有采集动作但没有平台名（保留采集意图，交给 LLM 补全平台）
    if any(v in message for v in _COLLECT_VERBS):
        limit, sort, limit_explicit, sort_explicit = _extract_search_constraints(message)
        return {
            "intent": "collect",
            "knowledge_mode": knowledge_mode,
            "platform": None,
            "query": _extract_query(message, None, sort) or None,
            "limit": limit,
            "sort": sort,
            "_limit_explicit": limit_explicit,
            "_sort_explicit": sort_explicit,
            "reason": "rule: generic collection",
            "confidence": 0.8,
        }

    # 8. 严格知识模式本身是有效判定：即便无动作词，也返回 chat + strict
    if knowledge_mode == "strict":
        return {
            "intent": "chat",
            "knowledge_mode": "strict",
            "platform": None,
            "query": None,
            "reason": "rule: strict knowledge mode",
            "confidence": 1.0,
        }

    # 未命中，交给 LLM
    return None
