from __future__ import annotations

import unittest

from app.config.runtime import get_workflow_config
from app.api.schemas.workflow import QuestionItem, RunPayload


class ContentModeDefaultsTests(unittest.TestCase):
    """覆盖 content_mode 字段的默认值与别名行为；这样知乎现有调用路径不会被新字段意外改变行为。"""

    def test_question_item_defaults_content_mode_to_answer(self) -> None:
        item = QuestionItem(id="1", title="t", url="u", topic="topic")
        self.assertEqual(item.content_mode, "answer")

    def test_question_item_accepts_content_mode_via_camel_case_alias(self) -> None:
        item = QuestionItem(id="1", title="t", url="u", topic="topic", contentMode="imitate")
        self.assertEqual(item.content_mode, "imitate")

    def test_workflow_config_defaults_content_mode_to_answer(self) -> None:
        config = get_workflow_config({})
        self.assertEqual(config.content_mode, "answer")

    def test_workflow_config_respects_content_mode_override(self) -> None:
        config = get_workflow_config({"contentMode": "imitate"})
        self.assertEqual(config.content_mode, "imitate")

    def test_run_payload_exposes_content_mode_via_alias(self) -> None:
        payload = RunPayload.model_validate({"contentMode": "imitate"})
        self.assertEqual(payload.content_mode, "imitate")


if __name__ == "__main__":
    unittest.main()
