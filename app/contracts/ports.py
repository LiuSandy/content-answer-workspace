"""领域层接口定义（Ports）；所有接口仅用 Protocol 定义，不引入任何框架或平台具体实现。

依赖方向：Domain 层不依赖 FastAPI、LangGraph、SQLAlchemy 或具体模型供应商。
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Protocol

from pydantic import BaseModel

from .dto import (
    CollectionRequest,
    LLMMessage,
    LLMRequest,
    LLMResponse,
    LLMStreamEvent,
    ParseUrlRequest,
    SourceItemDTO,
    StructuredResult,
    ToolContext,
)


# ─────────────────────────────────────────────────────────────────────────────
# Content Source 接口
# ─────────────────────────────────────────────────────────────────────────────

class ContentSource(Protocol):
    """多平台内容采集器统一接口；实现类放入 infrastructure/sources/adapters/。

    如果某平台只支持解析或只支持采集，应在 capabilities 中显式声明，
    而不是提供一个运行后才报错的空实现。
    """

    key: str  # 平台唯一标识，如 "zhihu" / "xiaohongshu" / "universal"

    @property
    def capabilities(self) -> set[str]:
        """声明该适配器支持的能力，如 {"parse_url", "collect"}。"""
        ...

    def can_handle_url(self, url: str) -> bool:
        """判断此适配器是否可处理给定 URL；用于 Source Registry 路由。"""
        ...

    async def parse_url(
        self, request: ParseUrlRequest, context: ToolContext
    ) -> SourceItemDTO:
        """解析单个 URL 并返回标准化帖子；仅当 capabilities 包含 "parse_url" 时调用。"""
        ...

    async def collect(
        self, request: CollectionRequest, context: ToolContext
    ) -> list[SourceItemDTO]:
        """按主题/关键词采集帖子列表；仅当 capabilities 包含 "collect" 时调用。"""
        ...


# ─────────────────────────────────────────────────────────────────────────────
# LLM Provider 接口
# ─────────────────────────────────────────────────────────────────────────────

class LLMProvider(Protocol):
    """语言模型供应商统一接口；实现类放入 infrastructure/llm/providers/。

    Agent 和 Workflow 只依赖此接口，不引用 DeepSeek SDK 或任何专有响应类型。
    """

    key: str  # 供应商唯一标识，如 "deepseek" / "openai"
    default_model: str

    # 声明结构化输出能力（roadmap R1）：不支持原生 json_schema 的兼容端点
    # 不得声明它；结构化生成从声明的最高优先级方法开始，不做异常探测。
    structured_methods: list[str] = ["json_mode", "generic_parse"]

    async def generate(self, request: LLMRequest) -> LLMResponse:
        """同步生成完整回复；适用于结构化输出和意图路由等场景。"""
        ...

    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMStreamEvent]:
        """流式生成回复；适用于聊天和长文本生成场景。"""
        ...

    def model_for(self, purpose: str | None = None) -> str:
        """返回默认模型，或指定用途的模型覆盖。"""
        ...


class StructuredGenerationPort(Protocol):
    """结构化输出公共入口；实现类（LLMServiceAdapter）供质检/选题/记忆/摘要共用。

    调用方拿到 StructuredResult 后，把 method_used/attempts/degradation_reason
    审计到各自 AIOperation.model_parameters。
    """

    async def generate_structured(
        self,
        schema: type[BaseModel],
        system_prompt: str,
        user_prompt: str,
        retries: int = 1,
    ) -> StructuredResult[Any]:
        """按 schema 生成结构化输出；三级降级，全部失败时 value 为 None 不抛异常。"""
        ...


# ─────────────────────────────────────────────────────────────────────────────
# Task Dispatcher 接口（异步任务抽象）
# ─────────────────────────────────────────────────────────────────────────────

class TaskHandle(Protocol):
    """任务句柄；用于查询任务状态或取消任务。"""

    task_id: str
    status: str  # pending / running / completed / failed / cancelled


class ApplicationTask(Protocol):
    """可提交给 TaskDispatcher 的任务定义。"""

    task_id: str
    idempotency_key: str | None

    async def execute(self) -> Any: ...


class TaskDispatcher(Protocol):
    """任务分发器；第一版用 InProcessTaskDispatcher，未来可替换为 Dramatiq/Celery。"""

    async def submit(self, task: ApplicationTask) -> TaskHandle: ...


# ─────────────────────────────────────────────────────────────────────────────
# 历史遗留兼容接口 (Legacy Compatibility Ports)
# ─────────────────────────────────────────────────────────────────────────────

class CollectorPort(Protocol):
    """历史遗留的采集器接口。"""
    platform: str
    async def collect(self, topics: Any, config: Any) -> Any: ...


class AnswerGeneratorPort(Protocol):
    """历史遗留的回答生成器接口。"""
    async def generate_answer(self, *args: Any, **kwargs: Any) -> Any: ...


class TopicExpanderPort(Protocol):
    """历史遗留的主题扩展接口。"""
    async def expand_topic(self, *args: Any, **kwargs: Any) -> Any: ...


# ─────────────────────────────────────────────────────────────────────────────
# 知识库扩展 Ports (Knowledge Ports)
# ─────────────────────────────────────────────────────────────────────────────

class DocumentParserPort(Protocol):
    """知识库文档解析器端口。"""
    async def parse(self, source_path: str, doc_id: str) -> Any: ...


class EmbeddingProviderPort(Protocol):
    """Embedding 向量计算端口。"""
    dimensions: int
    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class RerankerProviderPort(Protocol):
    """Reranker 重排序端口。"""
    async def rerank(self, query: str, documents: list[str]) -> list[float]: ...
