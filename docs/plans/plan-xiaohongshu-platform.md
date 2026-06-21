# 小红书平台接入 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增小红书作为第二个采集平台，支持"笔记仿写"和"评论区问答"两种采集模式，并让生成层按模式输出对应文案。

**Architecture:** 新建独立的 `XiaohongshuCollector`（不复用 `UniversalCollector` 的 YAML+HTTP 路径），底层用新建的 `PlaywrightFetcher` 注入 cookie 登录态渲染页面，从页面内嵌的 `window.__INITIAL_STATE__` JSON 中解析笔记列表/详情/评论区；新增跨平台的 `content_mode`（`answer`/`imitate`）字段贯穿数据模型和生成层 prompt 分支；前端复用现有"来源"选择器槛位按平台切换为"内容模式"选择器。

**Tech Stack:** Python 3.11 / FastAPI / Pydantic v2 / httpx / Playwright（新增依赖） / pytest + pytest-asyncio；React + TypeScript / Zustand / TanStack Query。

## Global Constraints

- 知乎现有采集与生成逻辑必须保持行为不变；`content_mode` 默认值为 `"answer"`，未传时所有现有调用路径行为等同于引入此字段之前。
- 新增/修改的 Python 测试遵循项目现有约定：`unittest.IsolatedAsyncioTestCase` + `unittest.mock.AsyncMock`/`MagicMock`，不做真实网络请求、不启动真实浏览器。
- 小红书页面解析（`__INITIAL_STATE__` 字段路径）基于公开资料中常见的小红书前端状态结构编写，真实字段路径需要在拿到真实账号 cookie 后人工跑一次校对；本计划的测试使用人工构造的 HTML 样例验证解析逻辑本身正确，不验证真实页面结构。
- 前端改动后必须执行 `cd frontend && bun run typecheck` 并确认通过（项目里没有配置 JS 单元测试框架，这是前端唯一的自动化验证手段）。
- Pydantic 字段沿用项目既有别名约定：Python 侧 `snake_case` + `alias="camelCase"` + `populate_by_name=True`。
- 修改完成后只报告变更，不要启动前端/后端开发服务器。

---

### Task 1: 数据模型 — content_mode 字段

**Files:**
- Modify: `app/models.py:44-62`（`QuestionItem`）、`app/models.py:23-41`（`WorkflowConfig`）、`app/models.py:92-106`（`RunPayload`）
- Modify: `app/core/config.py:80-126`（`get_workflow_config`）
- Test: `tests/test_content_mode.py`

**Interfaces:**
- Produces: `QuestionItem.content_mode: str`（alias `contentMode`，默认 `"answer"`）；`WorkflowConfig.content_mode: str`（alias `contentMode`，默认 `"answer"`）；`RunPayload.content_mode: str | None`（alias `contentMode`，默认 `None`）；`get_workflow_config(overrides)` 读取 `overrides["contentMode"]`。

- [ ] **Step 1: 写失败的测试**

```python
# tests/test_content_mode.py
from __future__ import annotations

import unittest

from app.core.config import get_workflow_config
from app.models import QuestionItem, RunPayload


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
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_content_mode.py -v`
Expected: FAIL，报 `QuestionItem`/`WorkflowConfig`/`RunPayload` 没有 `content_mode` 属性，或 `get_workflow_config` 返回的对象没有该属性。

- [ ] **Step 3: 实现最小改动**

在 `app/models.py` 的 `QuestionItem` 类里，`image_prompts` 字段之后新增：

```python
    content_mode: str = Field(default="answer", alias="contentMode")
```

在 `WorkflowConfig` 类里，`source` 字段之后新增：

```python
    content_mode: str = Field(default="answer", alias="contentMode")
```

在 `RunPayload` 类里，`generation_prompt` 字段之后新增：

```python
    content_mode: str | None = Field(default=None, alias="contentMode")
```

在 `app/core/config.py` 的 `get_workflow_config` 函数里，`source` 行之后新增：

```python
    content_mode = str(overrides.get("contentMode") or os.getenv("CONTENT_MODE", "answer")).strip().lower()
```

并在函数末尾 `return WorkflowConfig(...)` 调用里，`source=source,` 之后新增一行：

```python
        contentMode=content_mode,
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/test_content_mode.py -v`
Expected: PASS（5 passed）

- [ ] **Step 5: 提交**

```bash
git add app/models.py app/core/config.py tests/test_content_mode.py
git commit -m "feat: add content_mode field for note-imitation vs answer collection modes"
```

---

### Task 2: PlaywrightFetcher（新增依赖 + cookie 注入渲染）

**Files:**
- Modify: `pyproject.toml`（新增 `playwright` 依赖）
- Create: `app/infrastructure/collectors/fetchers/playwright_fetcher.py`
- Test: `tests/test_playwright_fetcher.py`

**Interfaces:**
- Consumes: 无（独立基础设施组件）
- Produces: `parse_cookie_string(cookie_string: str, domain: str) -> list[dict[str, str]]`；`PlaywrightFetcher(cookie_string: str | None = None, cookie_domain: str = "")`，实例方法 `async def fetch(self, url: str, headers: dict[str, str]) -> str`（与现有 `FetcherPort`/`HttpFetcher` 同构，供 `UniversalCollector` 和后续 `XiaohongshuCollector` 复用）。

- [ ] **Step 1: 写失败的测试**

