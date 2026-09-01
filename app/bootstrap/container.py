"""Composition root for concrete runtime dependencies."""

from __future__ import annotations

from functools import lru_cache

from app.modules.memory.adapters.embeddings import ExistingEmbeddingAdapter
from app.modules.memory.adapters.db import SQLAlchemyMemoryRepository
from app.modules.memory.adapters.prompts import PromptRegistryMemoryExtractionPrompt
from app.modules.memory.application import MemoryExtractionUseCase
from app.platform.config.llm import load_llm_runtime_config
from app.plugins.llm.gateway import PluginLLMGateway
from app.plugins.llm.providers.deepseek.registration import register_deepseek
from app.plugins.llm.providers.glm.registration import register_glm
from app.plugins.llm.providers.kimi.registration import register_kimi
from app.plugins.llm.providers.minimax.registration import register_minimax
from app.plugins.llm.registry import LLMProviderRegistry
from app.plugins.llm.resolver import LLMResolver
from app.shared.llm.port import LLMGatewayPort


def build_llm_gateway() -> PluginLLMGateway:
    config = load_llm_runtime_config()
    registry = LLMProviderRegistry()
    register_deepseek(registry, config.providers["deepseek"])
    register_kimi(registry, config.providers["kimi"])
    register_minimax(registry, config.providers["minimax"])
    register_glm(registry, config.providers["glm"])
    resolver = LLMResolver(config=config, registry=registry)
    return PluginLLMGateway(resolver=resolver)


@lru_cache(maxsize=1)
def get_llm_gateway() -> LLMGatewayPort:
    """Return the process gateway; tests should inject isolated instances."""

    return build_llm_gateway()


@lru_cache(maxsize=1)
def get_memory_extraction_use_case() -> MemoryExtractionUseCase:
    """Wire the memory extraction vertical slice at the composition root."""

    from app.platform.database.session import get_session_factory
    from app.plugins.embeddings.provider import get_embedding_provider
    from app.platform.prompts.registry import prompt_registry

    return MemoryExtractionUseCase(
        llm=get_llm_gateway(),
        prompts=PromptRegistryMemoryExtractionPrompt(prompt_registry),
        embeddings=ExistingEmbeddingAdapter(get_embedding_provider()),
        repository=SQLAlchemyMemoryRepository(get_session_factory()),
    )
