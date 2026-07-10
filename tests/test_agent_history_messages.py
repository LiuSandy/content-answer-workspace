from __future__ import annotations

import json
import unittest

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.api.routes.agent import _build_history_messages
from app.application.agent.process_steps import tool_end_step, tool_start_step


class AgentHistoryMessageTests(unittest.TestCase):
    def test_collect_tool_result_is_attached_to_final_assistant_message(self) -> None:
        raw_messages = [
            HumanMessage(content="帮我采集个人网站搭建问题"),
            AIMessage(content="", tool_calls=[{"name": "zhihu_search", "args": {"keyword": "个人网站搭建"}, "id": "call-1"}]),
            ToolMessage(
                content=json.dumps(
                    {
                        "platform": "zhihu",
                        "topic": "个人网站搭建",
                        "items": [
                            {"title": "如何自己搭建一个个人网站？", "url": "https://www.zhihu.com/question/1"},
                        ],
                    },
                    ensure_ascii=False,
                ),
                name="zhihu_search",
                tool_call_id="call-1",
            ),
            AIMessage(content="采集完毕，建议先导入新手入门问题。"),
        ]

        messages = _build_history_messages(raw_messages)

        self.assertEqual(messages[0], {"role": "user", "content": "帮我采集个人网站搭建问题"})
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[1]["role"], "assistant")
        self.assertEqual(messages[1]["content"], "采集完毕，建议先导入新手入门问题。")
        self.assertEqual(messages[1]["steps"], [tool_start_step("zhihu_search"), tool_end_step("zhihu_search")])
        self.assertEqual(messages[1]["collectResults"][0]["platform"], "zhihu")
        self.assertEqual(messages[1]["collectResults"][0]["items"][0]["title"], "如何自己搭建一个个人网站？")

    def test_non_collect_tool_steps_remain_as_tool_message(self) -> None:
        raw_messages = [
            HumanMessage(content="现在几点"),
            AIMessage(content="", tool_calls=[{"name": "get_current_datetime", "args": {}, "id": "call-2"}]),
            ToolMessage(content="2026-07-05 22:00", name="get_current_datetime", tool_call_id="call-2"),
            AIMessage(content="现在是 2026-07-05 22:00。"),
        ]

        messages = _build_history_messages(raw_messages)

        self.assertEqual(messages[0]["role"], "user")
        self.assertEqual(messages[1], {
            "role": "tool",
            "content": "",
            "steps": [tool_start_step("get_current_datetime"), tool_end_step("get_current_datetime")],
        })
        self.assertEqual(messages[2], {"role": "assistant", "content": "现在是 2026-07-05 22:00。"})

    def test_collect_result_without_final_text_becomes_empty_assistant_task_message(self) -> None:
        raw_messages = [
            HumanMessage(content="采集知乎问题"),
            ToolMessage(
                content=json.dumps(
                    {
                        "platform": "zhihu",
                        "topic": "个人网站搭建",
                        "items": [{"title": "想要搭建个人网站需要准备什么？"}],
                    },
                    ensure_ascii=False,
                ),
                name="zhihu_search",
                tool_call_id="call-3",
            ),
        ]

        messages = _build_history_messages(raw_messages)

        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[1]["role"], "assistant")
        self.assertEqual(messages[1]["content"], "")
        self.assertEqual(messages[1]["steps"], [tool_end_step("zhihu_search")])
        self.assertEqual(messages[1]["collectResults"][0]["topic"], "个人网站搭建")


if __name__ == "__main__":
    unittest.main()
