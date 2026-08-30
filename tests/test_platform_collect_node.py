from __future__ import annotations

import json

import pytest


class _FakeSearchTool:
    name = "zhihu_search"

    def __init__(self, result: dict):
        self.result = result
        self.calls: list[dict] = []

    async def ainvoke(self, arguments: dict) -> str:
        self.calls.append(arguments)
        return json.dumps(self.result, ensure_ascii=False)


def _state() -> dict:
    return {
        "intent": "collect",
        "intent_platform": "zhihu",
        "intent_query": "热门",
        "intent_limit": 10,
        "intent_sort": "relevance",
        "messages": [],
    }


def test_explicit_zhihu_query_has_deterministic_platform_route(monkeypatch):
    from app.agents.chat.nodes import platform_collect

    tool = _FakeSearchTool({"platform": "zhihu", "items": []})
    monkeypatch.setattr(platform_collect, "ALL_TOOLS", [tool])

    assert platform_collect.has_platform_search_route(_state()) is True


@pytest.mark.asyncio
async def test_platform_collect_invokes_only_matching_tool_once(monkeypatch):
    from app.agents.chat.nodes import platform_collect

    tool = _FakeSearchTool(
        {
            "platform": "zhihu",
            "topic": "热门",
            "items": [
                {
                    "title": "问题一",
                    "url": "https://www.zhihu.com/question/1",
                    "excerpt": "摘要",
                    "answer_count": 3,
                }
            ],
        }
    )
    monkeypatch.setattr(platform_collect, "ALL_TOOLS", [tool])

    result = await platform_collect.platform_collect_node(_state())

    assert tool.calls == [{"keyword": "热门", "limit": 10, "sort": "relevance"}]
    assert len(result["messages"]) == 1
    assert result["messages"][0].type == "ai"
    assert "检索到 1 条" in result["messages"][0].content
    assert result["platform_collect_result"]["tool_type"] == "zhihu_search"
    assert result["platform_collect_result"]["items"][0]["title"] == "问题一"


@pytest.mark.asyncio
async def test_platform_collect_turns_tool_error_into_terminal_response(monkeypatch):
    from app.agents.chat.nodes import platform_collect

    tool = _FakeSearchTool(
        {
            "platform": "zhihu",
            "error": "ERR_TICKET_NOT_EXIST",
            "error_code": "zhihu_auth_invalid",
            "retryable": False,
            "message": "知乎登录凭据已失效，请更新凭据后重试。",
            "items": [],
        }
    )
    monkeypatch.setattr(platform_collect, "ALL_TOOLS", [tool])

    result = await platform_collect.platform_collect_node(_state())

    assert tool.calls == [{"keyword": "热门", "limit": 10, "sort": "relevance"}]
    assert len(result["messages"]) == 1
    assert result["messages"][0].content == (
        "知乎检索失败：知乎登录凭据已失效，请更新凭据后重试。"
        "（错误码：zhihu_auth_invalid；原因：ERR_TICKET_NOT_EXIST）"
    )


@pytest.mark.asyncio
async def test_platform_collect_exposes_generic_tool_error_reason(monkeypatch):
    from app.agents.chat.nodes import platform_collect

    tool = _FakeSearchTool(
        {
            "platform": "zhihu",
            "error": "浏览器启动失败：未找到 Chromium",
            "error_code": "zhihu_search_failed",
            "retryable": False,
            "message": "知乎检索失败，请稍后重试。",
            "items": [],
        }
    )
    monkeypatch.setattr(platform_collect, "ALL_TOOLS", [tool])

    result = await platform_collect.platform_collect_node(_state())

    assert "错误码：zhihu_search_failed" in result["messages"][0].content
    assert "原因：浏览器启动失败：未找到 Chromium" in result["messages"][0].content


def test_generic_chat_has_no_platform_search_route(monkeypatch):
    from app.agents.chat.nodes import platform_collect

    monkeypatch.setattr(
        platform_collect,
        "ALL_TOOLS",
        [_FakeSearchTool({"platform": "zhihu", "items": []})],
    )

    assert platform_collect.has_platform_search_route(
        {"intent": "chat", "intent_platform": None, "intent_query": "热门"}
    ) is False


@pytest.mark.asyncio
async def test_platform_collect_passes_parsed_limit_and_sort(monkeypatch):
    from app.agents.chat.nodes import platform_collect

    tool = _FakeSearchTool({"platform": "zhihu", "items": []})
    monkeypatch.setattr(platform_collect, "ALL_TOOLS", [tool])
    state = _state()
    state.update(
        {
            "intent_query": "个人网站",
            "intent_limit": 5,
            "intent_sort": "hot",
        }
    )

    await platform_collect.platform_collect_node(state)

    assert tool.calls == [{"keyword": "个人网站", "limit": 5, "sort": "hot"}]
