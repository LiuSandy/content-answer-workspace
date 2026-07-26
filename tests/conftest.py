"""测试全局夹具。

reset_db_engine 设为 autouse：asyncpg engine 绑定首次创建时的 event loop，
而各测试（TestClient / pytest-asyncio）会各自新建 loop，复用旧 engine 会报
"attached to a different loop"。每个测试前重置全局 engine 保证隔离。
"""
import pytest

from app.persistence.session import reset_engine


@pytest.fixture(autouse=True)
def reset_db_engine():
    reset_engine()
    yield
