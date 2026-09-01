from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from app.modules.acquisition.application.workflow import WorkflowService
from app.modules.acquisition.domain.workflow import ParseQuestionUrlPayload, QuestionItem, Topic
from app.modules.acquisition.application.zhihu import (
    extract_zhihu_question_id,
    extract_zhihu_question_snapshot_from_html,
    extract_zhihu_question_snapshot_from_state,
    fetch_zhihu_question_by_url,
    map_zhihu_question_detail_payload,
)


class ZhihuImportTests(unittest.IsolatedAsyncioTestCase):
    """覆盖知乎问题链接导入的关键场景；这样 URL 导入逻辑收紧后能防止同类 400 再次回归。"""

    def test_extract_zhihu_question_id_supports_standard_question_url(self) -> None:
        """验证标准知乎问题链接能提取问题 id；这样常规 question URL 不会被误判为非法链接。"""

        self.assertEqual(extract_zhihu_question_id("https://www.zhihu.com/question/659910537"), "659910537")

    def test_extract_zhihu_question_id_supports_large_question_id(self) -> None:
        """验证较长问题 id 也能正确提取；这样位数变化不会再次造成导入失败。"""

        self.assertEqual(extract_zhihu_question_id("https://www.zhihu.com/question/4497183579"), "4497183579")

    def test_extract_zhihu_question_id_ignores_query_and_spaces(self) -> None:
        """验证带查询参数和空白的真实浏览器链接也能导入；这样用户直接粘贴地址栏内容依然可用。"""

        self.assertEqual(
            extract_zhihu_question_id("  https://www.zhihu.com/question/4497183579?utm_source=test  "),
            "4497183579",
        )

    async def test_fetch_zhihu_question_by_url_rejects_placeholder_when_detail_parse_fails(self) -> None:
        """验证详情解析失败时不会把兜底标题伪装成成功导入。"""

        fallback_item = QuestionItem(
            id="4497183579",
            title="知乎问题 4497183579",
            url="https://www.zhihu.com/question/4497183579",
            topic="链接导入",
            answerCount=0,
            excerpt="",
            detail="",
        )
        with patch("app.modules.acquisition.application.zhihu.fetch_question_details", new=AsyncMock(return_value=fallback_item)):
            with self.assertRaisesRegex(ValueError, "未能解析知乎问题内容"):
                await fetch_zhihu_question_by_url(
                    "https://www.zhihu.com/question/4497183579",
                    "Mozilla/5.0",
                    "链接导入",
                )

    async def test_fetch_zhihu_question_by_url_accepts_resolved_detail(self) -> None:
        """验证只要补抓到真实标题，链接导入就正常返回问题对象。"""

        resolved_item = QuestionItem(
            id="4497183579",
            title="想要搭建一个个人网站需要做哪些准备？",
            url="https://www.zhihu.com/question/4497183579",
            topic="个人网站 / Web 开发",
            answerCount=34,
            excerpt="除了网站本身外，还需要做那些工作。",
            detail="除了网站本身外，还需要做那些工作。",
        )
        with patch("app.modules.acquisition.application.zhihu.fetch_question_details", new=AsyncMock(return_value=resolved_item)):
            item = await fetch_zhihu_question_by_url(
                "https://www.zhihu.com/question/4497183579",
                "Mozilla/5.0",
                "链接导入",
            )

        self.assertEqual(item.id, "4497183579")
        self.assertEqual(item.title, "想要搭建一个个人网站需要做哪些准备？")
        self.assertEqual(item.topic, "个人网站 / Web 开发")

    def test_map_zhihu_question_detail_payload_extracts_core_fields(self) -> None:
        """验证知乎详情接口字段会被完整映射；这样链接导入能稳定拿到真实标题、摘要、描述和标签。"""

        payload = {
            "title": "想要搭建一个个人网站需要做哪些准备？",
            "excerpt": "除了网站本身外，还需要做那些工作。",
            "detail": "<p>除了网站本身外，还需要做那些工作。</p>",
            "answer_count": 34,
            "updated_time": 1731922644,
            "topics": [{"name": "个人网站"}, {"name": "Web 开发"}],
        }

        snapshot = map_zhihu_question_detail_payload(payload)

        self.assertEqual(snapshot["title"], "想要搭建一个个人网站需要做哪些准备？")
        self.assertEqual(snapshot["excerpt"], "除了网站本身外，还需要做那些工作。")
        self.assertEqual(snapshot["detail"], "除了网站本身外，还需要做那些工作。")
        self.assertEqual(snapshot["answer_count"], 34)
        self.assertEqual(snapshot["topics"], ["个人网站", "Web 开发"])
        self.assertIsNotNone(snapshot["updated_time"])

    def test_map_zhihu_question_detail_payload_supports_camel_case_fields(self) -> None:
        """验证网页端/前端状态常见 camelCase 字段也能映射；这样接口形状变化不会导致导入空内容。"""

        payload = {
            "title": "如何看待 AI 辅助写作？",
            "questionExcerpt": "想了解 AI 写作工具对创作者的影响。",
            "questionDetail": "<p>尤其关注效率、原创性和平台分发。</p>",
            "answerCount": 128,
            "updatedTime": 1731922644,
            "topicList": [{"name": "人工智能"}, {"name": "内容创作"}],
        }

        snapshot = map_zhihu_question_detail_payload(payload)

        self.assertEqual(snapshot["title"], "如何看待 AI 辅助写作？")
        self.assertEqual(snapshot["excerpt"], "想了解 AI 写作工具对创作者的影响。")
        self.assertEqual(snapshot["detail"], "尤其关注效率、原创性和平台分发。")
        self.assertEqual(snapshot["answer_count"], 128)
        self.assertEqual(snapshot["topics"], ["人工智能", "内容创作"])

    def test_extract_zhihu_question_snapshot_from_state_uses_question_id(self) -> None:
        """验证 initialState 中多个 question 实体时会按 URL id 选择目标问题。"""

        state = {
            "initialState": {
                "entities": {
                    "questions": {
                        "1": {"title": "错误问题", "answerCount": 1},
                        "1893036825116922687": {
                            "title": "年轻人应该如何做长期职业规划？",
                            "excerpt": "想知道如何选择行业和能力方向。",
                            "detail": "<p>希望得到可执行建议。</p>",
                            "answerCount": 42,
                            "updatedTime": 1731922644,
                            "topics": [{"name": "职业规划"}, {"name": "年轻人"}],
                        },
                    }
                }
            }
        }

        snapshot = extract_zhihu_question_snapshot_from_state(state, "1893036825116922687")

        self.assertEqual(snapshot["title"], "年轻人应该如何做长期职业规划？")
        self.assertEqual(snapshot["excerpt"], "想知道如何选择行业和能力方向。")
        self.assertEqual(snapshot["detail"], "希望得到可执行建议。")
        self.assertEqual(snapshot["answer_count"], 42)
        self.assertEqual(snapshot["topics"], ["职业规划", "年轻人"])

    def test_extract_zhihu_question_snapshot_from_html_prefers_h1_and_topics(self) -> None:
        """验证 HTML 快照提取会补齐标题、摘要、描述和标签；这样页面兜底解析不只依赖单一 meta 标签。"""

        html = """
        <html>
          <head>
            <meta name="description" content="这是摘要">
            <meta itemprop="dateModified" content="2024-11-18T10:30:44">
          </head>
          <body>
            <h1>想要搭建一个个人网站需要做哪些准备？</h1>
            <script>
              window.__DATA__ = {
                "detail":"<p>除了网站本身外，还需要做那些工作。</p>",
                "answer_count":34,
                "topics":[{"name":"个人网站"},{"name":"前端开发"}]
              };
            </script>
          </body>
        </html>
        """

        snapshot = extract_zhihu_question_snapshot_from_html(html)

        self.assertEqual(snapshot["title"], "想要搭建一个个人网站需要做哪些准备？")
        self.assertEqual(snapshot["excerpt"], "这是摘要")
        self.assertEqual(snapshot["detail"], "除了网站本身外，还需要做那些工作。")
        self.assertEqual(snapshot["answer_count"], 34)
        self.assertEqual(snapshot["topics"], ["个人网站", "前端开发"])
        self.assertIsNotNone(snapshot["updated_time"])

    def test_extract_zhihu_question_snapshot_from_html_reads_js_initial_data(self) -> None:
        """验证知乎 js-initialData 能补出问题核心字段；这是 URL 导入最重要的页面兜底来源。"""

        html = """
        <html>
          <head><title>安全验证 - 知乎</title></head>
          <body>
            <script id="js-initialData" type="text/json">
              {
                "initialState": {
                  "entities": {
                    "questions": {
                      "1893036825116922687": {
                        "title": "如何评价这个职业选择？",
                        "questionExcerpt": "题主希望了解未来发展。",
                        "questionDetail": "<p>补充：更关心长期成长。</p>",
                        "answerCount": 18,
                        "updatedTime": 1731922644,
                        "topics": [{"name": "职业发展"}]
                      }
                    }
                  }
                }
              }
            </script>
          </body>
        </html>
        """

        snapshot = extract_zhihu_question_snapshot_from_html(html, "1893036825116922687")

        self.assertEqual(snapshot["title"], "如何评价这个职业选择？")
        self.assertEqual(snapshot["excerpt"], "题主希望了解未来发展。")
        self.assertEqual(snapshot["detail"], "补充：更关心长期成长。")
        self.assertEqual(snapshot["answer_count"], 18)
        self.assertEqual(snapshot["topics"], ["职业发展"])

    def test_extract_zhihu_question_snapshot_from_html_ignores_security_page(self) -> None:
        """验证知乎安全验证页不会被误识别为真实问题标题。"""

        html = """
        <html>
          <head>
            <title>安全验证 - 知乎</title>
            <meta name="description" content="请您登录后查看更多专业优质内容。">
          </head>
          <body>请您登录后查看更多专业优质内容。</body>
        </html>
        """

        snapshot = extract_zhihu_question_snapshot_from_html(html, "1893036825116922687")

        self.assertIsNone(snapshot["title"])
        self.assertEqual(snapshot["excerpt"], "")
        self.assertEqual(snapshot["detail"], "")

    async def test_parse_question_url_does_not_inherit_selected_topic_name(self) -> None:
        """验证链接导入不会错误继承当前工作区主题；这样导入个人网站问题时不会显示成数据结构与算法。"""

        service = WorkflowService()
        imported_item = QuestionItem(
            id="4497183579",
            title="想要搭建一个个人网站需要做哪些准备？",
            url="https://www.zhihu.com/question/4497183579",
            topic="个人网站 / Web 开发",
            answerCount=34,
            excerpt="除了网站本身外，还需要做那些工作。",
            detail="除了网站本身外，还需要做那些工作。",
        )
        payload = ParseQuestionUrlPayload(
            platform="zhihu",
            url="https://www.zhihu.com/question/4497183579",
            topic=Topic(id="algo", name="数据结构与算法", keywords=["算法"]),
        )

        with patch("app.modules.acquisition.application.workflow.fetch_zhihu_question_by_url", new=AsyncMock(return_value=imported_item)):
            item = await service.parse_question_url(payload)

        self.assertEqual(item.topic, "个人网站 / Web 开发")
        self.assertEqual(item.platform, "zhihu")


if __name__ == "__main__":
    unittest.main()
