"""写作 Prompt 装配器测试：验证平台包选择、分层拼接与不可变组装。"""
from pathlib import Path

import pytest

from app.prompts.composer import compose_writing_prompt, resolve_platform_pack_id
from app.prompts.registry import PromptRegistry, prompt_registry

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "app" / "agents"


@pytest.fixture(autouse=True)
def load_registry():
    """每个测试用未冻结的全新加载，避免与其他测试的 warmup 状态互相干扰。"""
    fresh = PromptRegistry()
    fresh.load_from_dir(PROMPTS_DIR)
    # 替换全局单例内部状态（composer 依赖全局单例）
    prompt_registry._prompts = fresh._prompts
    prompt_registry._model_profiles = fresh._model_profiles
    yield


def test_resolve_platform_pack_known_platforms():
    assert resolve_platform_pack_id("zhihu") == "platform.zhihu"
    assert resolve_platform_pack_id("xiaohongshu") == "platform.xiaohongshu"
    # 大小写与空白归一化
    assert resolve_platform_pack_id(" Zhihu ") == "platform.zhihu"


def test_resolve_platform_pack_fallback():
    assert resolve_platform_pack_id("bilibili") == "platform.default"
    assert resolve_platform_pack_id(None) == "platform.default"
    assert resolve_platform_pack_id("") == "platform.default"


def test_compose_zhihu_prompt_contains_all_layers():
    rendered = compose_writing_prompt(
        "writing.answer_generate",
        platform="zhihu",
        style_rules="多用短句",
        word_count=1500,
    )
    system = rendered.messages[0].content
    # 通用原则层
    assert "创作心智" in system
    # 平台包层：知乎专属内容
    assert "知乎" in system
    assert "结构模式" in system
    # 不应混入其他平台的包
    assert "小红书读者" not in system
    # 风格规则层：默认规范 + 用户自定义
    assert "多用短句" in system
    # 字数约束层
    assert "1500" in system


def test_compose_platforms_produce_different_prompts():
    zhihu = compose_writing_prompt("writing.answer_generate", platform="zhihu")
    xhs = compose_writing_prompt("writing.answer_generate", platform="xiaohongshu")
    assert zhihu.messages[0].content != xhs.messages[0].content
    assert "emoji" in xhs.messages[0].content
    assert "话题标签" in xhs.messages[0].content


def test_compose_is_immutable():
    # 装配不得污染 registry 内部模板：两次装配结果一致
    first = compose_writing_prompt("writing.answer_generate", platform="zhihu")
    second = compose_writing_prompt("writing.answer_generate", platform="zhihu")
    assert first.messages[0].content == second.messages[0].content
    # 原始渲染结果不含平台包内容
    raw = prompt_registry.render("writing.answer_generate")
    assert "目标平台：知乎" not in raw.messages[0].content


def test_compose_without_word_count_omits_limit():
    rendered = compose_writing_prompt("writing.answer_generate", platform="zhihu")
    assert "字数要求" not in rendered.messages[0].content
