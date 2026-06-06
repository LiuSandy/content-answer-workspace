from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Topic(BaseModel):
    """表示前端选择的采集主题；定义成模型是为了统一校验主题名称、关键词和前后端字段别名。"""

    id: str
    name: str
    keywords: list[str] = Field(default_factory=list)
    expanded_hints: list[str] = Field(default_factory=list, alias="expandedHints")

    model_config = {
        "populate_by_name": True,
    }


class WorkflowConfig(BaseModel):
    """表示一次工作流运行配置；定义成模型是为了让采集、生成和保存共享同一份规范化参数。"""

    platform: str = "zhihu"
    max_push_count: int = Field(alias="maxPushCount")
    sort_modes: list[str] = Field(alias="sortModes")
    answer_style: str = Field(alias="answerStyle")
    system_prompt: str = Field(alias="systemPrompt")
    test_mode: bool = Field(alias="testMode")
    skip_answer_generation: bool = Field(alias="skipAnswerGeneration")
    user_agent: str = Field(alias="userAgent")
    cta_text: str = Field(alias="ctaText")
    output_dir: str = Field(alias="outputDir")

    model_config = {
        "populate_by_name": True,
    }


class QuestionItem(BaseModel):
    """表示从平台采集到的待回答问题；定义成模型是为了让采集结果和 AI 生成入参保持同构。"""

    id: str
    platform: str = "zhihu"
    title: str
    url: str
    answer_count: int = Field(default=0, alias="answerCount")
    updated_time: str | None = Field(default=None, alias="updatedTime")
    excerpt: str = ""
    detail: str = ""
    topic: str
    answer: str = ""

    model_config = {
        "populate_by_name": True,
    }


class WorkflowResult(BaseModel):
    """表示采集工作流的返回结果；定义成模型是为了把平台、配置、主题和问题列表作为一个整体返回前端。"""

    platform: str = "zhihu"
    config: WorkflowConfig
    topics: list[Topic]
    items: list[QuestionItem]


class SessionPayload(BaseModel):
    """表示前端保存或批量生成时提交的会话数据；定义成模型是为了兼容本地保存和回答生成两个场景。"""

    platform: str = "zhihu"
    saved_at: str | None = Field(default=None, alias="savedAt")
    topics: list[Topic] = Field(default_factory=list)
    answer_style: str = Field(default="", alias="answerStyle")
    system_prompt: str = Field(default="", alias="systemPrompt")
    max_push_count: int | None = Field(default=None, alias="maxPushCount")
    items: list[QuestionItem] = Field(default_factory=list)

    model_config = {
        "populate_by_name": True,
    }


class RunPayload(BaseModel):
    """表示前端发起采集时提交的参数；定义成模型是为了支持平台默认值和主题、生成选项的统一解析。"""

    platform: str = "zhihu"
    topics: list[Topic] = Field(default_factory=list)
    max_push_count: int | None = Field(default=None, alias="maxPushCount")
    skip_answer_generation: bool | None = Field(default=None, alias="skipAnswerGeneration")
    answer_style: str | None = Field(default=None, alias="answerStyle")
    system_prompt: str | None = Field(default=None, alias="systemPrompt")

    model_config = {
        "populate_by_name": True,
    }


class RegeneratePayload(BaseModel):
    """表示前端对单个问题生成回答的请求；定义成模型是为了把目标问题和提示词覆盖项绑定传递。"""

    platform: str = "zhihu"
    item: QuestionItem
    answer_style: str | None = Field(default=None, alias="answerStyle")
    system_prompt: str | None = Field(default=None, alias="systemPrompt")

    model_config = {
        "populate_by_name": True,
    }


class ZhihuSearchQuestionCore(BaseModel):
    """表示知乎搜索结果里的问题核心字段；定义成模型是为了隔离知乎原始响应和内部 QuestionItem。"""

    id: str | None = None
    type: str | None = "question"
    name: str | None = None
    title: str | None = None
    url: str | None = None
    answer_count: int | None = None
    follow_count: int | None = None


class ZhihuSearchObject(BaseModel):
    """表示知乎搜索结果里的内容对象；定义成模型是为了容纳 answer/question 混合返回的数据结构。"""

    id: str | None = None
    type: str | None = None
    title: str | None = None
    description: str | None = None
    excerpt: str | None = None
    url: str | None = None
    created_time: int | None = None
    updated_time: int | None = None
    answer_count: int | None = None
    question: ZhihuSearchQuestionCore | None = None
    content: str | None = None


class ZhihuSearchResultItem(BaseModel):
    """表示知乎搜索列表中的单条原始结果；定义成模型是为了在解析前先固定外部响应的形状。"""

    type: str | None = None
    highlight: dict[str, Any] | None = None
    object: ZhihuSearchObject | None = None
    index: int | None = None


class ZhihuSearchResponse(BaseModel):
    """表示知乎搜索接口响应；定义成模型是为了对分页信息和原始数据列表做最小结构约束。"""

    paging: dict[str, Any] = Field(default_factory=dict)
    data: list[dict[str, Any]] = Field(default_factory=list)
