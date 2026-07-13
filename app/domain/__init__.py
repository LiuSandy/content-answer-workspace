"""领域层公开接口；通过此包导入所有 Port 和 DTO，避免直接导入子模块路径。"""
from __future__ import annotations

from .dto import (
    AgentError,
    ChatResponsePayload,
    CollectionRequest,
    DocumentStateDTO,
    InlineRefineRequest,
    LLMMessage,
    LLMRequest,
    LLMResponse,
    LLMStreamEvent,
    ParseUrlRequest,
    SelectionDTO,
    SourceItemDTO,
    ToolContext,
    ToolResult,
    VersionSummaryDTO,
)
from .ports import (
    ApplicationTask,
    ContentSource,
    LLMProvider,
    TaskDispatcher,
    TaskHandle,
    CollectorPort,
    AnswerGeneratorPort,
    TopicExpanderPort,
)

__all__ = [
    # DTOs
    "AgentError",
    "ChatResponsePayload",
    "CollectionRequest",
    "DocumentStateDTO",
    "InlineRefineRequest",
    "LLMMessage",
    "LLMRequest",
    "LLMResponse",
    "LLMStreamEvent",
    "ParseUrlRequest",
    "SelectionDTO",
    "SourceItemDTO",
    "ToolContext",
    "ToolResult",
    "VersionSummaryDTO",
    # Ports
    "ApplicationTask",
    "ContentSource",
    "LLMProvider",
    "TaskDispatcher",
    "TaskHandle",
    "CollectorPort",
    "AnswerGeneratorPort",
    "TopicExpanderPort",
]

