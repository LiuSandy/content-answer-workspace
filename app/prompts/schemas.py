"""Prompt YAML Schema 定义；使用 Pydantic 校验每个 YAML 文件的结构。"""
from __future__ import annotations
from typing import Any, Literal
from pydantic import BaseModel, Field, model_validator


class ModelProfile(BaseModel):
    profile: str = "default"  # 对应 model_profiles YAML 中的 key
    temperature: float | None = None
    max_tokens: int | None = None
    extra: dict[str, Any] = Field(default_factory=dict)
    model_config = {"populate_by_name": True}


class PromptMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str
    model_config = {"populate_by_name": True}


class PromptVariables(BaseModel):
    required: list[str] = Field(default_factory=list)
    optional: list[str] = Field(default_factory=list)
    model_config = {"populate_by_name": True}


class PromptSchema(BaseModel):
    """单个 YAML Prompt 文件的完整 Schema。"""
    id: str
    version: str = "1.0.0"
    description: str = ""
    model: ModelProfile = Field(default_factory=ModelProfile)
    variables: PromptVariables = Field(default_factory=PromptVariables)
    includes: dict[str, str] = Field(default_factory=dict)  # alias -> prompt_id
    messages: list[PromptMessage] = Field(default_factory=list)
    # 共享片段专用：只有 content 字段
    content: str | None = None

    @model_validator(mode="after")
    def check_has_content(self) -> "PromptSchema":
        if not self.messages and self.content is None:
            raise ValueError(f"Prompt '{self.id}' must have either 'messages' or 'content'")
        return self

    model_config = {"populate_by_name": True}


class ModelProfiles(BaseModel):
    """model_profiles.yml 的 Schema。"""
    model_profiles: dict[str, ModelProfileEntry]
    model_config = {"populate_by_name": True}


class ModelProfileEntry(BaseModel):
    provider: str
    model: str
    temperature: float | None = None
    max_tokens: int | None = None
    # 声明结构化输出能力（roadmap R1）：兼容端点不支持原生 json_schema 时不声明它
    structured_methods: list[str] = Field(default_factory=lambda: ["json_mode", "generic_parse"])
    model_config = {"populate_by_name": True}