```python
# tests/test_playwright_fetcher.py
from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from app.infrastructure.collectors.fetchers.playwright_fetcher import (
    PlaywrightFetcher,
    parse_cookie_string,
)


class ParseCookieStringTests(unittest.TestCase):
    """覆盖 cookie 字符串转 Playwright cookie 字典的解析逻辑；这样注入登录态时字段格式不会出错。"""

    def test_parses_multiple_cookie_pairs_into_playwright_cookie_dicts(self) -> None:
        result = parse_cookie_string("a=1; b=2", domain=".xiaohongshu.com")
        self.assertEqual(
            result,
            [
                {"name": "a", "value": "1", "domain": ".xiaohongshu.com", "path": "/"},
                {"name": "b", "value": "2", "domain": ".xiaohongshu.com", "path": "/"},
            ],
        )

    def test_skips_malformed_pairs_without_equals_sign(self) -> None:
        result = parse_cookie_string("a=1; malformed; b=2", domain=".xiaohongshu.com")
        self.assertEqual([c["name"] for c in result], ["a", "b"])


class PlaywrightFetcherTests(unittest.IsolatedAsyncioTestCase):
    """覆盖 PlaywrightFetcher 的渲染编排；这样不需要真实浏览器也能验证 cookie 注入和返回值路径。"""

    async def test_fetch_injects_cookies_and_returns_rendered_html(self) -> None:
        fake_page = AsyncMock()
        fake_page.content = AsyncMock(return_value="<html>rendered</html>")
        fake_context = AsyncMock()
        fake_context.new_page = AsyncMock(return_value=fake_page)
        fake_browser = AsyncMock()
        fake_browser.new_context = AsyncMock(return_value=fake_context)
        fake_chromium = AsyncMock()
        fake_chromium.launch = AsyncMock(return_value=fake_browser)
        fake_playwright_instance = MagicMock()
        fake_playwright_instance.chromium = fake_chromium

        fake_playwright_cm = AsyncMock()
        fake_playwright_cm.__aenter__ = AsyncMock(return_value=fake_playwright_instance)
        fake_playwright_cm.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "app.infrastructure.collectors.fetchers.playwright_fetcher.async_playwright",
            return_value=fake_playwright_cm,
        ):
            fetcher = PlaywrightFetcher(cookie_string="a=1", cookie_domain=".xiaohongshu.com")
            html = await fetcher.fetch(
                "https://www.xiaohongshu.com/search_result?keyword=test", {"User-Agent": "UA"}
            )

        self.assertEqual(html, "<html>rendered</html>")
        fake_context.add_cookies.assert_awaited_once_with(
            [{"name": "a", "value": "1", "domain": ".xiaohongshu.com", "path": "/"}]
        )
        fake_browser.close.assert_awaited_once()

    async def test_fetch_skips_cookie_injection_when_no_cookie_configured(self) -> None:
        fake_page = AsyncMock()
        fake_page.content = AsyncMock(return_value="<html>no-cookie</html>")
        fake_context = AsyncMock()
        fake_context.new_page = AsyncMock(return_value=fake_page)
        fake_browser = AsyncMock()
        fake_browser.new_context = AsyncMock(return_value=fake_context)
        fake_chromium = AsyncMock()
        fake_chromium.launch = AsyncMock(return_value=fake_browser)
        fake_playwright_instance = MagicMock()
        fake_playwright_instance.chromium = fake_chromium

        fake_playwright_cm = AsyncMock()
        fake_playwright_cm.__aenter__ = AsyncMock(return_value=fake_playwright_instance)
        fake_playwright_cm.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "app.infrastructure.collectors.fetchers.playwright_fetcher.async_playwright",
            return_value=fake_playwright_cm,
        ):
            fetcher = PlaywrightFetcher()
            await fetcher.fetch("https://example.com", {"User-Agent": "UA"})

        fake_context.add_cookies.assert_not_called()


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_playwright_fetcher.py -v`
Expected: FAIL，报 `ModuleNotFoundError: No module named 'app.infrastructure.collectors.fetchers.playwright_fetcher'`

- [ ] **Step 3: 添加依赖并实现**

在 `pyproject.toml` 的 `dependencies` 列表里，`"beautifulsoup4>=4.12",` 之后新增一行：

```toml
  "playwright>=1.48.0",
```

运行 `uv sync` 安装 Python 包（此时**不需要**执行 `playwright install chromium`，因为本任务的测试全部 mock 了浏览器调用，不会真正启动 Chromium；只有后续真实联调采集时才需要安装浏览器二进制）。

创建 `app/infrastructure/collectors/fetchers/playwright_fetcher.py`：

```python
from __future__ import annotations

from playwright.async_api import async_playwright


def parse_cookie_string(cookie_string: str, domain: str) -> list[dict[str, str]]:
    """把 `a=1; b=2` 形式的 cookie 字符串转成 Playwright 需要的 cookie 字典列表。"""

    cookies: list[dict[str, str]] = []
    for pair in cookie_string.split(";"):
        if "=" not in pair:
            continue
        name, _, value = pair.strip().partition("=")
        name = name.strip()
        value = value.strip()
        if not name:
            continue
        cookies.append({"name": name, "value": value, "domain": domain, "path": "/"})
    return cookies


class PlaywrightFetcher:
    """使用 Playwright 渲染页面获取最终 DOM HTML；负责 Cookie 注入和等待页面渲染完成。"""

    def __init__(self, cookie_string: str | None = None, cookie_domain: str = "") -> None:
        self._cookie_string = cookie_string
        self._cookie_domain = cookie_domain

    async def fetch(self, url: str, headers: dict[str, str]) -> str:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            try:
                context = await browser.new_context(user_agent=headers.get("User-Agent"))
                if self._cookie_string and self._cookie_domain:
                    await context.add_cookies(parse_cookie_string(self._cookie_string, self._cookie_domain))
                page = await context.new_page()
                await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                await page.wait_for_timeout(2_000)
                return await page.content()
            finally:
                await browser.close()
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/test_playwright_fetcher.py -v`
Expected: PASS（4 passed）

