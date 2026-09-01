from __future__ import annotations

import re

from bs4 import BeautifulSoup


class HtmlCleaner:
    """裁剪 HTML，只保留有效文本内容，降低传给 LLM 的 token 数量。"""

    _STRIP_TAGS = {"script", "style", "noscript", "svg", "iframe", "head"}
    _MAX_CHARS = 12_000   # LLM context 预算

    def clean(self, raw_html: str) -> str:
        soup = BeautifulSoup(raw_html, "html.parser")
        for tag in soup.find_all(self._STRIP_TAGS):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text[: self._MAX_CHARS]
