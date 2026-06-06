from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Topic(BaseModel):
    id: str
    name: str
    keywords: list[str] = Field(default_factory=list)
    expanded_hints: list[str] = Field(default_factory=list, alias="expandedHints")

    model_config = {
        "populate_by_name": True,
    }


class WorkflowConfig(BaseModel):
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
    id: str
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
    config: WorkflowConfig
    topics: list[Topic]
    items: list[QuestionItem]


class SessionPayload(BaseModel):
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
    topics: list[Topic] = Field(default_factory=list)
    max_push_count: int | None = Field(default=None, alias="maxPushCount")
    skip_answer_generation: bool | None = Field(default=None, alias="skipAnswerGeneration")
    answer_style: str | None = Field(default=None, alias="answerStyle")
    system_prompt: str | None = Field(default=None, alias="systemPrompt")

    model_config = {
        "populate_by_name": True,
    }


class RegeneratePayload(BaseModel):
    item: QuestionItem
    answer_style: str | None = Field(default=None, alias="answerStyle")
    system_prompt: str | None = Field(default=None, alias="systemPrompt")

    model_config = {
        "populate_by_name": True,
    }


class ZhihuSearchQuestionCore(BaseModel):
    id: str | None = None
    type: str | None = "question"
    name: str | None = None
    title: str | None = None
    url: str | None = None
    answer_count: int | None = None
    follow_count: int | None = None


class ZhihuSearchObject(BaseModel):
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
    type: str | None = None
    highlight: dict[str, Any] | None = None
    object: ZhihuSearchObject | None = None
    index: int | None = None


class ZhihuSearchResponse(BaseModel):
    paging: dict[str, Any] = Field(default_factory=dict)
    data: list[dict[str, Any]] = Field(default_factory=list)
