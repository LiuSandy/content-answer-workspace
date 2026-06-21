from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from app.infrastructure.collectors.xiaohongshu_collector import XiaohongshuCollector
from app.models import Topic, WorkflowConfig
from app.services.xiaohongshu_service import XiaohongshuAccessError

SEARCH_HTML = """
<html><body><script>
window.__INITIAL_STATE__ = {"search":{"feeds":{"feeds":[
  {"id":"note1","noteCard":{"noteId":"note1","displayTitle":"周末徒步路线分享","desc":"摘要"}},
  {"id":"note2","noteCard":{"noteId":"note2","displayTitle":"徒步装备清单","desc":"摘要2"}}
]}}};
</script></body></html>
"""

NOTE1_DETAIL_HTML = """
<html><body><script>
window.__INITIAL_STATE__ = {
  "note":{
    "noteDetailMap":{"note1":{"note":{"title":"周末徒步路线分享","desc":"正文全文","tagList":[]}}},
    "commentsList":{"note1":{"comments":[
      {"id":"c1","content":"这条路线新手能走吗？"},
      {"id":"c2","content":"已收藏"}
    ]}}
  }
};
</script></body></html>
"""

NOTE2_BROKEN_HTML = "<html><body>页面结构异常，没有状态数据</body></html>"

LOGIN_WALL_HTML = "<html><body><div class='login-modal'>手机号登录</div></body></html>"


def _config(content_mode: str) -> WorkflowConfig:
    return WorkflowConfig(
        contentMode=content_mode,
        maxPushCount=10,
        sortModes=["latest"],
        answerStyle="活泼",
        systemPrompt="system",
        generationPrompt="generation",
        testMode=True,
        skipAnswerGeneration=True,
        userAgent="UA",
        ctaText="",
        outputDir="./output",
    )


def _topic() -> Topic:
    return Topic(id="hiking", name="徒步", keywords=["徒步"], expandedHints=["徒步路线"])


class XiaohongshuCollectorTests(unittest.IsolatedAsyncioTestCase):
    """覆盖采集器在两种 content_mode 下的产出，以及登录失效/单笔记解析失败时的处理方式。"""

    async def test_imitate_mode_returns_one_item_per_note_with_full_detail(self) -> None:
        fetch_mock = AsyncMock(side_effect=[SEARCH_HTML, NOTE1_DETAIL_HTML, NOTE2_BROKEN_HTML])
        with patch(
            "app.infrastructure.collectors.xiaohongshu_collector.load_xiaohongshu_cookie",
            return_value="a=1",
        ):
            collector = XiaohongshuCollector(fetcher=AsyncMock(fetch=fetch_mock))
        with patch("app.infrastructure.collectors.xiaohongshu_collector.asyncio.sleep", new=AsyncMock()):
            items = await collector.collect([_topic()], _config("imitate"))

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].content_mode, "imitate")
        self.assertEqual(items[0].detail, "正文全文")
        self.assertEqual(items[0].platform, "xiaohongshu")

    async def test_answer_mode_returns_items_only_for_question_like_comments(self) -> None:
        fetch_mock = AsyncMock(side_effect=[SEARCH_HTML, NOTE1_DETAIL_HTML, NOTE2_BROKEN_HTML])
        with patch(
            "app.infrastructure.collectors.xiaohongshu_collector.load_xiaohongshu_cookie",
            return_value="a=1",
        ):
            collector = XiaohongshuCollector(fetcher=AsyncMock(fetch=fetch_mock))
        with patch("app.infrastructure.collectors.xiaohongshu_collector.asyncio.sleep", new=AsyncMock()):
            items = await collector.collect([_topic()], _config("answer"))

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].content_mode, "answer")
        self.assertEqual(items[0].title, "这条路线新手能走吗？")

    async def test_login_wall_on_search_page_raises_access_error_without_swallowing(self) -> None:
        fetch_mock = AsyncMock(return_value=LOGIN_WALL_HTML)
        with patch(
            "app.infrastructure.collectors.xiaohongshu_collector.load_xiaohongshu_cookie",
            return_value="a=1",
        ):
            collector = XiaohongshuCollector(fetcher=AsyncMock(fetch=fetch_mock))
        with self.assertRaises(XiaohongshuAccessError):
            await collector.collect([_topic()], _config("imitate"))

    async def test_constructor_raises_when_cookie_missing(self) -> None:
        with patch(
            "app.infrastructure.collectors.xiaohongshu_collector.load_xiaohongshu_cookie",
            return_value=None,
        ):
            with self.assertRaises(ValueError):
                XiaohongshuCollector()


if __name__ == "__main__":
    unittest.main()
