"""测试全局夹具。

reset_db_engine 设为 autouse：asyncpg engine 绑定首次创建时的 event loop，
而各测试（TestClient / pytest-asyncio）会各自新建 loop，复用旧 engine 会报
"attached to a different loop"。每个测试前重置全局 engine 保证隔离。

reset_prompt_registry 也设为 autouse：多个测试模块会调用 warmup(freeze=False)
加载 prompts，但某个测试可能调 warmup(freeze=True) 冻结 registry，导致后续
测试无法加载新 prompt。每个测试前重置 prompt registry 保证隔离。
"""
import pytest

from app.platform.database.session import reset_engine


@pytest.fixture(autouse=True)
def reset_db_engine():
    reset_engine()
    yield


@pytest.fixture(autouse=True)
def reset_prompt_registry():
    """每个测试前确保 prompt registry 处于可用状态（解冻且已加载）。

    若其他测试已加载并冻结，这里解冻；若已加载未冻结，跳过重复加载避免
    PromptDuplicateIdError；若从未加载，则首次加载。
    """
    from app.platform.prompts.registry import prompt_registry
    if not prompt_registry._prompts:
        # 从未加载，首次 load
        from pathlib import Path
        prompts_dir = Path(__file__).resolve().parent.parent / "app"
        prompt_registry._frozen = False
        prompt_registry.load_from_dir(prompts_dir)
    # 解冻（此 fixture 不再冻结，由需要冻结的测试自行调用 freeze）
    prompt_registry._frozen = False
    yield
