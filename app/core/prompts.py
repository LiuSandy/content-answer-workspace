"""提示词常量的对外入口；保留原有变量名作为兼容层，实际内容已外置到 app/config/prompts。
单独保留此模块是为了让现有 `from ..core.prompts import XXX` 的调用方零改动，只把数据来源切到 config。"""

from __future__ import annotations

from ..config.loader import load_prompt, load_topic_presets

# 主题提示词预设：dict[str, {"answer_style", "system_prompt"}]
TOPIC_PROMPT_PRESETS = load_topic_presets()

DEFAULT_SYSTEM_PROMPT = load_prompt("default_system")
DEFAULT_ANSWER_STYLE = load_prompt("default_answer_style")
GLOBAL_GENERATION_PROMPT = load_prompt("global_generation")
CONVERSATION_SYSTEM_PROMPT = load_prompt("conversation_system")