- [ ] **Step 5: 提交**

```bash
git add pyproject.toml uv.lock app/infrastructure/collectors/fetchers/playwright_fetcher.py tests/test_playwright_fetcher.py
git commit -m "feat: add PlaywrightFetcher with cookie injection for JS-rendered platforms"
```

---

### Task 3: 小红书 cookie 加载与登录态/风控检测

**Files:**
- Modify: `app/core/config.py:16`（新增 `XIAOHONGSHU_COOKIE_PATH_DEFAULT` 常量）
- Modify: `.env.example`（新增 `XIAOHONGSHU_COOKIE_FILE` 示例项）
- Create: `app/services/xiaohongshu_service.py`
- Test: `tests/test_xiaohongshu_service.py`

**Interfaces:**
- Consumes: `app.core.config.COOKIE_PATH_DEFAULT` 同级新增的 `XIAOHONGSHU_COOKIE_PATH_DEFAULT`；`app.services.zhihu_service.clean_text`（复用现成的 HTML/空白清理函数）。
- Produces: `class XiaohongshuAccessError(RuntimeError)`；`load_xiaohongshu_cookie() -> str | None`；`ensure_xiaohongshu_cookie(cookie: str | None) -> None`；`is_login_wall_html(html: str) -> bool`；`is_captcha_challenge_html(html: str) -> bool`；`ensure_usable_xiaohongshu_page(html: str) -> None`（供 Task 7 的 collector 调用，登录失效/风控时抛 `XiaohongshuAccessError`）。

- [ ] **Step 1: 写失败的测试**

```python
# tests/test_xiaohongshu_service.py
from __future__ import annotations

import unittest

from app.services.xiaohongshu_service import (
    XiaohongshuAccessError,
    ensure_usable_xiaohongshu_page,
    ensure_xiaohongshu_cookie,
    is_captcha_challenge_html,
    is_login_wall_html,
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


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_xiaohongshu_service.py -v`
Expected: FAIL，报 `ModuleNotFoundError: No module named 'app.services.xiaohongshu_service'`

- [ ] **Step 3: 实现**

在 `app/core/config.py` 里，`COOKIE_PATH_DEFAULT` 常量行之后新增：

```python
XIAOHONGSHU_COOKIE_PATH_DEFAULT = ROOT_DIR / ".secrets" / "xiaohongshu.cookie"
```

在 `.env.example` 里 `ZHIHU_COOKIE_FILE` 那一行附近新增：

```
XIAOHONGSHU_COOKIE_FILE=.secrets/xiaohongshu.cookie
```

创建 `app/services/xiaohongshu_service.py`：

```python
from __future__ import annotations

import os
from pathlib import Path

from ..core.config import XIAOHONGSHU_COOKIE_PATH_DEFAULT
from .zhihu_service import clean_text, read_optional_file


class XiaohongshuAccessError(RuntimeError):
    """小红书登录态失效或被风控拦截时抛出；这样调用方能区分"内容解析失败可降级跳过"和"账号层面必须终止"两类错误。"""


def load_xiaohongshu_cookie() -> str | None:
    """加载小红书 cookie 内容；这样所有小红书请求都能复用统一的凭据读取规则。"""

    configured = os.getenv("XIAOHONGSHU_COOKIE_FILE", "").strip()
    cookie_path = Path(configured).resolve() if configured else XIAOHONGSHU_COOKIE_PATH_DEFAULT
    content = read_optional_file(cookie_path)
    return content.strip() if content else None


def ensure_xiaohongshu_cookie(cookie: str | None) -> None:
    """校验小红书采集凭据；这样缺少 cookie 时会返回可理解错误，而不是继续触发空结果或风控误判。"""

    if not cookie:
        raise ValueError(
            "小红书采集需要已登录账号的 Cookie；当前缺少：XIAOHONGSHU_COOKIE_FILE。"
            "请登录小红书网页版后导出 cookie 到对应文件路径，并在 .env 中配置该路径后重启后端。"
        )


_LOGIN_WALL_MARKERS = ("login-modal", "手机号登录", "扫码登录", "请先登录")
_CAPTCHA_MARKERS = ("captcha", "验证码", "向右滑动", "滑动验证")


def is_login_wall_html(html: str) -> bool:
    """识别页面是否落在登录墙；这样登录态失效时能及时报错而不是误判为"没搜到内容"。"""

    return any(marker in html for marker in _LOGIN_WALL_MARKERS)


def is_captcha_challenge_html(html: str) -> bool:
    """识别页面是否触发验证码风控；这样不会把验证码页面内容误喂给后续解析逻辑。"""

    return any(marker.lower() in html.lower() for marker in _CAPTCHA_MARKERS)


def ensure_usable_xiaohongshu_page(html: str) -> None:
    """校验页面是否可用于后续解析；登录失效或风控拦截时抛出需要终止整次采集的错误。"""

    if is_login_wall_html(html):
        raise XiaohongshuAccessError(
            "小红书登录态已失效，请重新导出 cookie 并更新 XIAOHONGSHU_COOKIE_FILE 指向的文件"
        )
    if is_captcha_challenge_html(html):
        raise XiaohongshuAccessError("小红书触发了验证码风控拦截，请降低采集频率或更换账号后重试")


__all__ = [
    "XiaohongshuAccessError",
    "load_xiaohongshu_cookie",
    "ensure_xiaohongshu_cookie",
    "is_login_wall_html",
    "is_captcha_challenge_html",
    "ensure_usable_xiaohongshu_page",
    "clean_text",
]
```

