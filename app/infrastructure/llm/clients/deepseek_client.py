from __future__ import annotations

import json
import os
import re
from collections.abc import AsyncIterator

from openai import AsyncOpenAI, OpenAI

from app.config.runtime import get_required_env
from app.contracts.ports import AnswerGeneratorPort, TopicExpanderPort
from app.api.schemas.workflow import QuestionItem, Topic


class DeepSeekAnswerGenerator(AnswerGeneratorPort):
    """封装 DeepSeek 回答生成能力；这样模型配置和 API 调用细节不会散落在业务流程中。"""

    def __init__(self) -> None:
        """初始化延迟创建的模型客户端；这样缺少配置时只在真正生成回答时才报错。"""

        self._client: OpenAI | None = None
        self._async_client: AsyncOpenAI | None = None

    def get_client(self) -> OpenAI:
        """获取 DeepSeek OpenAI 兼容客户端；这样同一进程内可以复用客户端并集中读取模型配置。"""

        if self._client is None:
            self._client = OpenAI(
                api_key=get_required_env("DEEPSEEK_API_KEY"),
                base_url=get_required_env("DEEPSEEK_BASE_URL").strip().rstrip("/"),
            )
        return self._client

    def get_async_client(self) -> AsyncOpenAI:
        """获取异步 OpenAI 兼容客户端；供流式调用使用，不阻塞事件循环。"""

        if self._async_client is None:
            self._async_client = AsyncOpenAI(
                api_key=get_required_env("DEEPSEEK_API_KEY"),
                base_url=get_required_env("DEEPSEEK_BASE_URL").strip().rstrip("/"),
            )
        return self._async_client

    async def generate_answer(
        self,
        item: QuestionItem,
        answer_style: str = "",
        cta_text: str = "",
        system_prompt: str = "",
        generation_prompt: str = "",
        content_constraint: str | None = None,
    ) -> str:
        """调用 DeepSeek 为问题创作回答；使用 Prompt Registry 模板。"""
        from app.prompts.registry import prompt_registry
        rendered = prompt_registry.render(
            "writing.answer_generate",
        )
        user_rendered = prompt_registry.render(
            "writing.user_generate",
            title=item.title,
            content=item.excerpt or item.detail or "",
            content_mode=item.content_mode,
        )
        rendered.messages.extend(user_rendered.messages)
            
        client = self.get_client()
        messages = [{"role": m.role, "content": m.content} for m in rendered.messages]
        if cta_text and cta_text.strip():
            messages.append({"role": "user", "content": f"\n\n结尾引流文案：{cta_text}"})

        completion = client.chat.completions.create(
            model=rendered.model or get_required_env("DEEPSEEK_MODEL"),
            messages=messages,
            temperature=rendered.temperature,
            max_tokens=rendered.max_tokens,
        )
        content = completion.choices[0].message.content if completion.choices else None
        if isinstance(content, str):
            return self._normalize_answer_content(content)
        if isinstance(content, list):
            text = "".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in content)
            return self._normalize_answer_content(text)
        raise ValueError("DeepSeek returned empty answer content")

    async def generate_answer_stream(
        self,
        item: QuestionItem,
        answer_style: str = "",
        cta_text: str = "",
        system_prompt: str = "",
        generation_prompt: str = "",
        content_constraint: str | None = None,
    ) -> AsyncIterator[str]:
        """流式调用 DeepSeek 生成回答；使用 Prompt Registry 模板。"""
        from app.prompts.registry import prompt_registry
        rendered = prompt_registry.render(
            "writing.answer_generate",
        )
        user_rendered = prompt_registry.render(
            "writing.user_generate",
            title=item.title,
            content=item.excerpt or item.detail or "",
            content_mode=item.content_mode,
        )
        rendered.messages.extend(user_rendered.messages)

        client = self.get_async_client()
        messages = [{"role": m.role, "content": m.content} for m in rendered.messages]
        if cta_text and cta_text.strip():
            messages.append({"role": "user", "content": f"\n\n结尾引流文案：{cta_text}"})

        stream = await client.chat.completions.create(
            model=rendered.model or get_required_env("DEEPSEEK_MODEL"),
            messages=messages,
            temperature=rendered.temperature,
            max_tokens=rendered.max_tokens,
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and delta.content:
                yield delta.content

    async def polish_answer(
        self,
        item: QuestionItem,
        current_answer: str,
        answer_style: str = "",
        cta_text: str = "",
        system_prompt: str = "",
        generation_prompt: str = "",
        content_constraint: str | None = None,
    ) -> str:
        """对已有回答进行润色改写；使用 Prompt Registry 模板。"""
        from app.prompts.registry import prompt_registry
        rendered = prompt_registry.render(
            "writing.answer_rewrite",
        )
        user_rendered = prompt_registry.render(
            "writing.user_rewrite",
            title=item.title,
            current_answer=current_answer,
            instruction="润色改写语言表达，消除 AI 腔，让行文更自然简洁，保留原有观点。",
            content_mode=item.content_mode,
        )
        rendered.messages.extend(user_rendered.messages)

        client = self.get_client()
        messages = [{"role": m.role, "content": m.content} for m in rendered.messages]

        completion = client.chat.completions.create(
            model=rendered.model or get_required_env("DEEPSEEK_MODEL"),
            messages=messages,
            temperature=rendered.temperature,
            max_tokens=rendered.max_tokens,
        )
        content = completion.choices[0].message.content if completion.choices else None
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            text = "".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in content)
            return text.strip()
        raise ValueError("DeepSeek returned empty polish content")

    async def polish_answer_stream(
        self,
        item: QuestionItem,
        current_answer: str,
        answer_style: str = "",
        cta_text: str = "",
        system_prompt: str = "",
        generation_prompt: str = "",
        content_constraint: str | None = None,
    ) -> AsyncIterator[str]:
        """流式润色回答；使用 Prompt Registry 模板。"""
        from app.prompts.registry import prompt_registry
        rendered = prompt_registry.render(
            "writing.answer_rewrite",
        )
        user_rendered = prompt_registry.render(
            "writing.user_rewrite",
            title=item.title,
            current_answer=current_answer,
            instruction="润色改写语言表达，消除 AI 腔，让行文更自然简洁，保留原有观点。",
            content_mode=item.content_mode,
        )
        rendered.messages.extend(user_rendered.messages)

        client = self.get_async_client()
        messages = [{"role": m.role, "content": m.content} for m in rendered.messages]

        stream = await client.chat.completions.create(
            model=rendered.model or get_required_env("DEEPSEEK_MODEL"),
            messages=messages,
            temperature=rendered.temperature,
            max_tokens=rendered.max_tokens,
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and delta.content:
                yield delta.content

    def _normalize_answer_content(self, content: str) -> str:
        """规范化回答输出；这样模型返回的内容在交给上层前统一做基本清理。"""

        return content.strip()

    async def call_raw(self, system: str, user: str) -> str:
        """通用 LLM 调用，不附加任何业务提示词。供 Agent 层和提取器使用。"""
        client = self.get_client()
        model = get_required_env("DEEPSEEK_MODEL")
        completion = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        content = completion.choices[0].message.content if completion.choices else None
        if isinstance(content, str):
            return content.strip()
        raise ValueError("LLM returned empty content")

    async def call_raw_stream(self, system: str, user: str) -> AsyncIterator[str]:
        """通用 LLM 流式调用，不附加任何业务提示词。供 Agent 层 SSE 端点使用。"""
        client = self.get_async_client()
        model = get_required_env("DEEPSEEK_MODEL")
        stream = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and delta.content:
                yield delta.content

    async def chat(self, messages: list[dict[str, str]]) -> str:
        """多轮对话调用，messages 是完整历史（含 system/user/assistant），不附加任何业务提示词。"""
        client = self.get_client()
        model = get_required_env("DEEPSEEK_MODEL")
        completion = client.chat.completions.create(model=model, messages=messages)
        content = completion.choices[0].message.content if completion.choices else None
        if isinstance(content, str):
            return content.strip()
        raise ValueError("LLM returned empty chat content")


class DeepSeekTopicExpander(TopicExpanderPort):
    """封装 DeepSeek 主题扩词能力；这样采集前的关键词扩展可以复用同一套模型配置和接入方式。"""

    def __init__(self) -> None:
        """初始化延迟创建的模型客户端；这样只有在真正需要扩词时才读取模型配置。"""

        self._client: OpenAI | None = None

    def get_client(self) -> OpenAI:
        """获取 DeepSeek OpenAI 兼容客户端；这样主题扩词和回答生成都能走统一的模型出口。"""

        if self._client is None:
            self._client = OpenAI(
                api_key=get_required_env("DEEPSEEK_API_KEY"),
                base_url=get_required_env("DEEPSEEK_BASE_URL").strip().rstrip("/"),
            )
        return self._client

    async def expand_topic(self, topic: Topic, limit: int = 6) -> list[str]:
        """为主题扩展检索关键词；这样采集流程能先得到一批相近主题，再批量发起平台搜索。"""

        client = self.get_client()
        model = os.getenv("DEEPSEEK_TOPIC_EXPANSION_MODEL", "").strip() or get_required_env("DEEPSEEK_MODEL")
        seed_keywords = "、".join(keyword for keyword in topic.keywords if keyword.strip()) or "无"
        prompt = "\n".join(
            [
                "你现在是中文内容检索助手。",
                "任务：根据给定主题，补充一批适合社交平台检索的相近主题词或搜索关键词。",
                "要求：",
                f"1. 返回 4 到 {max(limit, 4)} 个中文关键词或短语。",
                "2. 关键词要贴近用户在知乎真实会搜索的问题主题，不要写解释。",
                "3. 不要返回序号、标题、Markdown 代码块。",
                "4. 允许包含少量英文术语，但整体以中文检索词为主。",
                "5. 输出必须是 JSON，对象格式固定为 {\"keywords\": [\"词1\", \"词2\"]}。",
                "",
                f"主题名称：{topic.name}",
                f"已有关键词：{seed_keywords}",
            ]
        )
        completion = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": "你只返回 JSON，不要输出任何额外说明。",
                },
                {"role": "user", "content": prompt},
            ],
        )
        content = completion.choices[0].message.content if completion.choices else None
        text = self._coerce_content_to_text(content)
        keywords = self._parse_keywords(text, limit)
        if not keywords:
            raise ValueError(f"DeepSeek returned empty topic keywords for topic: {topic.name}")
        return keywords

    def _coerce_content_to_text(self, content: str | list[object] | None) -> str:
        """把模型返回内容整理成纯文本；这样无论 SDK 返回字符串还是分片列表都能继续解析。"""

        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            return "".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in content).strip()
        return ""

    def _parse_keywords(self, text: str, limit: int) -> list[str]:
        """解析模型返回的关键词列表；这样模型偶发偏离 JSON 约束时仍能尽量恢复可用结果。"""

        if not text:
            return []

        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            payload = self._extract_json_fragment(text)

        if isinstance(payload, dict):
            raw_keywords = payload.get("keywords", [])
        elif isinstance(payload, list):
            raw_keywords = payload
        else:
            raw_keywords = []

        if not raw_keywords:
            raw_keywords = re.split(r"[\n,，、;；]+", text)

        normalized: list[str] = []
        seen: set[str] = set()
        for raw_keyword in raw_keywords:
            keyword = str(raw_keyword).strip().strip("\"'[]")
            if not keyword:
                continue
            key = keyword.lower()
            if key in seen:
                continue
            seen.add(key)
            normalized.append(keyword)
            if len(normalized) >= limit:
                break
        return normalized

    def _extract_json_fragment(self, text: str) -> dict[str, object] | list[object] | None:
        """从自由文本中提取 JSON 片段；这样模型夹带说明时仍有机会恢复结构化关键词结果。"""

        match = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", text)
        if not match:
            return None
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            return None
