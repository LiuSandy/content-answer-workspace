from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock

from app.contracts.dto import LLMResponse
from app.services.llm.answer_generator import AnswerGenerationService


class DeepSeekChatMethodTests(unittest.IsolatedAsyncioTestCase):
    """覆盖多轮对话调用方法；这样对话 Agent 节点能复用同一套 LLM 客户端而不附加业务提示词。"""

    async def test_chat_passes_messages_through_and_returns_content(self) -> None:
        provider = MagicMock()
        provider.default_model = "model-x"
        provider.generate = AsyncMock(
            return_value=LLMResponse(content="你好，我能帮你梳理选题思路。")
        )
        generator = AnswerGenerationService(provider=provider)

        messages = [
            {"role": "system", "content": "你是内容策略助手"},
            {"role": "user", "content": "帮我想几个选题"},
        ]
        reply = await generator.chat(messages)

        self.assertEqual(reply, "你好，我能帮你梳理选题思路。")
        request = provider.generate.await_args.args[0]
        self.assertEqual(request.model, "model-x")
        self.assertEqual([message.model_dump() for message in request.messages], messages)

    async def test_chat_raises_when_content_empty(self) -> None:
        provider = MagicMock()
        provider.default_model = "model-x"
        provider.generate = AsyncMock(return_value=LLMResponse(content=""))
        generator = AnswerGenerationService(provider=provider)

        with self.assertRaises(ValueError):
            await generator.chat([{"role": "user", "content": "hi"}])


if __name__ == "__main__":
    unittest.main()
