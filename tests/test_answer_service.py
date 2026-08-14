from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from app.api.schemas.workflow import QuestionItem
from app.services.answer_service import generate_answer_with_images


class AnswerServiceTests(unittest.IsolatedAsyncioTestCase):
    """覆盖回答生成服务的降级行为；这样图片链路出问题时不会再把整条回答流程一起打断。"""

    async def test_generate_answer_with_images_falls_back_to_text_when_image_env_missing(self) -> None:
        """验证图片配置缺失时仍返回文字回答；这样用户先用文本工作流时不会被未配置的配图能力阻塞。"""

        item = QuestionItem(
            id="4497183579",
            title="想要搭建一个个人网站需要做哪些准备？",
            url="https://www.zhihu.com/question/4497183579",
            topic="个人网站",
            answerCount=34,
            excerpt="除了网站本身外，还需要做那些工作。",
            detail="除了网站本身外，还需要做那些工作。",
        )

        with (
            patch("app.services.answer_service.generate_answer", new=AsyncMock(return_value="这是一段测试回答")),
            patch(
                "app.services.answer_service._image_generation_service.generate_images_for_answer",
                new=AsyncMock(side_effect=ValueError("Missing required env: IMAGE_API_KEY")),
            ),
        ):
            answer, image_payload = await generate_answer_with_images(item, "简洁", "", "system", "generation")

        self.assertEqual(answer, "这是一段测试回答")
        self.assertEqual(image_payload.get("images"), [])
        self.assertEqual(image_payload.get("imagePrompts"), [])


if __name__ == "__main__":
    unittest.main()