注意：`clean_text` 和 `read_optional_file` 直接从 `zhihu_service.py` 导入复用（它们是通用的 HTML/空白清理和可选文件读取工具，不是知乎专属逻辑），避免重复实现；`__all__` 里重新导出 `clean_text` 是为了后续 Task 4-6 可以从 `xiaohongshu_service` 模块统一导入，不用同时导入两个 service 模块。

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/test_xiaohongshu_service.py -v`
Expected: PASS（6 passed）

- [ ] **Step 5: 提交**

```bash
git add app/core/config.py .env.example app/services/xiaohongshu_service.py tests/test_xiaohongshu_service.py
git commit -m "feat: add xiaohongshu cookie loading and login/captcha wall detection"
```

---

### Task 4: 小红书笔记列表解析（搜索页 → 笔记摘要）

**Files:**
- Modify: `app/services/xiaohongshu_service.py`
- Modify: `tests/test_xiaohongshu_service.py`

**Interfaces:**
- Consumes: 无新依赖
- Produces: `extract_initial_state(html: str) -> dict`；`parse_note_list_from_search_state(state: dict) -> list[dict[str, str]]`（每条包含 `id`/`title`/`excerpt`/`url`）。

- [ ] **Step 1: 写失败的测试**

在 `tests/test_xiaohongshu_service.py` 末尾（`if __name__ == "__main__":` 之前）新增：

```python
from app.services.xiaohongshu_service import (
    extract_initial_state,
    parse_note_list_from_search_state,
)

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
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_xiaohongshu_service.py -v -k Search`
Expected: FAIL，报 `extract_initial_state`/`parse_note_list_from_search_state` 未定义

- [ ] **Step 3: 实现**

在 `app/services/xiaohongshu_service.py` 顶部新增 `import json` 和 `import re`，并在 `ensure_usable_xiaohongshu_page` 函数之后追加：

```python
def extract_initial_state(html: str) -> dict:
    """从小红书页面 HTML 中提取 window.__INITIAL_STATE__ 注入的前端状态 JSON。"""

    match = re.search(r"window\.__INITIAL_STATE__\s*=\s*(\{.*?\})\s*;?\s*</script>", html, re.S)
    if not match:
        raise ValueError("未能在页面中找到 __INITIAL_STATE__ 数据，页面结构可能已变化或被风控拦截")
    raw = match.group(1).replace("undefined", "null")
    return json.loads(raw)


def parse_note_list_from_search_state(state: dict) -> list[dict[str, str]]:
    """从搜索页状态中解析笔记摘要列表；跳过缺少 id 或标题的异常条目。"""

    feeds = state.get("search", {}).get("feeds", {}).get("feeds", [])
    notes: list[dict[str, str]] = []
    for feed in feeds:
        note_card = feed.get("noteCard") if isinstance(feed, dict) else None
        if not isinstance(note_card, dict):
            continue
        note_id = feed.get("id") or note_card.get("noteId")
        title = clean_text(note_card.get("displayTitle") or "")
        if not note_id or not title:
            continue
        notes.append(
            {
                "id": str(note_id),
                "title": title,
                "excerpt": clean_text(note_card.get("desc") or ""),
                "url": f"https://www.xiaohongshu.com/explore/{note_id}",
            }
        )
    return notes
```

同时把这两个函数名加入文件末尾的 `__all__` 列表。

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/test_xiaohongshu_service.py -v`
Expected: PASS（全部用例通过，包含本任务新增的 3 条）

- [ ] **Step 5: 提交**

```bash
git add app/services/xiaohongshu_service.py tests/test_xiaohongshu_service.py
git commit -m "feat: parse xiaohongshu search result note list from embedded initial state"
```

---

### Task 5: 小红书笔记详情解析（笔记正文，供仿写模式使用）

**Files:**
- Modify: `app/services/xiaohongshu_service.py`
- Modify: `tests/test_xiaohongshu_service.py`

**Interfaces:**
- Consumes: `extract_initial_state`（Task 4）
- Produces: `parse_note_detail_from_state(state: dict, note_id: str) -> dict[str, object]`（包含 `title`/`detail`/`tags`）

- [ ] **Step 1: 写失败的测试**

在 `tests/test_xiaohongshu_service.py` 中新增：

```python
from app.services.xiaohongshu_service import parse_note_detail_from_state

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
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_xiaohongshu_service.py -v -k NoteDetail`
Expected: FAIL，报 `parse_note_detail_from_state` 未定义

- [ ] **Step 3: 实现**

在 `app/services/xiaohongshu_service.py` 的 `parse_note_list_from_search_state` 函数之后追加：

```python
def parse_note_detail_from_state(state: dict, note_id: str) -> dict[str, object]:
    """从笔记详情页状态中解析正文全文和标签；note_id 找不到时返回空字段而不是抛错。"""

    note_detail_map = state.get("note", {}).get("noteDetailMap", {})
    entry = note_detail_map.get(note_id, {})
    note = entry.get("note", {}) if isinstance(entry, dict) else {}
    tags = [
        clean_text(tag.get("name") or "")
        for tag in note.get("tagList", [])
        if isinstance(tag, dict) and clean_text(tag.get("name") or "")
    ]
    return {
        "title": clean_text(note.get("title") or ""),
        "detail": clean_text(note.get("desc") or ""),
        "tags": tags,
    }
```

