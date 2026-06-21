from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from langchain_core.messages import AIMessage, HumanMessage

from app.application.agent.nodes.chat import chat_node


class ChatNodeTests(unittest.IsolatedAsyncioTestCase):
    """覆盖对话节点的消息历史转换；这样多轮上下文能正确传给 LLM 并按统一格式追加回复。"""

    async def test_chat_node_converts_history_and_appends_reply(self) -> None:
        state = {
            "messages": [
                HumanMessage(content="帮我想几个选题"),
                AIMessage(content="可以从读者痛点入手"),
                HumanMessage(content="再具体一点"),
            ]
        }

        with patch(
            "app.application.agent.nodes.chat._generator.chat",
            new=AsyncMock(return_value="比如「远程工作如何保持专注」这个角度"),
        ) as mock_chat:
            result = await chat_node(state)

        sent_messages = mock_chat.call_args.args[0]
        self.assertEqual(sent_messages[0]["role"], "system")
        self.assertEqual(sent_messages[1], {"role": "user", "content": "帮我想几个选题"})
        self.assertEqual(sent_messages[2], {"role": "assistant", "content": "可以从读者痛点入手"})
        self.assertEqual(sent_messages[3], {"role": "user", "content": "再具体一点"})
        self.assertEqual(
            result,
            {"messages": [{"role": "assistant", "content": "比如「远程工作如何保持专注」这个角度"}]},
        )


if __name__ == "__main__":
    unittest.main()
