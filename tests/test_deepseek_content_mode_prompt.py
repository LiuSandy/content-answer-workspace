from __future__ import annotations

from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

from app.infrastructure.llm.clients.deepseek_client import DeepSeekAnswerGenerator
from app.api.schemas.workflow import QuestionItem
from app.prompts import warmup


def _fake_completion(content: str) -> MagicMock:
    completion = MagicMock()
    completion.choices = [MagicMock(message=MagicMock(content=content))]
    return completion


class DeepSeekContentModePromptTests(unittest.IsolatedAsyncioTestCase):
    """覆盖生成层按 content_mode 选择 prompt 模板；这样小红书仿写不会被误用"回答问题"的话术。"""

    def setUp(self) -> None:
        super().setUp()
        warmup(Path(__file__).resolve().parent.parent / "app" / "agents")

    async def test_generate_answer_uses_imitation_prompt_for_imitate_mode(self) -> None:
        item = QuestionItem(
            id="1",
            platform="xiaohongshu",
            title="周末徒步路线分享",
            url="https://www.xiaohongshu.com/explore/1",
            topic="户外",
            detail="今天走了一条很棒的徒步路线",
            contentMode="imitate",
        )
        generator = DeepSeekAnswerGenerator()
        fake_client = MagicMock()
        fake_client.chat.completions.create.return_value = _fake_completion("生成的笔记")

        with (
            patch.object(generator, "get_client", return_value=fake_client),
            patch("app.infrastructure.llm.clients.deepseek_client.get_required_env", return_value="model-x"),
        ):
            await generator.generate_answer(item, "活泼", "", "system", "generation")

        sent_prompt = fake_client.chat.completions.create.call_args.kwargs["messages"][1]["content"]
        self.assertIn("创作一篇全新的原创笔记", sent_prompt)
        self.assertIn("不要照抄原文内容", sent_prompt)

    async def test_generate_answer_keeps_existing_answer_prompt_by_default(self) -> None:
        item = QuestionItem(id="2", title="知乎问题示例", url="https://www.zhihu.com/question/2", topic="测试")
        generator = DeepSeekAnswerGenerator()
        fake_client = MagicMock()
        fake_client.chat.completions.create.return_value = _fake_completion("生成的回答")

        with (
            patch.object(generator, "get_client", return_value=fake_client),
            patch("app.infrastructure.llm.clients.deepseek_client.get_required_env", return_value="model-x"),
        ):
            await generator.generate_answer(item, "简洁", "", "system", "generation")

        sent_prompt = fake_client.chat.completions.create.call_args.kwargs["messages"][1]["content"]
        self.assertIn("写一篇适合发布到对应平台的原创回答", sent_prompt)

    async def test_polish_answer_uses_imitation_prompt_for_imitate_mode(self) -> None:
        item = QuestionItem(
            id="1",
            platform="xiaohongshu",
            title="周末徒步路线分享",
            url="https://www.xiaohongshu.com/explore/1",
            topic="户外",
            contentMode="imitate",
        )
        generator = DeepSeekAnswerGenerator()
        fake_client = MagicMock()
        fake_client.chat.completions.create.return_value = _fake_completion("润色后的笔记")

        with (
            patch.object(generator, "get_client", return_value=fake_client),
            patch("app.infrastructure.llm.clients.deepseek_client.get_required_env", return_value="model-x"),
        ):
            await generator.polish_answer(item, "草稿内容", "活泼", "", "system", "generation")

        sent_prompt = fake_client.chat.completions.create.call_args.kwargs["messages"][1]["content"]
        self.assertIn("对下面这篇", sent_prompt)
        self.assertIn("笔记进行润色改写", sent_prompt)


if __name__ == "__main__":
    unittest.main()
