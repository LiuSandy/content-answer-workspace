"""Provider/model routing values produced by the platform config loader."""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class LLMBinding(BaseModel):
    """A provider and optional model selected for one business purpose."""

    provider: str
    model: str | None = None


class LLMProviderConfig(BaseModel):
    """Deployment connection plus the provider's final model fallback."""

    api_key: str = ""
    base_url: str
    default_model: str
    timeout_seconds: float = Field(default=60.0, gt=0)


class LLMRuntimeConfig(BaseModel):
    """Provider connections plus the fallback used when a Prompt has no route."""

    default: LLMBinding
    providers: dict[str, LLMProviderConfig]

    @model_validator(mode="after")
    def validate_bindings(self) -> "LLMRuntimeConfig":
        referenced = {self.default.provider}
        missing = sorted(referenced.difference(self.providers))
        if missing:
            raise ValueError(
                "LLM bindings reference providers without configuration: "
                + ", ".join(missing)
            )
        return self
