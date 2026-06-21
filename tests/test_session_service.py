from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.models import SessionPayload
from app.services.session_service import (
    create_session,
    list_sessions,
    read_latest_session,
    read_session,
    save_session,
    update_session_title,
)


class SessionServiceTests(unittest.TestCase):
    """覆盖多 session 创建/列表/读取/保存；这样对话页面能按 sessionId 切换工作区数据。"""

    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self._sessions_dir = Path(self._tmp_dir.name) / "sessions"
        self._patcher = patch("app.services.session_service.SESSIONS_DIR", self._sessions_dir)
        self._patcher.start()

    def tearDown(self) -> None:
        self._patcher.stop()
        self._tmp_dir.cleanup()

    def test_create_session_returns_new_id_and_default_title(self) -> None:
        session = create_session()

        self.assertTrue(session["sessionId"])
        self.assertEqual(session["title"], "新对话")
        self.assertTrue(session["createdAt"])
        self.assertTrue((self._sessions_dir / f"{session['sessionId']}.json").exists())

    def test_list_sessions_returns_newest_first(self) -> None:
        first = create_session()
        second = create_session()
        # 强制制造可比较的先后顺序，避免同一毫秒时间戳导致测试不稳定
        first_path = self._sessions_dir / f"{first['sessionId']}.json"
        data = json.loads(first_path.read_text("utf-8"))
        data["createdAt"] = "2020-01-01T00:00:00"
        first_path.write_text(json.dumps(data), "utf-8")

        summaries = list_sessions()

        self.assertEqual(summaries[0]["sessionId"], second["sessionId"])
        self.assertEqual(summaries[1]["sessionId"], first["sessionId"])

    def test_read_session_returns_none_for_missing_id(self) -> None:
        self.assertIsNone(read_session("does-not-exist"))

    def test_save_session_writes_to_file_named_by_session_id(self) -> None:
        payload = SessionPayload(sessionId="fixed-id-1", title="我的对话")

        file_path = save_session(payload)

        self.assertTrue(file_path.endswith("fixed-id-1.json"))
        saved = read_session("fixed-id-1")
        assert saved is not None
        self.assertEqual(saved["title"], "我的对话")

    def test_save_session_generates_id_when_missing(self) -> None:
        payload = SessionPayload(title="未指定 ID 的会话")

        file_path = save_session(payload)

        self.assertTrue(Path(file_path).exists())

    def test_read_latest_session_returns_most_recently_created(self) -> None:
        create_session()
        second = create_session()

        latest = read_latest_session()

        assert latest is not None
        self.assertEqual(latest["sessionId"], second["sessionId"])

    def test_read_latest_session_returns_none_when_no_sessions(self) -> None:
        self.assertIsNone(read_latest_session())

    def test_update_session_title_overwrites_existing_title(self) -> None:
        session = create_session()

        update_session_title(session["sessionId"], "帮我想几个选题方向")

        updated = read_session(session["sessionId"])
        assert updated is not None
        self.assertEqual(updated["title"], "帮我想几个选题方向")

    def test_update_session_title_is_noop_for_missing_session(self) -> None:
        update_session_title("does-not-exist", "标题")  # 不应抛出异常


if __name__ == "__main__":
    unittest.main()
