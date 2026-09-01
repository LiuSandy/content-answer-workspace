"""Normalized LLM errors visible across the gateway boundary."""


class LLMError(Exception):
    """Base error for normalized LLM failures."""


class LLMConfigurationError(LLMError):
    """Runtime configuration cannot resolve a usable provider/model."""


class LLMProviderNotFoundError(LLMConfigurationError):
    """A purpose references a provider that is not registered."""


class LLMProviderError(LLMError):
    """A provider call failed after vendor-specific errors were normalized."""
