from __future__ import annotations

from datetime import datetime

from langchain_core.tools import tool


@tool
def get_current_datetime() -> str:
    """返回当前日期和时间。"""
    return datetime.now().strftime("%Y-%m-%d %H:%M")
