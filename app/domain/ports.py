from __future__ import annotations

from typing import Protocol, Sequence

from ..models import QuestionItem, Topic, WorkflowConfig


class CollectorPort(Protocol):
    """定义平台采集器接口；这样工作流只依赖抽象能力而不依赖知乎等具体平台实现。"""

    platform: str

    async def collect(self, topics: Sequence[Topic], config: WorkflowConfig) -> list[QuestionItem]:
        """按主题采集平台内容；这样不同平台策略都能以相同方法接入工作流。"""


class AnswerGeneratorPort(Protocol):
    """定义回答生成器接口；这样 DeepSeek 等模型适配器可以被替换而不影响应用层。"""

    async def generate_answer(
        self,
        item: QuestionItem,
        answer_style: str,
        cta_text: str,
        system_prompt: str,
    ) -> str:
        """为单个问题生成回答；这样应用层只关心创作结果而不关心模型 API 细节。"""


class TopicExpanderPort(Protocol):
    """定义主题扩展器接口；这样工作流可以先做 AI 扩词，再把检索实现留给不同模型适配器。"""

    async def expand_topic(self, topic: Topic, limit: int = 6) -> list[str]:
        """为单个主题生成一组检索关键词；这样采集流程能把主题选择和检索词生成解耦。"""
