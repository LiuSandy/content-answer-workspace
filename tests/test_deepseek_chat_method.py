from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from app.infrastructure.llm.deepseek_client import DeepSeekAnswerGenerator


def _fake_completion(content: str | None) -> MagicMock:
    completion = MagicMock()
    completion.choices = [MagicMock(message=MagicMock(content=content))]
    return completion


class DeepSeekChatMethodTests(unittest.IsolatedAsyncioTestCase):
    """覆盖多轮对话调用方法；这样对话 Agent 节点能复用同一套 LLM 客户端而不附加业务提示词。"""

    async def test_chat_passes_messages_through_and_returns_content(self) -> None:
        generator = DeepSeekAnswerGenerator()
        fake_client = MagicMock()
        fake_client.chat.completions.create.return_value = _fake_completion("你好，我能帮你梳理选题思路。")

        with (
            patch.object(generator, "get_client", return_value=fake_client),
            patch("app.infrastructure.llm.deepseek_client.get_required_env", return_value="model-x"),
        ):
            messages = [
                {"role": "system", "content": "你是内容策略助手"},
                {"role": "user", "content": "帮我想几个选题"},
            ]
            reply = await generator.chat(messages)

        self.assertEqual(reply, "你好，我能帮你梳理选题思路。")
        fake_client.chat.completions.create.assert_called_once_with(model="model-x", messages=messages)

    async def test_chat_raises_when_content_empty(self) -> None:
        generator = DeepSeekAnswerGenerator()
        fake_client = MagicMock()
        fake_client.chat.completions.create.return_value = _fake_completion(None)

        with (
            patch.object(generator, "get_client", return_value=fake_client),
            patch("app.infrastructure.llm.deepseek_client.get_required_env", return_value="model-x"),
        ):
            with self.assertRaises(ValueError):
                await generator.chat([{"role": "user", "content": "hi"}])


if __name__ == "__main__":
    unittest.main()
