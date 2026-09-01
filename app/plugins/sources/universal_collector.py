from __future__ import annotations

import os
from pathlib import Path
from typing import Sequence

from app.shared.ports import CollectorPort
from app.modules.acquisition.domain.workflow import QuestionItem, Topic, WorkflowConfig
from .extractors.llm_extractor import LLMExtractor
from .fetchers.http_fetcher import HttpFetcher
from .html_cleaner import HtmlCleaner
from .platform_config import PlatformConfig
from .question_item_mapper import QuestionItemMapper


class UniversalCollector:
    """编排「获取 → 清洗 → 提取 → 映射」采集流程；平台差异完全由 PlatformConfig 描述。"""

    platform: str

    def __init__(self, config: PlatformConfig) -> None:
        self._config = config
        self.platform = config.name
        self._fetcher = self._build_fetcher(config)
        self._extractor = LLMExtractor()
        self._cleaner = HtmlCleaner()
        self._mapper = QuestionItemMapper()

    def _build_fetcher(self, config: PlatformConfig):
        cookie_string = self._load_cookie_string(config)
        if config.fetcher == "playwright":
            from .fetchers.playwright_fetcher import PlaywrightFetcher
            return PlaywrightFetcher(cookie_string=cookie_string)
        return HttpFetcher(cookie_string=cookie_string)

    def _load_cookie_string(self, config: PlatformConfig) -> str | None:
        if not config.auth.env_var:
            return None
        cookie_file = os.getenv(config.auth.env_var, "").strip()
        if not cookie_file or not Path(cookie_file).exists():
            return None
        return Path(cookie_file).read_text(encoding="utf-8").strip() or None

    async def collect(
        self, topics: Sequence[Topic], config: WorkflowConfig
    ) -> list[QuestionItem]:
        results: list[QuestionItem] = []
        headers = self._default_headers(config)
        for topic in topics:
            keywords = topic.expanded_hints or topic.keywords or [topic.name]
            for keyword in keywords:
                url = self._config.search_url_template.format(keyword=keyword)
                try:
                    html = await self._fetcher.fetch(url, headers)
                    text = self._cleaner.clean(html)
                    raw_items = await self._extractor.extract(text, self._config.extraction_prompt)
                    for raw in raw_items:
                        item = self._mapper.map(raw, self.platform, topic.name)
                        if item:
                            results.append(item)
                except Exception:
                    continue
        return results

    def _default_headers(self, config: WorkflowConfig) -> dict[str, str]:
        return {"User-Agent": config.user_agent}
