"""Provider-neutral LangChain model access."""
from __future__ import annotations

from typing import Any

from .registry import llm_provider_registry


def get_chat_model() -> Any:
    """Return the active provider's reusable, unbound LangChain chat model."""
    return llm_provider_registry.get_langchain_chat_model()
