"""写作 Prompt 装配器：按目标平台把分层片段拼成最终 system prompt。

单独成模块的原因：装配顺序（通用原则 → 平台包 → 风格规则 → 字数约束）
是内容质量的核心策略，必须只存在一处——此前 answer_generation 与
full_rewrite 各自复制了一份拼接代码且直接访问 Registry 私有属性。

装配结构：
    最终 system prompt =
        通用写作原则（writing.answer_generate 等 base prompt）
      + 平台包（platform.<platform>，未适配平台回退 platform.default）
      + 风格规则尾部（shared.style_rules + 用户自定义追加）
      + 字数约束尾部（shared.word_limit_footer）
"""
from __future__ import annotations

import logging

from .registry import RenderedPrompt, prompt_registry

logger = logging.getLogger(__name__)

# 平台包 Prompt ID 前缀与兜底包
_PLATFORM_PACK_PREFIX = "platform."
_DEFAULT_PACK_ID = "platform.default"


def resolve_platform_pack_id(platform: str | None) -> str:
    """把平台标识解析为平台包 Prompt ID；未适配的平台回退到通用兜底包。"""
    if platform:
        pack_id = f"{_PLATFORM_PACK_PREFIX}{platform.strip().lower()}"
        if prompt_registry.has(pack_id):
            return pack_id
        logger.info("Platform pack %s not found, falling back to default", pack_id)
    return _DEFAULT_PACK_ID


def compose_writing_prompt(
    base_prompt_id: str,
    *,
    platform: str | None = None,
    style_rules: str | None = None,
    word_count: int | None = None,
) -> RenderedPrompt:
    """按平台装配写作 system prompt，返回新的 RenderedPrompt（不修改原对象）。

    调用方拿到结果后自行 extend user messages——user 侧模板与平台无关，
    不属于本装配器的职责。
    """
    rendered = prompt_registry.render(base_prompt_id)

    parts: list[str] = []
    for msg in rendered.messages:
        if msg.role == "system":
            parts.append(msg.content.strip())
            break

    # 平台包：读者画像 / 格式规范 / 结构模式 / 平台雷区
    parts.append(prompt_registry.render_fragment(resolve_platform_pack_id(platform)))

    # 风格规则：共享默认规范 + 用户自定义追加
    base_rules = prompt_registry.render_fragment("shared.style_rules")
    rules = f"{base_rules}\n{style_rules.strip()}" if style_rules and style_rules.strip() else base_rules
    if rules:
        parts.append(prompt_registry.render_fragment("shared.style_rules_footer", rules=rules))

    # 字数约束
    if word_count:
        parts.append(prompt_registry.render_fragment("shared.word_limit_footer", word_count=word_count))

    system_content = "\n\n".join(parts)

    # 不可变组装：构造新的消息列表与 RenderedPrompt，不就地修改 registry 返回值
    new_messages = [
        msg.model_copy(update={"content": system_content}) if msg.role == "system" else msg
        for msg in rendered.messages
    ]
    return RenderedPrompt(
        prompt_id=rendered.prompt_id,
        messages=new_messages,
        model=rendered.model,
        temperature=rendered.temperature,
        max_tokens=rendered.max_tokens,
        provider=rendered.provider,
    )
