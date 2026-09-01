"""Load all LLM routing and connection settings at the composition boundary."""

from __future__ import annotations

import os
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from app.shared.llm.config import LLMRuntimeConfig

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent / "defaults" / "llm.toml"


def _with_environment_connections(
    raw: dict[str, Any], environ: Mapping[str, str]
) -> dict[str, Any]:
    llm = raw.setdefault("llm", {})
    providers = llm.setdefault("providers", {})
    for key, values in providers.items():
        prefix = key.upper()
        api_key = environ.get(f"{prefix}_API_KEY")
        base_url = environ.get(f"{prefix}_BASE_URL")
        timeout = environ.get(f"{prefix}_TIMEOUT_SECONDS")
        if api_key is not None:
            values["api_key"] = api_key.strip()
        if base_url is not None and base_url.strip():
            values["base_url"] = base_url.strip().rstrip("/")
        if timeout is not None and timeout.strip():
            values["timeout_seconds"] = float(timeout)
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
