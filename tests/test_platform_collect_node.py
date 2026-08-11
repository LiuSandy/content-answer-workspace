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
        "intent": "chat",
        "intent_platform": "zhihu",
        "intent_query": "热门",
        "messages": [],
    }


def test_explicit_zhihu_query_has_deterministic_platform_route(monkeypatch):
    from app.application.agent.nodes import platform_collect

    tool = _FakeSearchTool({"platform": "zhihu", "items": []})
    monkeypatch.setattr(platform_collect, "ALL_TOOLS", [tool])

    assert platform_collect.has_platform_search_route(_state()) is True


@pytest.mark.asyncio
async def test_platform_collect_invokes_only_matching_tool_once(monkeypatch):
    from app.application.agent.nodes import platform_collect

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

    assert tool.calls == [{"keyword": "热门", "limit": 10}]
    assert len(result["messages"]) == 2
    assert result["messages"][0].name == "zhihu_search"
    assert json.loads(result["messages"][0].content)["items"][0]["title"] == "问题一"
    assert "检索到 1 条" in result["messages"][1].content


@pytest.mark.asyncio
async def test_platform_collect_turns_tool_error_into_terminal_response(monkeypatch):
    from app.application.agent.nodes import platform_collect

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

    assert tool.calls == [{"keyword": "热门", "limit": 10}]
    assert len(result["messages"]) == 2
    assert result["messages"][1].content == "知乎检索失败：知乎登录凭据已失效，请更新凭据后重试。"


def test_generic_chat_has_no_platform_search_route(monkeypatch):
    from app.application.agent.nodes import platform_collect

    monkeypatch.setattr(
        platform_collect,
        "ALL_TOOLS",
        [_FakeSearchTool({"platform": "zhihu", "items": []})],
    )

    assert platform_collect.has_platform_search_route(
        {"intent": "chat", "intent_platform": None, "intent_query": "热门"}
    ) is False