并把 `parse_note_detail_from_state` 加入 `__all__`。

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/test_xiaohongshu_service.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add app/services/xiaohongshu_service.py tests/test_xiaohongshu_service.py
git commit -m "feat: parse xiaohongshu note detail body and tags for imitation mode"
```

---

### Task 6: 小红书评论区解析与提问识别（供评论问答模式使用）

**Files:**
- Modify: `app/services/xiaohongshu_service.py`
- Modify: `tests/test_xiaohongshu_service.py`

**Interfaces:**
- Consumes: `extract_initial_state`（Task 4）
- Produces: `parse_comments_from_state(state: dict, note_id: str) -> list[dict[str, str]]`；`is_question_comment(content: str) -> bool`

- [ ] **Step 1: 写失败的测试**

```python
from app.services.xiaohongshu_service import is_question_comment, parse_comments_from_state

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
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_xiaohongshu_service.py -v -k Comment`
Expected: FAIL，报 `parse_comments_from_state`/`is_question_comment` 未定义

- [ ] **Step 3: 实现**

在 `app/services/xiaohongshu_service.py` 的 `parse_note_detail_from_state` 函数之后追加：

```python
_QUESTION_MARKERS = ("吗", "？", "?", "怎么", "如何", "求", "请问")


def parse_comments_from_state(state: dict, note_id: str) -> list[dict[str, str]]:
    """从笔记评论区状态中解析评论列表；缺少有效内容或 id 的评论会被跳过。"""

    comments_list = state.get("note", {}).get("commentsList", {})
    entry = comments_list.get(note_id, {})
    raw_comments = entry.get("comments", []) if isinstance(entry, dict) else []
    parsed: list[dict[str, str]] = []
    for comment in raw_comments:
        if not isinstance(comment, dict):
            continue
        content = clean_text(comment.get("content") or "")
        comment_id = comment.get("id")
        if not content or not comment_id:
            continue
        parsed.append({"id": str(comment_id), "content": content})
    return parsed


def is_question_comment(content: str) -> bool:
    """判断评论是否是提问；这样评论区抓取只挑出真正的疑问，不是所有评论都当成问题。"""

    return any(marker in content for marker in _QUESTION_MARKERS)
```

并把 `parse_comments_from_state`、`is_question_comment` 加入 `__all__`。

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/test_xiaohongshu_service.py -v`
Expected: PASS（全部用例）

- [ ] **Step 5: 提交**

```bash
git add app/services/xiaohongshu_service.py tests/test_xiaohongshu_service.py
git commit -m "feat: parse xiaohongshu note comments and detect question-like comments"
```

---

### Task 7: XiaohongshuCollector 编排 + 工厂注册

**Files:**
- Create: `app/infrastructure/collectors/xiaohongshu_collector.py`
- Modify: `app/infrastructure/collectors/factory.py:20-23`
- Test: `tests/test_xiaohongshu_collector.py`

**Interfaces:**
- Consumes: `PlaywrightFetcher`（Task 2）；`load_xiaohongshu_cookie`、`ensure_xiaohongshu_cookie`、`ensure_usable_xiaohongshu_page`、`XiaohongshuAccessError`、`extract_initial_state`、`parse_note_list_from_search_state`、`parse_note_detail_from_state`、`parse_comments_from_state`、`is_question_comment`（Task 3-6）；`CollectorPort`（`app/domain/ports.py`）
- Produces: `class XiaohongshuCollector(CollectorPort)`，`platform = "xiaohongshu"`，`async def collect(self, topics, config) -> list[QuestionItem]`；`CollectorFactory._collectors["xiaohongshu"] = XiaohongshuCollector`

- [ ] **Step 1: 写失败的测试**

```python
# tests/test_xiaohongshu_collector.py
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
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_xiaohongshu_collector.py -v`
Expected: FAIL，报 `ModuleNotFoundError: No module named 'app.infrastructure.collectors.xiaohongshu_collector'`

- [ ] **Step 3: 实现**

创建 `app/infrastructure/collectors/xiaohongshu_collector.py`：

```python
from __future__ import annotations

import asyncio
from typing import Sequence

from ...domain.ports import CollectorPort
from ...models import QuestionItem, Topic, WorkflowConfig
from ...services.xiaohongshu_service import (
    ensure_usable_xiaohongshu_page,
    ensure_xiaohongshu_cookie,
    extract_initial_state,
    is_question_comment,
    load_xiaohongshu_cookie,
    parse_comments_from_state,
    parse_note_detail_from_state,
    parse_note_list_from_search_state,
)
from .fetchers.playwright_fetcher import PlaywrightFetcher

XIAOHONGSHU_COOKIE_DOMAIN = ".xiaohongshu.com"
REQUEST_INTERVAL_SECONDS = 1.5


class XiaohongshuCollector(CollectorPort):
    """实现小红书平台采集策略；按 content_mode 产出笔记仿写素材或评论区问答素材。"""

    platform = "xiaohongshu"

    def __init__(self, fetcher: PlaywrightFetcher | None = None) -> None:
        cookie = load_xiaohongshu_cookie()
        ensure_xiaohongshu_cookie(cookie)
        self._fetcher = fetcher or PlaywrightFetcher(cookie_string=cookie, cookie_domain=XIAOHONGSHU_COOKIE_DOMAIN)

    async def collect(self, topics: Sequence[Topic], config: WorkflowConfig) -> list[QuestionItem]:
        """按主题和关键词采集小红书内容；这样一次调用能覆盖多个主题扩展出的检索词。"""

        items: list[QuestionItem] = []
        for topic in topics:
            keywords = topic.expanded_hints or topic.keywords or [topic.name]
            for keyword in keywords:
                items.extend(await self._collect_for_keyword(topic, keyword, config))
                await asyncio.sleep(REQUEST_INTERVAL_SECONDS)
        return items

    async def _collect_for_keyword(
        self, topic: Topic, keyword: str, config: WorkflowConfig
    ) -> list[QuestionItem]:
        search_url = f"https://www.xiaohongshu.com/search_result?keyword={keyword}"
        html = await self._fetcher.fetch(search_url, {"User-Agent": config.user_agent})
        ensure_usable_xiaohongshu_page(html)
        state = extract_initial_state(html)
        notes = parse_note_list_from_search_state(state)

        results: list[QuestionItem] = []
        for note in notes:
            try:
                results.extend(await self._collect_for_note(topic, note, config))
            except ValueError:
                continue
        return results

    async def _collect_for_note(
        self, topic: Topic, note: dict[str, str], config: WorkflowConfig
    ) -> list[QuestionItem]:
        detail_html = await self._fetcher.fetch(note["url"], {"User-Agent": config.user_agent})
        ensure_usable_xiaohongshu_page(detail_html)
        state = extract_initial_state(detail_html)
        detail = parse_note_detail_from_state(state, note["id"])

        if config.content_mode == "imitate":
            return [
                QuestionItem(
                    id=note["id"],
                    platform=self.platform,
                    title=detail.get("title") or note["title"],
                    url=note["url"],
                    excerpt=note.get("excerpt", ""),
                    detail=str(detail.get("detail", "")),
                    topic=topic.name,
                    contentMode="imitate",
                )
            ]

        comments = parse_comments_from_state(state, note["id"])
        results: list[QuestionItem] = []
        for comment in comments:
            if not is_question_comment(comment["content"]):
                continue
            results.append(
                QuestionItem(
                    id=f"{note['id']}:{comment['id']}",
                    platform=self.platform,
                    title=comment["content"],
                    url=note["url"],
                    excerpt=str(detail.get("title") or note["title"]),
                    detail=str(detail.get("detail", "")),
                    topic=topic.name,
                    contentMode="answer",
                )
            )
        return results
```

