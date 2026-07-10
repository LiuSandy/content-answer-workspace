from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver

from app.application.agent.graphs.conversation import build_conversation_graph


class ConversationGraphTests(unittest.IsolatedAsyncioTestCase):
    """覆盖对话 Graph 的多轮历史持久化；这样同一个 thread_id 在多次调用间能正确累积消息。"""

    async def test_history_accumulates_across_invocations_with_same_thread_id(self) -> None:
        checkpointer = InMemorySaver()
        graph = build_conversation_graph(checkpointer)
        config = {"configurable": {"thread_id": "session-1"}}
        fake_llm = _FakeChatModel(["第一句回复", "第二句回复"])

        with patch(
            "app.application.agent.nodes.chat._get_llm",
            return_value=fake_llm,
        ):
            await graph.ainvoke({"messages": [{"role": "user", "content": "你好"}]}, config=config)
            result = await graph.ainvoke({"messages": [{"role": "user", "content": "继续"}]}, config=config)

        self.assertEqual(len(result["messages"]), 4)
        self.assertEqual(result["messages"][-1].content, "第二句回复")

    async def test_different_thread_ids_do_not_share_history(self) -> None:
        checkpointer = InMemorySaver()
        graph = build_conversation_graph(checkpointer)
        fake_llm = _FakeChatModel(["回复", "回复"])

        with patch(
            "app.application.agent.nodes.chat._get_llm",
            return_value=fake_llm,
        ):
            await graph.ainvoke(
                {"messages": [{"role": "user", "content": "会话一"}]},
                config={"configurable": {"thread_id": "session-a"}},
            )
            result_b = await graph.ainvoke(
                {"messages": [{"role": "user", "content": "会话二"}]},
                config={"configurable": {"thread_id": "session-b"}},
            )

        self.assertEqual(len(result_b["messages"]), 2)

class _FakeChatModel:
    def __init__(self, replies: list[str]) -> None:
        self.ainvoke = AsyncMock(side_effect=[AIMessage(content=reply) for reply in replies])


if __name__ == "__main__":
    unittest.main()
