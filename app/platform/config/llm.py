"""Load all LLM routing and connection settings at the composition boundary."""

from __future__ import annotations

import os
import re
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from app.shared.llm.config import LLMRuntimeConfig

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent / "defaults" / "llm.toml"


def load_llm_service_config(name: str, path: Path | None = None) -> dict[str, Any]:
    """Load non-secret service settings (endpoint/model) from ``llm.toml``."""

    config_path = path or DEFAULT_CONFIG_PATH
    with config_path.open("rb") as config_file:
        raw = tomllib.load(config_file)
    services = raw.get("llm", {}).get("services", {})
    value = services.get(name, {})
    return dict(value) if isinstance(value, Mapping) else {}


def update_default_provider_config(*, base_url: str, model: str, path: Path | None = None) -> None:
    """Persist editable endpoint/model values in the default provider TOML block."""

    config_path = path or DEFAULT_CONFIG_PATH
    text = config_path.read_text(encoding="utf-8")
    raw = tomllib.loads(text)
    provider = raw["llm"]["default"]["provider"]
    section = re.compile(
        rf"(\[llm\.providers\.{re.escape(provider)}\][\s\S]*?)(?=\n\[|\Z)"
    )
    match = section.search(text)
    if not match:
        raise ValueError(f"Provider section not found: {provider}")
    block = match.group(1)
    block = re.sub(r'(?m)^base_url\s*=\s*".*"$', f'base_url = "{base_url.rstrip("/")}"', block)
    block = re.sub(r'(?m)^default_model\s*=\s*".*"$', f'default_model = "{model}"', block)
    config_path.write_text(text[: match.start(1)] + block + text[match.end(1) :], encoding="utf-8")


def _with_environment_connections(
    raw: dict[str, Any], environ: Mapping[str, str]
) -> dict[str, Any]:
    """Inject secrets from the environment into the static TOML configuration.

    Provider endpoints, models, and timeouts are deployment configuration and
    therefore live exclusively in ``llm.toml``.  Only API keys are accepted
    from ``.env`` so credentials never need to be committed with the routing
    configuration.
    """
    llm = raw.setdefault("llm", {})
    providers = llm.setdefault("providers", {})
    for key, values in providers.items():
        prefix = key.upper()
        api_key = environ.get(f"{prefix}_API_KEY")
        if api_key is not None:
            values["api_key"] = api_key.strip()
    return raw


def load_llm_runtime_config(
    path: Path | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> LLMRuntimeConfig:
    """Create the single runtime routing object consumed by bootstrap."""

    config_path = path or DEFAULT_CONFIG_PATH
    with config_path.open("rb") as config_file:
        raw = tomllib.load(config_file)
    merged = _with_environment_connections(
        raw, os.environ if environ is None else environ
    )
    return LLMRuntimeConfig.model_validate(merged["llm"])
