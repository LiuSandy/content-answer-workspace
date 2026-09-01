"""Validated domain values produced by memory extraction."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, RootModel, field_validator


class ExtractedMemory(BaseModel):
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
    evidence: str | None = None

    @field_validator("content")
    @classmethod
    def content_must_not_be_blank(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("memory content must not be blank")
        return normalized


class MemoryExtractionBatch(RootModel[list[ExtractedMemory]]):
    """Root-list schema retained because the existing prompt emits a JSON array."""
