"""数据库会话工厂；提供异步 engine 和 session，所有数据访问层通过此模块获取连接。"""
from __future__ import annotations

import os
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from . import Base  # noqa: F401 – 导入 Base 确保 metadata 在 create_all 前已注册

# 延迟初始化：engine 在第一次调用 get_engine() 时创建，避免模块导入时读取环境变量
_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _build_database_url() -> str:
    """从环境变量构建 asyncpg 连接 URL。"""
    url = os.getenv("DATABASE_URL", "")
    if url:
        # 如果提供的是 postgres:// 或 postgresql:// 格式，统一转为 asyncpg 驱动格式
        return url.replace("postgresql://", "postgresql+asyncpg://", 1).replace(
            "postgres://", "postgresql+asyncpg://", 1
        )
    # 本地 Docker Compose 默认值
    host = os.getenv("DB_HOST", "localhost")
    port = os.getenv("DB_PORT", "5432")
    user = os.getenv("DB_USER", "dev")
    password = os.getenv("DB_PASSWORD", "dev")
    db = os.getenv("DB_NAME", "content_workspace")
    return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{db}"


def get_engine():
    """获取（或懒创建）异步 SQLAlchemy engine。"""
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            _build_database_url(),
            echo=os.getenv("DB_ECHO", "false").lower() == "true",
            pool_size=5,
            max_overflow=10,
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """获取（或懒创建）异步 session 工厂。"""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            get_engine(),
            expire_on_commit=False,
            class_=AsyncSession,
        )
    return _session_factory


def reset_engine() -> None:
    """重置全局 engine 与 session 工厂；仅供测试隔离使用。

    asyncpg engine 会绑定创建时的 event loop，测试各自新建 loop 时
    复用旧 engine 会报 "attached to a different loop"，故需重置。
    """
    global _engine, _session_factory
    _engine = None
    _session_factory = None


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI 依赖注入用 session 生成器；每个请求获得独立 session，请求结束后自动关闭。"""
    factory = get_session_factory()
    async with factory() as session:
        yield session
