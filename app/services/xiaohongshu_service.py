from __future__ import annotations

import json
import os
import re
from pathlib import Path

from ..core.config import XIAOHONGSHU_COOKIE_PATH_DEFAULT
from .zhihu_service import clean_text, read_optional_file


class XiaohongshuAccessError(RuntimeError):
    """小红书登录态失效或被风控拦截时抛出；这样调用方能区分"内容解析失败可降级跳过"和"账号层面必须终止"两类错误。"""


def load_xiaohongshu_cookie() -> str | None:
    """加载小红书 cookie 内容；这样所有小红书请求都能复用统一的凭据读取规则。"""

    configured = os.getenv("XIAOHONGSHU_COOKIE_FILE", "").strip()
    cookie_path = Path(configured).resolve() if configured else XIAOHONGSHU_COOKIE_PATH_DEFAULT
    content = read_optional_file(cookie_path)
    return content.strip() if content else None


def ensure_xiaohongshu_cookie(cookie: str | None) -> None:
    """校验小红书采集凭据；这样缺少 cookie 时会返回可理解错误，而不是继续触发空结果或风控误判。"""

    if not cookie:
        raise ValueError(
            "小红书采集需要已登录账号的 Cookie；当前缺少：XIAOHONGSHU_COOKIE_FILE。"
            "请登录小红书网页版后导出 cookie 到对应文件路径，并在 .env 中配置该路径后重启后端。"
        )


_LOGIN_WALL_MARKERS = ("login-modal", "手机号登录", "扫码登录", "请先登录")
_CAPTCHA_MARKERS = ("captcha", "验证码", "向右滑动", "滑动验证")


def is_login_wall_html(html: str) -> bool:
    """识别页面是否落在登录墙；这样登录态失效时能及时报错而不是误判为"没搜到内容"。"""

    return any(marker in html for marker in _LOGIN_WALL_MARKERS)


def is_captcha_challenge_html(html: str) -> bool:
    """识别页面是否触发验证码风控；这样不会把验证码页面内容误喂给后续解析逻辑。"""

    return any(marker.lower() in html.lower() for marker in _CAPTCHA_MARKERS)


def ensure_usable_xiaohongshu_page(html: str) -> None:
    """校验页面是否可用于后续解析；登录失效或风控拦截时抛出需要终止整次采集的错误。"""

    if is_login_wall_html(html):
        raise XiaohongshuAccessError(
            "小红书登录态已失效，请重新导出 cookie 并更新 XIAOHONGSHU_COOKIE_FILE 指向的文件"
        )
    if is_captcha_challenge_html(html):
        raise XiaohongshuAccessError("小红书触发了验证码风控拦截，请降低采集频率或更换账号后重试")


def extract_initial_state(html: str) -> dict:
    """从小红书页面 HTML 中提取 window.__INITIAL_STATE__ 注入的前端状态 JSON。"""

    match = re.search(r"window\.__INITIAL_STATE__\s*=\s*(\{.*?\})\s*;?\s*</script>", html, re.S)
    if not match:
        raise ValueError("未能在页面中找到 __INITIAL_STATE__ 数据，页面结构可能已变化或被风控拦截")
    raw = match.group(1).replace("undefined", "null")
    return json.loads(raw)


def parse_note_list_from_search_state(state: dict) -> list[dict[str, str]]:
    """从搜索页状态中解析笔记摘要列表；跳过缺少 id 或标题的异常条目。"""

    feeds = state.get("search", {}).get("feeds", {}).get("feeds", [])
    notes: list[dict[str, str]] = []
    for feed in feeds:
        note_card = feed.get("noteCard") if isinstance(feed, dict) else None
        if not isinstance(note_card, dict):
            continue
        note_id = feed.get("id") or note_card.get("noteId")
        title = clean_text(note_card.get("displayTitle") or "")
        if not note_id or not title:
            continue
        notes.append(
            {
                "id": str(note_id),
                "title": title,
                "excerpt": clean_text(note_card.get("desc") or ""),
                "url": f"https://www.xiaohongshu.com/explore/{note_id}",
            }
        )
    return notes


def parse_note_detail_from_state(state: dict, note_id: str) -> dict[str, object]:
    """从笔记详情页状态中解析正文全文和标签；note_id 找不到时返回空字段而不是抛错。"""

    note_detail_map = state.get("note", {}).get("noteDetailMap", {})
    entry = note_detail_map.get(note_id, {})
    note = entry.get("note", {}) if isinstance(entry, dict) else {}
    tags = [
        clean_text(tag.get("name") or "")
        for tag in note.get("tagList", [])
        if isinstance(tag, dict) and clean_text(tag.get("name") or "")
    ]
    return {
        "title": clean_text(note.get("title") or ""),
        "detail": clean_text(note.get("desc") or ""),
        "tags": tags,
    }


_QUESTION_MARKERS = ("吗", "？", "?", "怎么", "如何", "求", "请问")


def parse_comments_from_state(state: dict, note_id: str) -> list[dict[str, str]]:
    """从笔记评论区状态中解析评论列表；缺少有效内容或 id 的评论会被跳过。"""

    comments_list = state.get("note", {}).get("commentsList", {})
    entry = comments_list.get(note_id, {})
    raw_comments = entry.get("comments", []) if isinstance(entry, dict) else []
    parsed: list[dict[str, str]] = []
    for comment in raw_comments:
        if not isinstance(comment, dict):
            continue
        content = clean_text(comment.get("content") or "")
        comment_id = comment.get("id")
        if not content or not comment_id:
            continue
        parsed.append({"id": str(comment_id), "content": content})
    return parsed


def is_question_comment(content: str) -> bool:
    """判断评论是否是提问；这样评论区抓取只挑出真正的疑问，不是所有评论都当成问题。"""

    return any(marker in content for marker in _QUESTION_MARKERS)


__all__ = [
    "XiaohongshuAccessError",
    "load_xiaohongshu_cookie",
    "ensure_xiaohongshu_cookie",
    "is_login_wall_html",
    "is_captcha_challenge_html",
    "ensure_usable_xiaohongshu_page",
    "extract_initial_state",
    "parse_note_list_from_search_state",
    "parse_note_detail_from_state",
    "parse_comments_from_state",
    "is_question_comment",
    "clean_text",
]
