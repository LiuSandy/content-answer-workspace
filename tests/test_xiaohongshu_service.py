from __future__ import annotations

import unittest

from app.services.xiaohongshu_service import (
    XiaohongshuAccessError,
    ensure_usable_xiaohongshu_page,
    ensure_xiaohongshu_cookie,
    extract_initial_state,
    is_captcha_challenge_html,
    is_login_wall_html,
    is_question_comment,
    parse_comments_from_state,
    parse_note_detail_from_state,
    parse_note_list_from_search_state,
)


class XiaohongshuCookieTests(unittest.TestCase):
    """覆盖 cookie 缺失时的报错提示；这样配置缺失会被尽早发现，而不是采集到一半才失败。"""

    def test_ensure_xiaohongshu_cookie_raises_with_actionable_message_when_missing(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            ensure_xiaohongshu_cookie(None)
        self.assertIn("XIAOHONGSHU_COOKIE_FILE", str(ctx.exception))

    def test_ensure_xiaohongshu_cookie_accepts_present_cookie(self) -> None:
        ensure_xiaohongshu_cookie("a=1; b=2")  # 不应抛出


class XiaohongshuPageDetectionTests(unittest.TestCase):
    """覆盖登录墙和验证码页的特征识别；这样采集器能区分"账号层面必须终止"和普通解析失败。"""

    def test_detects_login_wall_html(self) -> None:
        html = "<html><body><div class='login-modal'>手机号登录</div></body></html>"
        self.assertTrue(is_login_wall_html(html))

    def test_does_not_flag_normal_note_page_as_login_wall(self) -> None:
        html = "<html><body><div class='note-detail'>正文内容</div></body></html>"
        self.assertFalse(is_login_wall_html(html))

    def test_detects_captcha_challenge_html(self) -> None:
        html = "<html><body><div class='captcha-container'>请向右滑动完成验证</div></body></html>"
        self.assertTrue(is_captcha_challenge_html(html))

    def test_ensure_usable_page_raises_access_error_on_login_wall(self) -> None:
        html = "<html><body><div class='login-modal'>手机号登录</div></body></html>"
        with self.assertRaises(XiaohongshuAccessError):
            ensure_usable_xiaohongshu_page(html)

    def test_ensure_usable_page_passes_for_normal_page(self) -> None:
        html = "<html><body><div class='note-detail'>正文内容</div></body></html>"
        ensure_usable_xiaohongshu_page(html)  # 不应抛出


SEARCH_PAGE_HTML = """
<html><body><script>
window.__INITIAL_STATE__ = {"search":{"feeds":{"feeds":[
  {"id":"note1","noteCard":{"noteId":"note1","displayTitle":"周末徒步路线分享","desc":"今天走了一条很棒的路线"}},
  {"id":"note2","noteCard":{"noteId":"note2","displayTitle":"","desc":"无标题占位"}}
]}}};
</script></body></html>
"""


class XiaohongshuSearchParsingTests(unittest.TestCase):
    """覆盖搜索页 __INITIAL_STATE__ 解析为笔记摘要列表；这样后续详情/评论抓取能拿到稳定的 id 和 url。"""

    def test_extract_initial_state_parses_embedded_json(self) -> None:
        state = extract_initial_state(SEARCH_PAGE_HTML)
        self.assertIn("search", state)

    def test_extract_initial_state_raises_when_marker_missing(self) -> None:
        with self.assertRaises(ValueError):
            extract_initial_state("<html><body>没有任何状态数据</body></html>")

    def test_parse_note_list_skips_entries_without_title(self) -> None:
        state = extract_initial_state(SEARCH_PAGE_HTML)
        notes = parse_note_list_from_search_state(state)
        self.assertEqual([note["id"] for note in notes], ["note1"])
        self.assertEqual(notes[0]["title"], "周末徒步路线分享")
        self.assertEqual(notes[0]["url"], "https://www.xiaohongshu.com/explore/note1")


NOTE_DETAIL_HTML = """
<html><body><script>
window.__INITIAL_STATE__ = {"note":{"noteDetailMap":{"note1":{"note":{
  "title":"周末徒步路线分享",
  "desc":"今天走了一条很棒的徒步路线，沿途风景很好，全程约8公里。",
  "tagList":[{"name":"户外"},{"name":"徒步"}]
}}}}};
</script></body></html>
"""


class XiaohongshuNoteDetailParsingTests(unittest.TestCase):
    """覆盖笔记详情页解析；这样仿写模式能拿到完整正文和标签作为创作参考。"""

    def test_parse_note_detail_extracts_title_detail_and_tags(self) -> None:
        state = extract_initial_state(NOTE_DETAIL_HTML)
        detail = parse_note_detail_from_state(state, "note1")
        self.assertEqual(detail["title"], "周末徒步路线分享")
        self.assertIn("全程约8公里", detail["detail"])
        self.assertEqual(detail["tags"], ["户外", "徒步"])

    def test_parse_note_detail_returns_empty_fields_when_note_id_missing(self) -> None:
        state = extract_initial_state(NOTE_DETAIL_HTML)
        detail = parse_note_detail_from_state(state, "not-exist")
        self.assertEqual(detail["title"], "")
        self.assertEqual(detail["detail"], "")
        self.assertEqual(detail["tags"], [])


NOTE_COMMENTS_HTML = """
<html><body><script>
window.__INITIAL_STATE__ = {"note":{"commentsList":{"note1":{"comments":[
  {"id":"c1","content":"这条路线新手能走吗？"},
  {"id":"c2","content":"风景真好，已收藏"},
  {"id":"c3","content":"装备要怎么准备"}
]}}}};
</script></body></html>
"""


class XiaohongshuCommentParsingTests(unittest.TestCase):
    """覆盖评论区解析和提问识别；这样评论问答模式只挑出真正的疑问而不是所有评论。"""

    def test_parse_comments_returns_all_comments_for_note(self) -> None:
        state = extract_initial_state(NOTE_COMMENTS_HTML)
        comments = parse_comments_from_state(state, "note1")
        self.assertEqual([c["id"] for c in comments], ["c1", "c2", "c3"])

    def test_parse_comments_returns_empty_list_when_note_has_no_comments(self) -> None:
        state = extract_initial_state(NOTE_COMMENTS_HTML)
        self.assertEqual(parse_comments_from_state(state, "not-exist"), [])

    def test_is_question_comment_detects_question_markers(self) -> None:
        self.assertTrue(is_question_comment("这条路线新手能走吗？"))
        self.assertTrue(is_question_comment("装备要怎么准备"))

    def test_is_question_comment_rejects_plain_statement(self) -> None:
        self.assertFalse(is_question_comment("风景真好，已收藏"))


if __name__ == "__main__":
    unittest.main()
