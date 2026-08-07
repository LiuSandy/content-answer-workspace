"""领域层 DTO（Data Transfer Objects）；用于 Agent State、工具契约和跨层数据传递。

所有 DTO 使用 Pydantic v2 定义，不依赖 SQLAlchemy 或任何框架。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, Literal, TypeVar

import uuid
from pydantic import BaseModel, Field
from pydantic.alias_generators import to_camel

T = TypeVar("T")



# ─────────────────────────────────────────────────────────────────────────────
# Content Source DTO
# ─────────────────────────────────────────────────────────────────────────────

class SourceItemDTO(BaseModel):
    """平台采集或 URL 解析结果的标准化表示；所有平台适配器返回此格式。"""

    id: uuid.UUID | None = None
    external_id: str | None = None

    platform: str
    url: str
    title: str
    content: str | None = None
    author: str | None = None
    summary: str | None = None
    metrics: dict[str, int | float | str] = Field(default_factory=dict)
    published_at: datetime | None = None
    raw_metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = {
        "alias_generator": to_camel,
        "populate_by_name": True,
    }


class ParseUrlRequest(BaseModel):
    """URL 解析工具请求参数。"""

    url: str
    chat_id: str
    # 可选：用户在消息中附带的额外说明
    hint: str | None = None

    model_config = {"populate_by_name": True}


class CollectionRequest(BaseModel):
    """主题采集工具请求参数。"""

    query: str
    platform: str | None = None  # None 表示由 Registry 自动选择
    chat_id: str
    max_results: int = Field(default=10, ge=1, le=50)
    idempotency_key: str | None = None

    model_config = {"populate_by_name": True}


class ToolContext(BaseModel):
    """工具执行上下文；传递给 ContentSource 适配器，但不包含敏感凭证。"""

    chat_id: str
    run_id: str
    # 平台凭证 key 名（具体值从 secrets store 读取，不在 context 中传递）
    credential_key: str | None = None

    model_config = {"populate_by_name": True}


# ─────────────────────────────────────────────────────────────────────────────
# LLM Provider DTO
# ─────────────────────────────────────────────────────────────────────────────

class LLMMessage(BaseModel):
    """单条 LLM 消息。"""

    role: Literal["system", "user", "assistant"]
    content: str


class LLMRequest(BaseModel):
    """LLM 调用请求；由 PromptRegistry 渲染后传给 LLMProvider。"""

    messages: list[LLMMessage]
    model: str
    temperature: float = 0.7
    max_tokens: int = 4096
    # 结构化输出 JSON Schema（可选）
    response_format: dict[str, Any] | None = None
    # 额外供应商参数（透传，不做类型约束）
    extra: dict[str, Any] = Field(default_factory=dict)

    model_config = {"populate_by_name": True}


class LLMResponse(BaseModel):
    """LLM 同步调用完整响应。"""

    content: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    model: str | None = None
    finish_reason: str | None = None

    model_config = {"populate_by_name": True}


class LLMStreamEvent(BaseModel):
    """LLM 流式响应中的单个事件。"""

    delta: str = ""  # 当前增量文本
    finish_reason: str | None = None
    input_tokens: int | None = None   # 仅在最后一个事件携带
    output_tokens: int | None = None  # 仅在最后一个事件携带

    model_config = {"populate_by_name": True}


# ─────────────────────────────────────────────────────────────────────────────
# 结构化输出公共类型（roadmap R1）
# ─────────────────────────────────────────────────────────────────────────────

class StructuredResult(BaseModel, Generic[T]):
    """结构化输出结果；含降级元数据，底层不写 DB。

    降级元数据（method_used / attempts / degradation_reason）由业务调用方
    审计到各自 AIOperation.model_parameters。
    """

    value: T | None = None
    method_used: Literal["json_schema", "json_mode", "generic_parse"] | None = None
    attempts: int = 0
    degradation_reason: str | None = None

    model_config = {"populate_by_name": True}


class IntentRoute(BaseModel):
    """意图路由 LLM 判定结果；字段对齐 route_intent 节点消费（spec §4.1）。"""

    intent: Literal["chat", "parse_url", "collect", "task_plan", "multi_agent"] = "chat"
    knowledge_mode: Literal["off", "normal", "strict"] = "normal"
    confidence: float = Field(default=0.9, ge=0.0, le=1.0)
    platform: str | None = None
    query: str | None = None
    reason: str | None = None

    model_config = {"populate_by_name": True}


class QualityReport(BaseModel):
    """质检报告；分数统一为 0..100 整数（roadmap R1 接口决定）。"""

    overall_score: int = Field(ge=0, le=100)
    dimension_scores: dict[str, int] = Field(default_factory=dict)
    issues: list[dict[str, Any]] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    summary: str = ""

    model_config = {"populate_by_name": True}


class TopicEvaluation(BaseModel):
    """选题评估；字段固定为 worth_score/reason/competition_level/user_match/suggestion。"""

    worth_score: int = Field(ge=0, le=100)
    reason: str
    competition_level: Literal["low", "medium", "high"]
    user_match: int = Field(ge=0, le=100)
    suggestion: str

    model_config = {"populate_by_name": True}


class MemoryExtraction(BaseModel):
    """单条记忆抽取条目；memory_type 对齐 memory_service.VALID_TYPES（含 implicit）。"""

    memory_type: Literal["explicit", "implicit", "work_pattern"] = "explicit"
    content: str
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)

    model_config = {"populate_by_name": True}


class ConversationSummary(BaseModel):
    """对话滚动摘要；唯一键为 (chat_id, branch_root_message_id)，供 R4 使用。"""

    summary: str
    covered_message_ids: list[str] = Field(default_factory=list)
    last_covered_message_id: str | None = None
    version: int = 1

    model_config = {"populate_by_name": True}


# ─────────────────────────────────────────────────────────────────────────────
# Chat Agent State DTO
# ─────────────────────────────────────────────────────────────────────────────

class AgentError(BaseModel):
    """Agent 执行过程中捕获的错误；传递给 build_response 节点生成友好错误消息。"""

    error_code: str
    message: str
    retryable: bool = False

    model_config = {"populate_by_name": True}


class ToolResult(BaseModel):
    """工具执行结果摘要；包含采集或解析的帖子列表和状态。"""

    tool_type: Literal["parse_url", "collect"]
    platform: str | None = None
    items: list[SourceItemDTO] = Field(default_factory=list)
    total_found: int = 0
    error: str | None = None

    model_config = {"populate_by_name": True}


class ChatResponsePayload(BaseModel):
    """Agent 最终构造的前端响应载荷；build_response 节点生成，API 层序列化为 SSE 事件。"""

    message_id: str
    message_type: Literal["text", "source_card", "source_list", "tool_status", "error"]
    text_content: str | None = None
    # 结构化内容（source_list / tool_status / error 时使用）
    structured: dict[str, Any] | None = None

    model_config = {"populate_by_name": True}


# ─────────────────────────────────────────────────────────────────────────────
# Document / Version DTO（供 Application Service 和 API 层使用）
# ─────────────────────────────────────────────────────────────────────────────

class SelectionDTO(BaseModel):
    """编辑器文字选区；用于局部润色请求。"""

    from_pos: int = Field(alias="fromPos")
    to_pos: int = Field(alias="toPos")
    text: str  # 当前选中的原始文字（用于后端校验位置是否仍匹配）

    model_config = {"populate_by_name": True}


class InlineRefineRequest(BaseModel):
    """局部润色请求体；前端提交选区、指令和乐观锁版本号。"""

    expected_lock_version: int = Field(alias="expectedLockVersion")
    selection: SelectionDTO
    instruction: str

    model_config = {"populate_by_name": True}


class VersionSummaryDTO(BaseModel):
    """历史版本摘要；版本列表 API 返回，不包含完整 content。"""

    id: str
    version_number: int
    version_type: str
    instruction: str | None = None
    provider: str | None = None
    model: str | None = None
    created_at: datetime

    model_config = {
        "alias_generator": to_camel,
        "populate_by_name": True,
    }


class SourceItemInfoDTO(BaseModel):
    """供文档编辑器渲染使用的帖子元数据摘要。"""

    title: str
    content: str | None = None
    url: str
    platform: str
    author: str | None = None

    model_config = {
        "alias_generator": to_camel,
        "populate_by_name": True,
    }


class DocumentStateDTO(BaseModel):
    """文档当前状态；点击帖子后前端请求的完整状态。"""

    document_id: str
    source_item_id: str
    current_content: str | None = None
    current_version_id: str | None = None
    lock_version: int
    updated_at: datetime
    source_item: SourceItemInfoDTO | None = None

    model_config = {
        "alias_generator": to_camel,
        "populate_by_name": True,
    }

