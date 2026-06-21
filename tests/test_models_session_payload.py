from __future__ import annotations

import unittest

from app.models import SessionPayload


class SessionPayloadTests(unittest.TestCase):
    """覆盖 SessionPayload 新增的多 session 字段；这样序列化结果能被 session_service 正确按 ID 存取。"""

    def test_round_trips_session_id_title_created_at_by_alias(self) -> None:
        payload = SessionPayload(sessionId="abc123", title="聊聊选题", createdAt="2026-01-01T00:00:00")

        dumped = payload.model_dump(by_alias=True)

        self.assertEqual(dumped["sessionId"], "abc123")
        self.assertEqual(dumped["title"], "聊聊选题")
        self.assertEqual(dumped["createdAt"], "2026-01-01T00:00:00")

    def test_defaults_when_fields_omitted(self) -> None:
        payload = SessionPayload()

        self.assertEqual(payload.session_id, "")
        self.assertEqual(payload.title, "新对话")
        self.assertEqual(payload.created_at, "")


if __name__ == "__main__":
    unittest.main()
