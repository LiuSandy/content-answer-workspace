"""Architecture constraints for the v3 provider plugin boundary."""

from pathlib import Path

from app.bootstrap.container import build_llm_gateway
from app.plugins.llm.providers.deepseek.provider import DeepSeekProvider
from app.shared.llm.config import LLMProviderConfig


def test_deepseek_declares_only_supported_structured_methods() -> None:
    provider = DeepSeekProvider(
        LLMProviderConfig(
            api_key="test",
            base_url="https://example.test/v1",
            default_model="deepseek-test",
        )
    )
    assert provider.key == "deepseek"
    assert provider.capabilities.structured_methods == ("json_mode", "generic_parse")


def test_bootstrap_registry_contains_final_provider_set() -> None:
    gateway = build_llm_gateway()
    assert gateway._resolver._registry.keys() == ("deepseek", "kimi", "minimax", "glm")


def test_provider_configuration_does_not_leak_into_business_modules() -> None:
    app_root = Path(__file__).resolve().parent.parent / "app"
    violations = []
    for path in (app_root / "modules").rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        if any(name in source for name in ("DEEPSEEK_", "KIMI_", "MINIMAX_", "GLM_")):
            violations.append(path.relative_to(app_root).as_posix())
    assert violations == []


def test_application_layers_do_not_import_provider_internals() -> None:
    app_root = Path(__file__).resolve().parent.parent / "app"
    forbidden = ("LLMResolver", "LLMProviderRegistry", "AsyncOpenAI", "ChatOpenAI")
    violations = []
    for path in (app_root / "modules").glob("*/application/*.py"):
        source = path.read_text(encoding="utf-8")
        if any(name in source for name in forbidden):
            violations.append(path.relative_to(app_root).as_posix())
    assert violations == []