在 `app/infrastructure/collectors/factory.py` 顶部 import 区新增：

```python
from .xiaohongshu_collector import XiaohongshuCollector
```

并在 `_collectors` 字典里，`f"{ZhihuOfficialCollector.platform}:official": ZhihuOfficialCollector,` 之后新增一行：

```python
        XiaohongshuCollector.platform: XiaohongshuCollector,
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/test_xiaohongshu_collector.py -v`
Expected: PASS（4 passed）

再运行一次全量测试确认没有破坏既有功能：

Run: `uv run pytest tests/ -v`
Expected: 全部通过

- [ ] **Step 5: 提交**

```bash
git add app/infrastructure/collectors/xiaohongshu_collector.py app/infrastructure/collectors/factory.py tests/test_xiaohongshu_collector.py
git commit -m "feat: add XiaohongshuCollector orchestrating note/comment collection by content_mode"
```

---

### Task 8: 生成层 prompt 分支（仿写 vs 回答）

**Files:**
- Modify: `app/infrastructure/llm/deepseek_client.py:32-83`（`generate_answer`）、`app/infrastructure/llm/deepseek_client.py:85-136`（`polish_answer`）
- Test: `tests/test_deepseek_content_mode_prompt.py`

**Interfaces:**
- Consumes: `QuestionItem.content_mode`（Task 1）
- Produces: 无新增公共接口，`generate_answer`/`polish_answer` 签名不变，仅内部 prompt 文案按 `item.content_mode` 分支。

- [ ] **Step 1: 写失败的测试**

```python
# tests/test_deepseek_content_mode_prompt.py
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from app.infrastructure.llm.deepseek_client import DeepSeekAnswerGenerator
from app.models import QuestionItem


def _fake_completion(content: str) -> MagicMock:
    completion = MagicMock()
    completion.choices = [MagicMock(message=MagicMock(content=content))]
    return completion


class DeepSeekContentModePromptTests(unittest.IsolatedAsyncioTestCase):
    """覆盖生成层按 content_mode 选择 prompt 模板；这样小红书仿写不会被误用"回答问题"的话术。"""

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
            patch("app.infrastructure.llm.deepseek_client.get_required_env", return_value="model-x"),
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
            patch("app.infrastructure.llm.deepseek_client.get_required_env", return_value="model-x"),
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
            patch("app.infrastructure.llm.deepseek_client.get_required_env", return_value="model-x"),
        ):
            await generator.polish_answer(item, "草稿内容", "活泼", "", "system", "generation")

        sent_prompt = fake_client.chat.completions.create.call_args.kwargs["messages"][1]["content"]
        self.assertIn("对下面这篇", sent_prompt)
        self.assertIn("笔记进行润色改写", sent_prompt)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_deepseek_content_mode_prompt.py -v`
Expected: FAIL（前两个测试因为现有 prompt 文案里没有"创作一篇全新的原创笔记"而失败；第三个因为现有 `polish_answer` 文案是"对下面这篇{platform}回答进行润色改写"而不包含"笔记进行润色改写"而失败）

- [ ] **Step 3: 实现**

在 `app/infrastructure/llm/deepseek_client.py` 的 `generate_answer` 方法里，把：

```python
        prompt_parts = [
            f"请围绕下面这个{platform_label}问题写一篇适合发布到对应平台的原创回答，整体风格要求：{answer_style}",
            "",
            "全局生成规则：",
            generation_prompt,
        ]
```

替换为：

```python
        if item.content_mode == "imitate":
            intro_line = (
                f"请参考下面这篇{platform_label}笔记的选题角度和写作风格，创作一篇全新的原创笔记，"
                f"不要照抄原文内容，只学习其风格和结构。整体风格要求：{answer_style}"
            )
        else:
            intro_line = f"请围绕下面这个{platform_label}问题写一篇适合发布到对应平台的原创回答，整体风格要求：{answer_style}"
        prompt_parts = [
            intro_line,
            "",
            "全局生成规则：",
            generation_prompt,
        ]
```

在 `polish_answer` 方法里，把：

```python
        prompt_parts = [
            f"请对下面这篇{platform_label}回答进行润色改写。要求：保留原有核心观点和论证思路，不要引入新观点；改善语言表达，消除 AI 腔、模板痕迹和空泛表述；让行文更自然、简洁、像真人写的。整体风格要求：{answer_style}",
            "",
            "全局生成规则：",
            generation_prompt,
        ]
```

