from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.application.agent.nodes.chat_node import _drop_orphaned_tool_messages


def test_drops_legacy_orphaned_platform_tool_message():
    messages = [
        HumanMessage(content="检索知乎问题"),
        ToolMessage(
            content='{"items": []}',
            name="zhihu_search",
            tool_call_id="platform-legacy",
        ),
        AIMessage(content="已从知乎检索到结果。"),
        HumanMessage(content="有没有今年的帖子？"),
    ]

    cleaned, dropped = _drop_orphaned_tool_messages(messages)

    assert dropped == 1
    assert [message.type for message in cleaned] == ["human", "ai", "human"]


def test_preserves_tool_messages_with_matching_assistant_calls():
    messages = [
        HumanMessage(content="搜索"),
        AIMessage(
            content="",
            tool_calls=[
                {"name": "zhihu_search", "args": {}, "id": "call-1", "type": "tool_call"},
                {"name": "web_search", "args": {}, "id": "call-2", "type": "tool_call"},
            ],
        ),
        ToolMessage(content="a", name="zhihu_search", tool_call_id="call-1"),
        ToolMessage(content="b", name="web_search", tool_call_id="call-2"),
        AIMessage(content="结果"),
    ]

    cleaned, dropped = _drop_orphaned_tool_messages(messages)

    assert dropped == 0
    assert cleaned == messages
