"""意图路由节点：规则优先 + LLM 判断 chat/parse_url/collect。"""
from __future__ import annotations

import json
import logging
from typing import Literal

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

        intent: Literal["chat", "parse_url"] = data.get("intent", "chat")
        if intent == "collect" or intent not in ("chat", "parse_url"):
            intent = "chat"

        return {"intent": intent}
    except Exception as e:
        logger.warning("Intent routing failed, defaulting to chat: %s", e)
        return {"intent": "chat"}
