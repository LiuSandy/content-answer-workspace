from __future__ import annotations

import uuid

from ...models import QuestionItem


class QuestionItemMapper:
    """将 LLM 提取的原始 dict 映射为 QuestionItem；只做字段对应和缺省值填充。"""

    def map(self, raw: dict[str, str], platform: str, topic: str) -> QuestionItem | None:
        title = (raw.get("title") or "").strip()
        url = (raw.get("url") or "").strip()
        if not title or not url:
            return None
        return QuestionItem(
            id=raw.get("id") or str(uuid.uuid5(uuid.NAMESPACE_URL, url)),
            platform=platform,
            title=title,
            url=url,
            excerpt=raw.get("excerpt", ""),
            topic=topic,
            answerCount=0,
        )
