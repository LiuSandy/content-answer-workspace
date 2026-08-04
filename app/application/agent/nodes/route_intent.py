"""意图路由节点：规则优先 + LLM 判断执行模式与知识模式。

LLM 一次判定三个维度：
  - intent: chat | parse_url | task_plan | multi_agent
  - knowledge_mode: off | normal | strict（自动决定，不再由用户在前端选择）
  - platform / query：平台采集相关

设计理念：用户只需自然对话，Agent 自动决定该普通回答、查私有资料、
走复合任务规划，还是启动多 Agent 协作。
"""
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
            existing_mode = state.get("knowledge_mode")
            if existing_mode not in ("off", "normal", "strict"):
                existing_mode = "normal"
            return {
                "intent": "parse_url",
                "knowledge_mode": existing_mode,
            }
    # LLM 判断意图 + 知识模式
    try:
        rendered = prompt_registry.render(
            "chat.intent_router",
            user_message=message,
            extracted_urls=str(urls),
        )
        provider = llm_provider_registry.get("deepseek")
        resp = await provider.generate(rendered.to_llm_request())
        content = resp.content.strip()

        data = {"intent": "chat", "knowledge_mode": "normal"}
        if "{" in content:
            json_str = content[content.index("{") : content.rindex("}") + 1]
            data = json.loads(json_str)

        intent = data.get("intent", "chat")
        knowledge_mode = data.get("knowledge_mode", "normal")

        # 合法化：intent 只接受这四个；knowledge_mode 只接受三个
        valid_intents: set[str] = {"chat", "parse_url", "task_plan", "multi_agent"}
        if intent not in valid_intents:
            intent = "chat"
        valid_modes: set[str] = {"off", "normal", "strict"}
        if knowledge_mode not in valid_modes:
            knowledge_mode = "normal"

        # 仅当调用方显式指定了非默认的 knowledge_mode（strict/off）时优先保留，
        # 用于兼容测试与内部直连。默认 normal 不覆盖 LLM 判定。
        existing_mode = state.get("knowledge_mode")
        if existing_mode in ("strict", "off"):
            knowledge_mode = existing_mode

        return {
            "intent": intent,
            "knowledge_mode": knowledge_mode,
        }
    except Exception as e:
        logger.warning("Intent routing failed, defaulting to chat: %s", e)
        existing_mode = state.get("knowledge_mode")
        if existing_mode not in ("off", "normal", "strict"):
            existing_mode = "normal"
        return {"intent": "chat", "knowledge_mode": existing_mode}