替换为：

```python
        if item.content_mode == "imitate":
            intro_line = (
                f"请对下面这篇{platform_label}笔记进行润色改写。要求：保留原有核心创意和结构，不要引入新观点；"
                f"改善语言表达，消除 AI 腔、模板痕迹和空泛表述；让行文更自然、简洁、像真人写的。整体风格要求：{answer_style}"
            )
        else:
            intro_line = (
                f"请对下面这篇{platform_label}回答进行润色改写。要求：保留原有核心观点和论证思路，不要引入新观点；"
                f"改善语言表达，消除 AI 腔、模板痕迹和空泛表述；让行文更自然、简洁、像真人写的。整体风格要求：{answer_style}"
            )
        prompt_parts = [
            intro_line,
            "",
            "全局生成规则：",
            generation_prompt,
        ]
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/test_deepseek_content_mode_prompt.py -v`
Expected: PASS（3 passed）

再运行全量测试确认没有破坏既有功能：

Run: `uv run pytest tests/ -v`
Expected: 全部通过

- [ ] **Step 5: 提交**

```bash
git add app/infrastructure/llm/deepseek_client.py tests/test_deepseek_content_mode_prompt.py
git commit -m "feat: branch generation prompt between answer and note-imitation modes"
```

---

### Task 9: 前端 — 小红书平台选项与内容模式选择器

**Files:**
- Modify: `frontend/src/types/workflow.ts:1-43`
- Modify: `frontend/src/features/workspace/defaults.ts`
- Modify: `frontend/src/store/workspace-store.ts`
- Modify: `frontend/src/features/workspace/use-workspace.ts:64-220`
- Modify: `frontend/src/features/workspace/workspace-shell.tsx:870-900`、`frontend/src/features/workspace/workspace-shell.tsx:340-390`

**Interfaces:**
- Consumes: 无新后端接口变化，`CollectPayload`/`QuestionItem` 新增可选字段会被现有 `/api/workflow/collect` 按 alias 正确解析（Task 1 已支持 `contentMode`）。
- Produces: `ContentMode` 类型；`useWorkspaceStore().selectedContentMode` / `setSelectedContentMode`；`useWorkspace().selectedContentMode` / `selectContentMode`。

- [ ] **Step 1: 类型定义**

在 `frontend/src/types/workflow.ts` 里，`export type CollectSource = "official" | "web" | "auto";` 之后新增：

```typescript
export type ContentMode = "answer" | "imitate";
```

把 `QuestionItem` 类型里 `imagePrompts?: string[];` 之后新增一行：

```typescript
  contentMode?: ContentMode;
```

把 `CollectPayload` 类型里 `source?: CollectSource;` 之后新增一行：

```typescript
  contentMode?: ContentMode;
```

- [ ] **Step 2: 平台列表新增小红书**

修改 `frontend/src/features/workspace/defaults.ts`：

```typescript
import { DEFAULT_PLATFORM } from "@/types/workflow";

export const supportedPlatforms = [
  {
    id: DEFAULT_PLATFORM,
    label: "知乎",
  },
  {
    id: "xiaohongshu",
    label: "小红书",
  },
] as const;

export const defaultPlatform = supportedPlatforms[0].id;
export const maxCollectCount = 100;
```

**注意**：`DEFAULT_PLATFORM` 类型当前是 `typeof DEFAULT_PLATFORM`（即字面量 `"zhihu"`），`supportedPlatforms` 数组里混入 `"xiaohongshu"` 字面量后，`Platform` 类型也需要放宽。打开 `frontend/src/types/workflow.ts`，把：

```typescript
export type Platform = typeof DEFAULT_PLATFORM;
```

改为：

```typescript
export type Platform = typeof DEFAULT_PLATFORM | "xiaohongshu";
```

- [ ] **Step 3: Store 新增 selectedContentMode 状态**

修改 `frontend/src/store/workspace-store.ts`，在 import 行：

```typescript
import { DEFAULT_PLATFORM, type CollectSource, type Platform, type QuestionItem, type Topic } from "@/types/workflow";
```

改为：

```typescript
import {
  DEFAULT_PLATFORM,
  type CollectSource,
  type ContentMode,
  type Platform,
  type QuestionItem,
  type Topic,
} from "@/types/workflow";
```

在 `WorkspaceState` 类型里，`selectedSource: CollectSource;` 之后新增：

```typescript
  selectedContentMode: ContentMode;
```

并在同一类型里，`setSelectedSource: (source: CollectSource) => void;` 之后新增：

```typescript
  setSelectedContentMode: (mode: ContentMode) => void;
```

在 `create<WorkspaceState>` 的初始状态对象里，`selectedSource: "auto",` 之后新增：

```typescript
  selectedContentMode: "answer",
```

并在 `setSelectedSource: (selectedSource) => set({ selectedSource }),` 之后新增：

```typescript
  setSelectedContentMode: (selectedContentMode) => set({ selectedContentMode }),
```

- [ ] **Step 4: useWorkspace 暴露并使用 selectedContentMode**

修改 `frontend/src/features/workspace/use-workspace.ts`，在解构 `useWorkspaceStore()` 的地方，`selectedSource,` 之后新增 `selectedContentMode,`，并在对应的 setter 解构处新增 `setSelectedContentMode,`（紧跟 `setSelectedPlatform,` 之后即可）。

在 `collectMutation` 的 `mutationFn` 里，把：

```typescript
      const payload: CollectPayload = {
        platform: selectedPlatform,
        source: selectedSource,
```

改为：

