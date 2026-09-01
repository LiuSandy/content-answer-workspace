from __future__ import annotations

from app.modules.acquisition.application.topic_expansion_llm import TopicExpansionService
from app.modules.acquisition.domain.workflow import Topic
from .zhihu import build_keyword_hints, unique_by

_topic_expander = TopicExpansionService()


def merge_retrieval_keywords(topic: Topic, expanded_keywords: list[str]) -> list[str]:
    """合并主题原词和扩展词；这样检索既保留用户原始意图，也能覆盖 AI 推出的相近搜索词。"""

    base_keywords = [topic.name, *topic.keywords]
    merged = [str(keyword).strip() for keyword in [*base_keywords, *expanded_keywords] if str(keyword).strip()]
    return unique_by(merged, lambda item: item.lower())


async def expand_topic_for_collection(topic: Topic, limit: int = 6) -> Topic:
    """为采集准备主题检索词；这样工作流拿到的主题对象就包含本次实际使用的关键词集合。"""

    try:
        expanded_keywords = await _topic_expander.expand_topic(topic, limit=limit)
        retrieval_keywords = merge_retrieval_keywords(topic, expanded_keywords)
    except Exception:
        retrieval_keywords = build_keyword_hints(topic)
    return topic.model_copy(update={"expanded_hints": retrieval_keywords})
