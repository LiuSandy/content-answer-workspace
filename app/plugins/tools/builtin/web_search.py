from __future__ import annotations

import os

from langchain_community.tools import DuckDuckGoSearchRun
from langchain_core.tools import tool

from app.platform.config.runtime import load_env_file
from app.platform.config.loader import get_settings
from app.plugins.sources.zhihu_service import search_zhihu_global

_duckduckgo_search = DuckDuckGoSearchRun(name="web_search_backend")


@tool
async def web_search(
    query: str,
    count: int = 10,
    filter_expression: str = "",
    search_db: str = "all",
) -> str:
    """搜索互联网上与用户问题相关的内容，返回标题、摘要、作者和链接等信息。

    适合查询最新资料、事实信息、行业动态、观点和公开网页内容。

    参数：
    - query：必填，搜索关键词或自然语言查询。
    - count：可选，返回结果数量，默认 10，最大 20。
    - filter_expression：可选，高级筛选表达式。支持按站点和发布时间筛选：
      `host=="example.com"`、`host!="example.com"`；
      `publish_time` 使用秒级 Unix 时间戳，并支持 `==`、`!=`、`>`、`>=`、`<`、`<=`。
      多个条件使用大写 `AND`、`OR` 连接，`AND` 优先级高于 `OR`，可使用括号。
      例如：`host=="example.com" AND publish_time>=1778494631`。
      如果只搜索知乎站内内容，应使用知乎内容搜索能力，不要用 host 条件代替。
    - search_db：可选，内容索引库，取值为 `all`（全部，默认）、`realtime`（实时）
      或 `static`（静态）。
    """

    normalized_query = str(query or "").strip()
    if not normalized_query:
        return "搜索关键词不能为空。"

    sections: list[str] = []
    try:
        duckduckgo_result = await _duckduckgo_search.ainvoke(normalized_query)
        if duckduckgo_result:
            sections.append(f"【DuckDuckGo 全网搜索】\n{duckduckgo_result}")
    except Exception as exc:  # noqa: BLE001 - 保留其他搜索来源可用
        sections.append(f"【DuckDuckGo 全网搜索】\n搜索失败：{exc}")

    load_env_file()
    if os.getenv("ZHIHU_ACCESS_SECRET", "").strip():
        try:
            result = await search_zhihu_global(
                query=normalized_query,
                user_agent=get_settings().http.user_agent,
                count=count,
                filter_expression=filter_expression,
                search_db=search_db,
            )
            items = result.get("items") or []
            zhihu_lines = [
                f"标题：{item['title']}\n"
                f"类型：{item.get('content_type') or '未知'}\n"
                f"摘要：{item.get('excerpt') or ''}\n"
                f"作者：{item.get('author_name') or '知乎用户'}\n"
                f"链接：{item['url']}"
                for item in items
            ]
            if zhihu_lines:
                more = "（还有更多结果）" if result.get("has_more") else ""
                sections.append(
                    f"【知乎全网搜索，共 {len(zhihu_lines)} 条{more}】\n"
                    + "\n\n".join(zhihu_lines)
                )
        except Exception:
            # 知乎是补充来源，不应影响原有 web_search 的可用性；
            # 详细错误由知乎搜索工具边界记录，避免把凭据或内部异常暴露给用户。
            pass

    return "\n\n".join(sections) or "未找到相关搜索结果。"
