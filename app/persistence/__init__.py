"""SQLAlchemy 声明式基类；所有领域模型继承自此，保持一致的元数据注册。"""
from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
