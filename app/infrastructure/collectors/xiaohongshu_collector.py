from __future__ import annotations

import asyncio
from typing import Sequence

from ...config.loader import get_settings
from app.contracts.ports import CollectorPort
from app.api.schemas.workflow import QuestionItem, Topic, WorkflowConfig
from ...services.xiaohongshu_service import (
    ensure_usable_xiaohongshu_page,
    ensure_xiaohongshu_cookie,
    extract_initial_state,
    is_question_comment,
    load_xiaohongshu_cookie,
    parse_comments_from_state,
    parse_note_detail_from_state,
    parse_note_list_from_search_state,
)
from .fetchers.playwright_fetcher import PlaywrightFetcher

XIAOHONGSHU_COOKIE_DOMAIN = get_settings().xiaohongshu.cookie_domain
REQUEST_INTERVAL_SECONDS = get_settings().xiaohongshu.request_interval_seconds


class XiaohongshuCollector(CollectorPort):
    """实现小红书平台采集策略；按 content_mode 产出笔记仿写素材或评论区问答素材。"""

    platform = "xiaohongshu"

    def __init__(self, fetcher: PlaywrightFetcher | None = None) -> None:
        cookie = load_xiaohongshu_cookie()
        ensure_xiaohongshu_cookie(cookie)
        self._fetcher = fetcher or PlaywrightFetcher(cookie_string=cookie, cookie_domain=XIAOHONGSHU_COOKIE_DOMAIN)

    async def collect(self, topics: Sequence[Topic], config: WorkflowConfig) -> list[QuestionItem]:
        """按主题和关键词采集小红书内容；这样一次调用能覆盖多个主题扩展出的检索词。"""

        items: list[QuestionItem] = []
        for topic in topics:
            keywords = topic.expanded_hints or topic.keywords or [topic.name]
            for keyword in keywords:
                items.extend(await self._collect_for_keyword(topic, keyword, config))
                await asyncio.sleep(REQUEST_INTERVAL_SECONDS)
        return items

    async def _collect_for_keyword(
        self, topic: Topic, keyword: str, config: WorkflowConfig
    ) -> list[QuestionItem]:
        search_url = f"https://www.xiaohongshu.com/search_result?keyword={keyword}"
        html = await self._fetcher.fetch(search_url, {"User-Agent": config.user_agent})
        ensure_usable_xiaohongshu_page(html)
        state = extract_initial_state(html)
        notes = parse_note_list_from_search_state(state)

        results: list[QuestionItem] = []
        for note in notes:
            try:
                results.extend(await self._collect_for_note(topic, note, config))
            except ValueError:
                continue
        return results

    async def _collect_for_note(
        self, topic: Topic, note: dict[str, str], config: WorkflowConfig
    ) -> list[QuestionItem]:
        detail_html = await self._fetcher.fetch(note["url"], {"User-Agent": config.user_agent})
        ensure_usable_xiaohongshu_page(detail_html)
        state = extract_initial_state(detail_html)
        detail = parse_note_detail_from_state(state, note["id"])

        if config.content_mode == "imitate":
            return [
                QuestionItem(
                    id=note["id"],
                    platform=self.platform,
                    title=detail.get("title") or note["title"],
                    url=note["url"],
                    excerpt=note.get("excerpt", ""),
                    detail=str(detail.get("detail", "")),
                    topic=topic.name,
                    contentMode="imitate",
                )
            ]

        comments = parse_comments_from_state(state, note["id"])
        results: list[QuestionItem] = []
        for comment in comments:
            if not is_question_comment(comment["content"]):
                continue
            results.append(
                QuestionItem(
                    id=f"{note['id']}:{comment['id']}",
                    platform=self.platform,
                    title=comment["content"],
                    url=note["url"],
                    excerpt=str(detail.get("title") or note["title"]),
                    detail=str(detail.get("detail", "")),
                    topic=topic.name,
                    contentMode="answer",
                )
            )
        return results
