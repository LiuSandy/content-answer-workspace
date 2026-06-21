from __future__ import annotations

from .calculator import calculator
from .code_interpreter import code_interpreter
from .datetime_tool import get_current_datetime
from .news_search import news_search
from .web_fetch import web_fetch
from .web_search import web_search

ALL_TOOLS = [
    get_current_datetime,
    web_search,
    web_fetch,
    news_search,
    code_interpreter,
    calculator,
]
