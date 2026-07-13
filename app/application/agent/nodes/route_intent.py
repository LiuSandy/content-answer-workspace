"""意图路由节点：规则优先 + LLM 判断 chat/parse_url/collect。"""
from __future__ import annotations

import json
import logging
from typing import Literal

from ....domain.dto import CollectionRequest
from ....infrastructure.llm.registry import llm_provider_registry
from ....prompts.registry import prompt_registry
from ..state import ChatAgentState

logger = logging.getLogger(__name__)


async def route_intent_node(state: ChatAgentState) -> dict:
    urls = state.get("extracted_urls", [])
    message = state.get("user_message", "")

    # 规则优先：有 URL 且消息短（明显是粘贴 URL）
    if urls and len(message.strip()) < 300:
        words_without_url = message
        for u in urls:
            words_without_url = words_without_url.replace(u, "").strip()
        if len(words_without_url) < 50:
            return {"intent": "parse_url"}

    # 规则 2：显式包含平台和搜索意图，优先走向 collect
    msg_lower = message.lower().strip()
    has_platform = any(p in msg_lower for p in ("小红书", "知乎", "xhs", "zhihu", "xiaohongshu"))
    has_action = any(a in msg_lower for a in ("搜索", "采集", "搜一下", "找一下", "热门", "最新", "笔记", "帖子", "话题", "问答", "search", "collect", "fetch"))
    if has_platform and has_action and len(msg_lower) < 150:
        platform = "zhihu" if any(z in msg_lower for z in ("知乎", "zhihu")) else "xiaohongshu"
        query = message
        for word in ("搜索", "采集", "搜一下", "找一下", "小红书", "知乎", "xhs", "zhihu", "xiaohongshu", "的", "关于", "最新", "热门", "笔记", "帖子", "话题", "问答"):
            query = query.replace(word, "")
        query = query.strip().strip(":,，。？！\"' ")
        return {
            "intent": "collect",
            "collection_request": CollectionRequest(
                query=query or message,
                platform=platform,
                chat_id=state.get("chat_id"),
                max_results=10,
            )
        }

    # LLM 判断其它意图
    try:
        rendered = prompt_registry.render(
            "chat.intent_router",
            user_message=message,
            extracted_urls=str(urls),
        )
        provider = llm_provider_registry.get("deepseek")
        resp = await provider.generate(rendered.to_llm_request())
        content = resp.content.strip()

        # 提取 JSON
        if "{" in content:
            json_str = content[content.index("{") : content.rindex("}") + 1]
            data = json.loads(json_str)
        else:
            data = {"intent": "chat"}

        intent: Literal["chat", "parse_url", "collect"] = data.get("intent", "chat")
        if intent not in ("chat", "parse_url", "collect"):
            intent = "chat"

        result: dict = {"intent": intent}
        if intent == "collect":
            result["collection_request"] = CollectionRequest(
                query=data.get("query") or message,
                platform=data.get("platform"),
                chat_id=state.get("chat_id"),
                max_results=10,
            )
        return result
    except Exception as e:
        logger.warning("Intent routing failed, defaulting to chat: %s", e)
        return {"intent": "chat"}
