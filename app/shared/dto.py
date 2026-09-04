"""领域层 DTO（Data Transfer Objects）；用于 Agent State、工具契约和跨层数据传递。

所有 DTO 使用 Pydantic v2 定义，不依赖 SQLAlchemy 或任何框架。
"""
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

import uuid
from pydantic import BaseModel, Field
from pydantic.alias_generators import to_camel
from typing_extensions import TypedDict

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


class IntentRoute(BaseModel):
    """意图路由 LLM 判定结果；字段对齐 route_intent 节点消费（spec §4.1）。"""

    intent: Literal["chat", "parse_url", "collect", "task_plan", "multi_agent"] = "chat"
    knowledge_mode: Literal["off", "normal", "strict"] = "normal"
    confidence: float = Field(default=0.9, ge=0.0, le=1.0)
    platform: str | None = None
    query: str | None = None
    limit: int = Field(default=10, ge=1, le=20)
    sort: Literal["relevance", "hot", "latest"] = "relevance"
    reason: str | None = None

    model_config = {"populate_by_name": True}


class QualitySuggestion(BaseModel):
    """单条质检建议；anchor/replacement 支撑片段级逐条采纳（roadmap R3）。"""

    id: str
    dimension: str
    title: str
    reason: str = ""
    # 锚点：原文中要替换的片段（必须与原文逐字一致）；为空表示整体替换
    anchor: str = ""
    # 替换文本：anchor 匹配时替换该片段，否则作为全文替换文本
    replacement: str = ""

    model_config = {
        "alias_generator": to_camel,
        "populate_by_name": True,
    }


QualityDimensionScore = Annotated[int, Field(strict=True, ge=0, le=100)]


class QualityDimensionScores(TypedDict):
    """统一质检的五个必填评分维度。"""

    relevance: QualityDimensionScore
    information_density: QualityDimensionScore
    readability: QualityDimensionScore
    logic_coherence: QualityDimensionScore
    word_count_compliance: QualityDimensionScore


class QualityReport(BaseModel):
    """质检报告；分数统一为 0..100 整数（roadmap R1 接口决定）。

    suggestions 为简短文字建议（R1 契约）；quality_suggestions 为可逐条采纳的
    结构化建议（roadmap R3），含 anchor/replacement 片段级替换信息。
    """

    overall_score: int = Field(strict=True, ge=0, le=100)
    dimension_scores: QualityDimensionScores
    issues: list[dict[str, Any]] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    quality_suggestions: list[QualitySuggestion] = Field(default_factory=list)
    rewrite_instruction: str | None = None
    summary: str = ""

    model_config = {
        "alias_generator": to_camel,
        "populate_by_name": True,
    }


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
    memory_scope: Literal[
        "general",
        "conversation",
        "answer_format",
        "writing_style",
        "audience",
        "platform",
        "source_preference",
        "workflow",
    ] = "general"
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
    outline_operation_id: str | None = None
    content_summary: str
    outline_version_number: int | None = None
    outline_status: str | None = None
    outline_sections: list[dict[str, Any]] = Field(default_factory=list)
    quality_review: dict[str, Any] | None = None
    writing_settings: dict[str, Any] | None = None
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
