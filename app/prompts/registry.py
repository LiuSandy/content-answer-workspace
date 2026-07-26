"""Prompt Registry：扫描、注册、渲染 YAML Prompt 文件。

业务代码只通过稳定 ID 调用：
    rendered = prompt_registry.render(
        "refinement.inline_refine",
        selected_text=...,
        instruction=...,
    )
禁止在 Agent Node、Workflow 或 Service 中直接编写长提示词。
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml
from jinja2 import Environment, StrictUndefined, UndefinedError

from ..domain.dto import LLMMessage, LLMRequest
from .errors import (
    PromptDuplicateIdError,
    PromptNotFoundError,
    PromptRenderError,
    PromptVariableMissingError,
)
from .schemas import ModelProfileEntry, PromptSchema

logger = logging.getLogger(__name__)


class RenderedPrompt:
    """Registry.render() 的返回值；包含渲染好的 messages 和合并后的模型参数。"""

    def __init__(
        self,
        prompt_id: str,
        messages: list[LLMMessage],
        model: str,
        temperature: float,
        max_tokens: int,
    ):
        self.prompt_id = prompt_id
        self.messages = messages
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

    def to_llm_request(self) -> LLMRequest:
        return LLMRequest(
            messages=self.messages,
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )


class PromptRegistry:
    """YAML Prompt 注册表。

    启动时调用 load_from_dir() 扫描 prompts/ 目录；
    生产模式下调用 freeze() 禁止热加载。
    """

    def __init__(self) -> None:
        self._prompts: dict[str, PromptSchema] = {}  # id -> schema
        self._sources: dict[str, str] = {}  # id -> file path（用于错误提示）
        self._model_profiles: dict[str, ModelProfileEntry] = {}
        self._frozen = False
        self._jinja = Environment(undefined=StrictUndefined, keep_trailing_newline=True)

    # ── 加载 ──────────────────────────────────────────────────────────────────

    def load_from_dir(self, prompts_dir: Path) -> None:
        """递归扫描目录下所有 .yml/.yaml 文件，注册 Prompt。"""
        if self._frozen:
            logger.warning("PromptRegistry is frozen, skipping reload")
            return

        # 先加载 model_profiles.yml（如果存在）
        profiles_file = prompts_dir / "model_profiles.yml"
        if profiles_file.exists():
            self._load_model_profiles(profiles_file)

        for yml_path in sorted(prompts_dir.rglob("*.yml")):
            if yml_path.name == "model_profiles.yml":
                continue
            try:
                self._load_file(yml_path)
            except Exception as e:  # noqa: BLE001
                logger.error("Failed to load prompt file %s: %s", yml_path, e)
                raise

        logger.info(
            "PromptRegistry loaded %d prompts from %s", len(self._prompts), prompts_dir
        )

    def _load_model_profiles(self, path: Path) -> None:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        profiles = raw.get("model_profiles", {})
        for key, entry in profiles.items():
            self._model_profiles[key] = ModelProfileEntry(**entry)

    def _load_file(self, path: Path) -> None:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return  # 跳过空文件
        schema = PromptSchema.model_validate(raw)
        if schema.id in self._prompts:
            raise PromptDuplicateIdError(schema.id, self._sources[schema.id], str(path))
        self._prompts[schema.id] = schema
        self._sources[schema.id] = str(path)

    def freeze(self) -> None:
        """冻结 Registry；生产模式下启动后调用，禁止再次 load。"""
        self._frozen = True
        logger.info("PromptRegistry frozen with %d prompts", len(self._prompts))

    # ── 查询 ──────────────────────────────────────────────────────────────────

    def get(self, prompt_id: str) -> PromptSchema:
        if prompt_id not in self._prompts:
            raise PromptNotFoundError(prompt_id)
        return self._prompts[prompt_id]

    def has(self, prompt_id: str) -> bool:
        """判断 Prompt 是否已注册；供调用方做兜底选择（如平台包回退 default）。"""
        return prompt_id in self._prompts

    def get_source_path(self, prompt_id: str) -> Path:
        """返回 Prompt 的源 YAML 文件路径；供编辑接口读写文件用。"""
        if prompt_id not in self._sources:
            raise PromptNotFoundError(prompt_id)
        return Path(self._sources[prompt_id])

    def reload(self) -> None:
        """重新从磁盘加载全部 Prompt（编辑保存后调用），完成后恢复冻结状态。"""
        if not self._sources:
            return
        first_source = Path(next(iter(self._sources.values())))
        prompts_dir = first_source.parent.parent
        self._frozen = False
        self._prompts.clear()
        self._sources.clear()
        self.load_from_dir(prompts_dir)
        self.freeze()

    def render_fragment(self, prompt_id: str, **variables: Any) -> str:
        """渲染 content-only 共享片段并返回纯文本。

        这是拼接场景（平台包、风格尾部等）的唯一公开入口——
        业务代码不得访问 _prompts 私有属性自行渲染。
        """
        schema = self.get(prompt_id)
        if schema.content is None:
            raise PromptRenderError(
                f"Prompt '{prompt_id}' has no 'content' field, cannot render as fragment"
            )
        return self._render_str(schema.content, dict(variables), prompt_id).strip()

    def list_ids(self) -> list[str]:
        return sorted(self._prompts.keys())

    # ── 渲染 ──────────────────────────────────────────────────────────────────

    def render(self, prompt_id: str, **variables: Any) -> RenderedPrompt:
        """渲染 Prompt 并返回 RenderedPrompt；使用 Jinja2 StrictUndefined 严格校验变量。"""
        schema = self.get(prompt_id)

        # 校验必填变量
        missing = [v for v in schema.variables.required if v not in variables]
        if missing:
            raise PromptVariableMissingError(prompt_id, missing)

        # 解析 includes：把共享片段渲染后注入 variables
        render_vars = dict(variables)
        for alias, included_id in schema.includes.items():
            included = self.get(included_id)
            if included.content is None:
                raise PromptRenderError(
                    f"Included prompt '{included_id}' has no 'content' field"
                )
            render_vars[alias] = self._render_str(included.content, render_vars, included_id)

        # 渲染 messages
        messages: list[LLMMessage] = []
        for msg in schema.messages:
            content = self._render_str(msg.content, render_vars, prompt_id)
            messages.append(LLMMessage(role=msg.role, content=content))

        # 解析模型参数
        model_str, temperature, max_tokens = self._resolve_model_params(schema)

        return RenderedPrompt(
            prompt_id=prompt_id,
            messages=messages,
            model=model_str,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    def _render_str(self, template: str, variables: dict[str, Any], prompt_id: str) -> str:
        try:
            return self._jinja.from_string(template).render(**variables)
        except UndefinedError as e:
            raise PromptRenderError(f"Prompt '{prompt_id}' render error: {e}") from e

    def _resolve_model_params(
        self, schema: PromptSchema
    ) -> tuple[str, float, int]:
        profile_key = schema.model.profile if schema.model else "default"
        profile = self._model_profiles.get(profile_key)

        # 基础默认值
        model_str = "deepseek-chat"
        temperature = 0.7
        max_tokens = 4096

        if profile:
            model_str = profile.model
            if profile.temperature is not None:
                temperature = profile.temperature
            if profile.max_tokens is not None:
                max_tokens = profile.max_tokens

        # Prompt 级覆盖
        if schema.model:
            if schema.model.temperature is not None:
                temperature = schema.model.temperature
            if schema.model.max_tokens is not None:
                max_tokens = schema.model.max_tokens

        return model_str, temperature, max_tokens


# ── 全局单例 ─────────────────────────────────────────────────────────────────

prompt_registry = PromptRegistry()


def warmup(prompts_dir: Path | None = None, freeze: bool = True) -> None:
    """在服务启动时调用，加载并冻结 Prompt Registry。"""
    if prompts_dir is None:
        # 默认：项目根目录的 prompts/ 目录
        prompts_dir = Path(__file__).resolve().parent.parent.parent / "prompts"
    prompt_registry.load_from_dir(prompts_dir)
    if freeze:
        prompt_registry.freeze()
