from __future__ import annotations

import json
import os
import re
from collections.abc import AsyncIterator

from openai import AsyncOpenAI, OpenAI

from ...core.config import get_required_env
from ...domain.ports import AnswerGeneratorPort, TopicExpanderPort
from ...models import QuestionItem, Topic


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
        answer_style: str,
        cta_text: str,
        system_prompt: str,
        generation_prompt: str,
        content_constraint: str | None = None,
    ) -> str:
        """调用 DeepSeek 为问题创作回答；这样回答提示词、平台语境和模型输出处理集中在适配器内。"""

        client = self.get_client()
        model = get_required_env("DEEPSEEK_MODEL")
        platform_label = item.platform or "zhihu"
        if item.content_mode == "imitate":
            intro_line = (
                f"请参考下面这篇{platform_label}笔记的选题角度和写作风格，创作一篇全新的原创笔记，"
                f"不要照抄原文内容，只学习其风格和结构。整体风格要求：{answer_style}"
            )
        else:
            intro_line = f"请围绕下面这个{platform_label}问题写一篇适合发布到对应平台的原创回答，整体风格要求：{answer_style}"
        prompt_parts = [
            intro_line,
            "",
            "全局生成规则：",
            generation_prompt,
        ]
        if content_constraint and content_constraint.strip():
            prompt_parts += [
                "",
                f"内容约束（必须严格遵守）：回答只能围绕「{content_constraint.strip()}」展开，不要回答与此无关的内容。",
            ]
        prompt_parts += [
            "",
            f"平台：{platform_label}",
            f"问题标题：{item.title}",
            f"问题链接：{item.url}",
            f"问题分类：{item.topic or '未分类'}",
            f"问题摘要：{item.excerpt or '无'}",
            f"结尾引流文案：{cta_text}",
        ]
        prompt = "\n".join(prompt_parts)
        completion = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {"role": "user", "content": prompt},
            ],
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
        answer_style: str,
        cta_text: str,
        system_prompt: str,
        generation_prompt: str,
        content_constraint: str | None = None,
    ) -> AsyncIterator[str]:
        """流式调用 DeepSeek 生成回答；逐 token yield 给调用方，供 SSE 端点推送。"""

        client = self.get_async_client()
        model = get_required_env("DEEPSEEK_MODEL")
        platform_label = item.platform or "zhihu"
        if item.content_mode == "imitate":
            intro_line = (
                f"请参考下面这篇{platform_label}笔记的选题角度和写作风格，创作一篇全新的原创笔记，"
                f"不要照抄原文内容，只学习其风格和结构。整体风格要求：{answer_style}"
            )
        else:
            intro_line = f"请围绕下面这个{platform_label}问题写一篇适合发布到对应平台的原创回答，整体风格要求：{answer_style}"
        prompt_parts = [
            intro_line,
            "",
            "全局生成规则：",
            generation_prompt,
        ]
        if content_constraint and content_constraint.strip():
            prompt_parts += [
                "",
                f"内容约束（必须严格遵守）：回答只能围绕「{content_constraint.strip()}」展开，不要回答与此无关的内容。",
            ]
        prompt_parts += [
            "",
            f"平台：{platform_label}",
            f"问题标题：{item.title}",
            f"问题链接：{item.url}",
            f"问题分类：{item.topic or '未分类'}",
            f"问题摘要：{item.excerpt or '无'}",
            f"结尾引流文案：{cta_text}",
        ]
        prompt = "\n".join(prompt_parts)
        stream = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
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
        answer_style: str,
        cta_text: str,
        system_prompt: str,
        generation_prompt: str,
        content_constraint: str | None = None,
    ) -> str:
        """对已有回答进行润色改写；这样用户修改的草稿可以通过 AI 改善表达而不丢失原有观点。"""

        client = self.get_client()
        model = get_required_env("DEEPSEEK_MODEL")
        platform_label = item.platform or "zhihu"
        if item.content_mode == "imitate":
            intro_line = (
                f"请对下面这篇{platform_label}笔记进行润色改写。要求：保留原有核心创意和结构，不要引入新观点；"
                f"改善语言表达，消除 AI 腔、模板痕迹和空泛表述；让行文更自然、简洁、像真人写的。整体风格要求：{answer_style}"
            )
        else:
            intro_line = (
                f"请对下面这篇{platform_label}回答进行润色改写。要求：保留原有核心观点和论证思路，不要引入新观点；"
                f"改善语言表达，消除 AI 腔、模板痕迹和空泛表述；让行文更自然、简洁、像真人写的。整体风格要求：{answer_style}"
            )
        prompt_parts = [
            intro_line,
            "",
            "全局生成规则：",
            generation_prompt,
        ]
        if content_constraint and content_constraint.strip():
            prompt_parts += [
                "",
                f"内容约束（必须严格遵守）：回答只能围绕「{content_constraint.strip()}」展开，不要回答与此无关的内容。",
            ]
        prompt_parts += [
            "",
            f"平台：{platform_label}",
            f"问题标题：{item.title}",
            f"问题链接：{item.url}",
            f"问题分类：{item.topic or '未分类'}",
            f"结尾引流文案：{cta_text}",
            "",
            "当前回答草稿（请以此为基础润色，不要大幅偏离原有内容）：",
            current_answer,
        ]
        prompt = "\n".join(prompt_parts)
        completion = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
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
        answer_style: str,
        cta_text: str,
        system_prompt: str,
        generation_prompt: str,
        content_constraint: str | None = None,
    ) -> AsyncIterator[str]:
        """流式润色回答；逐 token yield，供 SSE 端点推送。"""

        client = self.get_async_client()
        model = get_required_env("DEEPSEEK_MODEL")
        platform_label = item.platform or "zhihu"
        if item.content_mode == "imitate":
            intro_line = (
                f"请对下面这篇{platform_label}笔记进行润色改写。要求：保留原有核心创意和结构，不要引入新观点；"
                f"改善语言表达，消除 AI 腔、模板痕迹和空泛表述；让行文更自然、简洁、像真人写的。整体风格要求：{answer_style}"
            )
        else:
            intro_line = (
                f"请对下面这篇{platform_label}回答进行润色改写。要求：保留原有核心观点和论证思路，不要引入新观点；"
                f"改善语言表达，消除 AI 腔、模板痕迹和空泛表述；让行文更自然、简洁、像真人写的。整体风格要求：{answer_style}"
            )
        prompt_parts = [
            intro_line,
            "",
            "全局生成规则：",
            generation_prompt,
        ]
        if content_constraint and content_constraint.strip():
            prompt_parts += [
                "",
                f"内容约束（必须严格遵守）：回答只能围绕「{content_constraint.strip()}」展开，不要回答与此无关的内容。",
            ]
        prompt_parts += [
            "",
            f"平台：{platform_label}",
            f"问题标题：{item.title}",
            f"问题链接：{item.url}",
            f"问题分类：{item.topic or '未分类'}",
            f"结尾引流文案：{cta_text}",
            "",
            "当前回答草稿（请以此为基础润色，不要大幅偏离原有内容）：",
            current_answer,
        ]
        prompt = "\n".join(prompt_parts)
        stream = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
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