```typescript
      const payload: CollectPayload = {
        platform: selectedPlatform,
        source: selectedSource,
        contentMode: selectedContentMode,
```

在文件末尾 `return { ... }` 的返回对象里（与 `selectSource: setSelectedSource,` 同一处），新增一行：

```typescript
    selectContentMode: setSelectedContentMode,
```

并把 `selectedContentMode,` 加入返回对象暴露给组件使用的字段列表（紧邻 `selectedSource,` 之后）。

- [ ] **Step 5: 操作栏按平台切换"来源"/"内容模式"选择器**

修改 `frontend/src/features/workspace/workspace-shell.tsx`，在解构 `useWorkspace()` 的地方（约第 780-793 行），新增 `selectedContentMode,` 和 `selectContentMode,`。

把第 886-898 行的"来源"选择器：

```tsx
          <div className="flex items-center gap-1.5">
            <Label className="shrink-0 text-[11px] font-medium text-slate-500">来源</Label>
            <Select value={selectedSource} onValueChange={(v) => selectSource(v as typeof selectedSource)}>
              <SelectTrigger className="h-8 w-[112px] rounded-md border-slate-200 bg-white text-[12px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="auto" className="text-[12px]">自动选择</SelectItem>
                <SelectItem value="official" className="text-[12px]">官方 API</SelectItem>
                <SelectItem value="web" className="text-[12px]">网页抓取</SelectItem>
              </SelectContent>
            </Select>
          </div>
```

改为按平台条件渲染：

```tsx
          {selectedPlatform === "xiaohongshu" ? (
            <div className="flex items-center gap-1.5">
              <Label className="shrink-0 text-[11px] font-medium text-slate-500">内容模式</Label>
              <Select
                value={selectedContentMode}
                onValueChange={(v) => selectContentMode(v as typeof selectedContentMode)}
              >
                <SelectTrigger className="h-8 w-[112px] rounded-md border-slate-200 bg-white text-[12px]">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="answer" className="text-[12px]">回答模式</SelectItem>
                  <SelectItem value="imitate" className="text-[12px]">仿写模式</SelectItem>
                </SelectContent>
              </Select>
            </div>
          ) : (
            <div className="flex items-center gap-1.5">
              <Label className="shrink-0 text-[11px] font-medium text-slate-500">来源</Label>
              <Select value={selectedSource} onValueChange={(v) => selectSource(v as typeof selectedSource)}>
                <SelectTrigger className="h-8 w-[112px] rounded-md border-slate-200 bg-white text-[12px]">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="auto" className="text-[12px]">自动选择</SelectItem>
                  <SelectItem value="official" className="text-[12px]">官方 API</SelectItem>
                  <SelectItem value="web" className="text-[12px]">网页抓取</SelectItem>
                </SelectContent>
              </Select>
            </div>
          )}
```

- [ ] **Step 6: 问题列表副标题区分仿写模式**

找到第 384 行附近渲染问题副标题的代码：

```tsx
              {question.platform ?? "zhihu"} · {question.answerCount} 个回答
```

改为：

```tsx
              {question.contentMode === "imitate"
                ? `${question.platform ?? "zhihu"} · 笔记仿写参考`
                : `${question.platform ?? "zhihu"} · ${question.answerCount} 个回答`}
```

- [ ] **Step 7: 类型检查**

Run: `cd frontend && bun run typecheck`
Expected: 无报错退出（exit code 0）

- [ ] **Step 8: 提交**

```bash
git add frontend/src/types/workflow.ts frontend/src/features/workspace/defaults.ts frontend/src/store/workspace-store.ts frontend/src/features/workspace/use-workspace.ts frontend/src/features/workspace/workspace-shell.tsx
git commit -m "feat: add xiaohongshu platform option and content mode selector to collect UI"
```

---

## Self-Review Notes（写计划时已做的检查，供执行者参考）

- **Spec 覆盖**：`feature-xiaohongshu-platform.md` 的"采集流程"→Task 4-7；"数据模型变更"→Task 1；"生成层分支"→Task 8；"前端改动"→Task 9；"需要新增的基础设施"→Task 2；"环境变量"→Task 3；"错误处理与已知风险"中的 cookie 失效/验证码识别→Task 3+7；评论区失败降级→Task 7（per-note `except ValueError`）；请求节流→Task 7（`REQUEST_INTERVAL_SECONDS`）。图片生成明确不在范围内，未建任务，符合 spec。
- **类型一致性**：`QuestionItem.content_mode`（Task 1）在 Task 7（collector 构造 `QuestionItem(...)`）、Task 8（`item.content_mode` 读取）、Task 9（`question.contentMode`）中引用一致；`PlaywrightFetcher(cookie_string, cookie_domain)` 构造签名在 Task 2 定义、Task 7 消费时保持一致；`ensure_usable_xiaohongshu_page` 抛出的 `XiaohongshuAccessError` 与 Task 7 测试里的 `except ValueError`（仅捕获笔记级解析失败，不捕获访问错误）边界一致。
- **已知限制**：小红书页面真实 DOM/JSON 结构未经真实账号验证，Task 4-6 的解析逻辑基于公开资料中常见结构编写，建议执行完 Task 7 后用真实 cookie 跑一次手动验证（非自动化测试覆盖范围）。

## Execution Handoff

Plan complete and saved to `docs/plans/plan-xiaohongshu-platform.md`。采用推荐方式执行：**Subagent-Driven**（superpowers:subagent-driven-development）—— 每个 Task 派一个新的子代理执行，执行间会有两段式审查（实现完成后review，commit前最终确认），适合这种跨 9 个任务、涉及新依赖和多个文件的变更。如果你更想在当前会话里批量跑、按检查点review，也可以告诉我换成 Inline Execution（superpowers:executing-plans）。
