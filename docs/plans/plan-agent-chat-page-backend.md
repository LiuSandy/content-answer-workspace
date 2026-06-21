# Agent Chat Page — Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让后端支持多 Session 管理（创建/列表/按 ID 读写）和一个真正多轮、可持久化的对话 Agent（`/api/agent/conversation`），为对话页面提供完整可用的 API。

**Architecture:** Session 工作区数据继续按 JSON 文件存储，但文件名从时间戳改为 `sessionId`，新增创建/列表/按 ID 读取函数；对话历史用 LangGraph 的 `AsyncSqliteSaver` 持久化到独立的 SQLite 文件，按 `thread_id = sessionId` 分区，由一个新的单节点 `ConversationGraph` 驱动，节点内只做纯 LLM 多轮对话，不调用任何业务工具。

**Tech Stack:** FastAPI、LangGraph（`StateGraph` + `MessagesState` + `AsyncSqliteSaver`）、Pydantic、OpenAI 兼容客户端（已有 `DeepSeekAnswerGenerator`）、`unittest.IsolatedAsyncioTestCase`（项目现有测试风格）。

## Global Constraints

- 后端新增依赖仅 `langgraph-checkpoint-sqlite`（已核实与当前锁定的 `langgraph-checkpoint 4.1.1` 兼容）。
- 不修改 `/api/agent/chat`、`RefinementGraph`、`AnalysisGraph` 的任何现有行为。
- 不引入工具调用（Function Calling）——`chat_node` 只做纯文本多轮对话。
- **测试范围约定**：项目现状是只对 `services/`、`infrastructure/`、未来的 `application/agent/` 下的业务逻辑写单元测试（`tests/` 目录现有 7 个测试文件全部如此），FastAPI 路由文件（`api/routes/*.py`）和 `server.py` 里的路由注册/生命周期管理代码没有专门的自动化测试（项目里也没有任何 `TestClient` 用例）。本计划遵循这个现状：业务逻辑（session_service、chat_node、ConversationGraph）写自动化测试；路由层和 `server.py` 的接线代码用手动 `curl` 验证（见 Task 10）。这不是疏漏，是匹配现有项目惯例。
- 所有 Pydantic 模型字段用 `alias` 驼峰命名，`model_config = {"populate_by_name": True}`，序列化统一 `model_dump_json(by_alias=True)`——这是项目现有强制约定（见 CLAUDE.md）。

---

### Task 1: 添加 `langgraph-checkpoint-sqlite` 依赖

**Files:**
- Modify: `pyproject.toml`

**Interfaces:**
- Produces: `langgraph.checkpoint.sqlite.aio.AsyncSqliteSaver` 在后续任务中可被导入使用。

- [ ] **Step 1: 添加依赖声明**

在 `pyproject.toml` 的 `dependencies` 列表里，`"langgraph>=0.2",` 这一行后面新增一行：

```toml
  "langgraph-checkpoint-sqlite>=3.0",
```

- [ ] **Step 2: 安装并锁定依赖**

```bash
uv sync
```

Expected: 命令成功退出，`uv.lock` 被更新，新增 `langgraph-checkpoint-sqlite`、`aiosqlite`、`sqlite-vec` 三个包。

- [ ] **Step 3: 验证可以正常导入**

```bash
uv run python -c "from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver; print('ok')"
```

Expected: 输出 `ok`，没有 `ModuleNotFoundError`。

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore: add langgraph-checkpoint-sqlite for persistent conversation history"
```

---

### Task 2: 扩展 `SessionPayload` 模型支持多 Session

**Files:**
- Modify: `app/models.py:76-91`（`SessionPayload` 类）
- Test: `tests/test_models_session_payload.py`

**Interfaces:**
- Produces: `SessionPayload` 新增字段 `session_id: str`（alias `sessionId`，默认 `""`）、`title: str`（alias `title`，默认 `"新对话"`）、`created_at: str`（alias `createdAt`，默认 `""`）。Task 3 的 `session_service.py` 依赖这三个字段。

- [ ] **Step 1: 写失败的测试**

创建 `tests/test_models_session_payload.py`：

```python
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
```

- [ ] **Step 2: 运行测试确认失败**

```bash
uv run pytest tests/test_models_session_payload.py -v
```

Expected: FAIL，报 `SessionPayload() got unexpected keyword argument 'sessionId'` 或 `AttributeError: 'SessionPayload' object has no attribute 'session_id'`。

- [ ] **Step 3: 修改 `SessionPayload`**

在 `app/models.py` 中，把：

```python
class SessionPayload(BaseModel):
    """表示前端保存或批量生成时提交的会话数据；定义成模型是为了兼容本地保存和回答生成两个场景。"""

    platform: str = "zhihu"
    saved_at: str | None = Field(default=None, alias="savedAt")
```

改成：

```python
class SessionPayload(BaseModel):
    """表示前端保存或批量生成时提交的会话数据；定义成模型是为了兼容本地保存和回答生成两个场景。"""

    session_id: str = Field(default="", alias="sessionId")
    title: str = Field(default="新对话", alias="title")
    created_at: str = Field(default="", alias="createdAt")
    platform: str = "zhihu"
    saved_at: str | None = Field(default=None, alias="savedAt")
```

（其余字段 `topics`/`answer_style`/`system_prompt`/`generation_prompt`/`content_constraint`/`max_push_count`/`items`/`model_config` 保持不变。）

- [ ] **Step 4: 运行测试确认通过**

```bash
uv run pytest tests/test_models_session_payload.py -v
```

Expected: PASS，2 passed。

- [ ] **Step 5: Commit**

```bash
git add app/models.py tests/test_models_session_payload.py
git commit -m "feat: add sessionId/title/createdAt fields to SessionPayload"
```

---

### Task 3: 重写 `session_service.py` 支持多 Session 创建/列表/按 ID 读写

**Files:**
- Modify: `app/services/session_service.py`
- Test: `tests/test_session_service.py`

**Interfaces:**
- Consumes: `SessionPayload`（Task 2 新增字段）、`app.core.config.OUTPUT_DIR`
- Produces:
  - `create_session() -> dict[str, str]`，返回 `{"sessionId": str, "title": str, "createdAt": str}`
  - `list_sessions() -> list[dict[str, str]]`，每项同上结构，按 `createdAt` 倒序
  - `read_session(session_id: str) -> dict[str, Any] | None`
  - `save_session(payload: SessionPayload) -> str`（签名不变，行为改为按 `sessionId` 落盘）
  - `read_latest_session() -> dict[str, Any] | None`（签名不变，内部改为基于 `list_sessions()`）
  - `update_session_title(session_id: str, title: str) -> None`，供 Task 9 在对话第一条消息发出后自动回填标题
  - `save_workflow_result`、`cookie_status` 保持不变，供 `workflow.py`/`session.py` 现有调用方继续使用。

- [ ] **Step 1: 写失败的测试**

创建 `tests/test_session_service.py`：

```python
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
```

- [ ] **Step 2: 运行测试确认失败**

```bash
uv run pytest tests/test_session_service.py -v
```

Expected: FAIL，报 `ImportError: cannot import name 'create_session'`（函数还不存在）。

- [ ] **Step 3: 重写 `session_service.py`**

把整个文件内容替换为：

```python
from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from ..core.config import OUTPUT_DIR
from ..models import SessionPayload, WorkflowResult

SESSIONS_DIR = OUTPUT_DIR / "sessions"


def _session_file_path(session_id: str) -> Path:
    """返回指定 session 对应的文件路径；这样创建、读取、保存都基于同一套寻址规则。"""

    return SESSIONS_DIR / f"{session_id}.json"


def create_session() -> dict[str, str]:
    """创建一个新的空 session；这样对话页面点「新建对话」时能立刻拿到一个可用的 sessionId。"""

    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    session_id = uuid.uuid4().hex
    created_at = datetime.now().isoformat()
    payload = SessionPayload(sessionId=session_id, title="新对话", createdAt=created_at)
    _session_file_path(session_id).write_text(payload.model_dump_json(indent=2, by_alias=True), "utf-8")
    return {"sessionId": session_id, "title": payload.title, "createdAt": created_at}


def list_sessions() -> list[dict[str, str]]:
    """列出所有 session 的摘要信息；这样对话页面和工作区页面能渲染可切换的会话列表。"""

    if not SESSIONS_DIR.exists():
        return []
    summaries: list[dict[str, str]] = []
    for file_path in SESSIONS_DIR.glob("*.json"):
        try:
            data = json.loads(file_path.read_text("utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        summaries.append(
            {
                "sessionId": data.get("sessionId") or file_path.stem,
                "title": data.get("title") or "新对话",
                "createdAt": data.get("createdAt") or "",
            }
        )
    return sorted(summaries, key=lambda item: item["createdAt"], reverse=True)


def read_session(session_id: str) -> dict[str, Any] | None:
    """按 ID 读取指定 session 的工作区数据；这样前端切换会话时能恢复对应的采集结果和回答。"""

    file_path = _session_file_path(session_id)
    if not file_path.exists():
        return None
    return json.loads(file_path.read_text("utf-8"))


def save_session(payload: SessionPayload) -> str:
    """保存前端提交的会话数据；按 sessionId 落盘，重复保存覆盖同一份文件而不再新建时间戳文件。"""

    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    session_id = payload.session_id or uuid.uuid4().hex
    data = payload.model_copy(update={"session_id": session_id})
    file_path = _session_file_path(session_id)
    file_path.write_text(data.model_dump_json(indent=2, by_alias=True), "utf-8")
    return str(file_path)


def save_workflow_result(result: WorkflowResult) -> dict[str, str]:
    """保存完整工作流结果；这样 CLI 执行采集和生成后能产出可追踪的本地文件。"""

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    date_label = datetime.now().strftime("%Y-%m-%d")
    report_path = OUTPUT_DIR / f"workflow-daily-{date_label}.md"
    json_path = OUTPUT_DIR / f"workflow-daily-{date_label}.json"
    report_path.write_text("# Workflow result\n", "utf-8")
    json_path.write_text(result.model_dump_json(indent=2, by_alias=True), "utf-8")
    return {"reportPath": str(report_path), "jsonPath": str(json_path)}


def read_latest_session() -> dict[str, Any] | None:
    """读取最近创建的一个 session；兼容旧版「只读最新一份」的调用方式。"""

    summaries = list_sessions()
    if not summaries:
        return None
    return read_session(summaries[0]["sessionId"])


def update_session_title(session_id: str, title: str) -> None:
    """更新指定 session 的标题；这样对话发出第一条消息后能自动生成有意义的会话名称。"""

    file_path = _session_file_path(session_id)
    if not file_path.exists():
        return
    data = json.loads(file_path.read_text("utf-8"))
    data["title"] = title
    file_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), "utf-8")


def cookie_status(cookie_path_value: str) -> dict[str, bool]:
    """检查 cookie 文件配置和存在状态；这样采集前可以判断知乎请求凭据是否可用。"""

    configured = bool(cookie_path_value)
    loaded = bool(cookie_path_value and Path(cookie_path_value).exists())
    return {"configured": configured, "loaded": loaded}
```

- [ ] **Step 4: 运行测试确认通过**

```bash
uv run pytest tests/test_session_service.py -v
```

Expected: PASS，9 passed。

- [ ] **Step 5: 确认没有破坏现有调用方**

```bash
uv run pytest tests/ -v
```

Expected: 全部通过（包括之前已存在的测试文件），没有因为 `session_service` 改动连带失败。

- [ ] **Step 6: Commit**

```bash
git add app/services/session_service.py tests/test_session_service.py
git commit -m "feat: support multi-session create/list/read in session_service"
```

---

### Task 4: 新增对话系统提示词与 `DeepSeekAnswerGenerator.chat()` 方法

**Files:**
- Modify: `app/core/prompts.py`
- Modify: `app/infrastructure/llm/deepseek_client.py`
- Test: `tests/test_deepseek_chat_method.py`

**Interfaces:**
- Produces:
  - `app.core.prompts.CONVERSATION_SYSTEM_PROMPT: str`
  - `DeepSeekAnswerGenerator.chat(self, messages: list[dict[str, str]]) -> str`（多轮对话调用，`messages` 含 `role`/`content`，不附加任何业务提示词）
- Task 5 的 `chat_node` 依赖这两者。

- [ ] **Step 1: 写失败的测试**

创建 `tests/test_deepseek_chat_method.py`：

```python
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from app.infrastructure.llm.deepseek_client import DeepSeekAnswerGenerator


def _fake_completion(content: str | None) -> MagicMock:
    completion = MagicMock()
    completion.choices = [MagicMock(message=MagicMock(content=content))]
    return completion


class DeepSeekChatMethodTests(unittest.IsolatedAsyncioTestCase):
    """覆盖多轮对话调用方法；这样对话 Agent 节点能复用同一套 LLM 客户端而不附加业务提示词。"""

    async def test_chat_passes_messages_through_and_returns_content(self) -> None:
        generator = DeepSeekAnswerGenerator()
        fake_client = MagicMock()
        fake_client.chat.completions.create.return_value = _fake_completion("你好，我能帮你梳理选题思路。")

        with (
            patch.object(generator, "get_client", return_value=fake_client),
            patch("app.infrastructure.llm.deepseek_client.get_required_env", return_value="model-x"),
        ):
            messages = [
                {"role": "system", "content": "你是内容策略助手"},
                {"role": "user", "content": "帮我想几个选题"},
            ]
            reply = await generator.chat(messages)

        self.assertEqual(reply, "你好，我能帮你梳理选题思路。")
        fake_client.chat.completions.create.assert_called_once_with(model="model-x", messages=messages)

    async def test_chat_raises_when_content_empty(self) -> None:
        generator = DeepSeekAnswerGenerator()
        fake_client = MagicMock()
        fake_client.chat.completions.create.return_value = _fake_completion(None)

        with (
            patch.object(generator, "get_client", return_value=fake_client),
            patch("app.infrastructure.llm.deepseek_client.get_required_env", return_value="model-x"),
        ):
            with self.assertRaises(ValueError):
                await generator.chat([{"role": "user", "content": "hi"}])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试确认失败**

```bash
uv run pytest tests/test_deepseek_chat_method.py -v
```

Expected: FAIL，报 `AttributeError: 'DeepSeekAnswerGenerator' object has no attribute 'chat'`。

- [ ] **Step 3: 添加系统提示词常量**

在 `app/core/prompts.py` 末尾追加：

```python
CONVERSATION_SYSTEM_PROMPT = "\n".join(
    [
        "你是内容创作工作台里的对话助手，帮用户梳理选题思路、讨论写作角度、起草和修改文字。",
        "用中文回复，语气自然，不要写成正式公文或空洞的套话。",
        "不知道的事情就说不知道，不要编造数据、案例、链接或机构名称。",
        "你现在不能执行采集、生成回答、发布等系统操作，只能通过对话本身帮用户思考和起草内容。",
    ]
)
```

- [ ] **Step 4: 添加 `chat()` 方法**

在 `app/infrastructure/llm/deepseek_client.py` 的 `DeepSeekAnswerGenerator` 类里，紧跟在 `call_raw` 方法（约第 160-174 行）后面新增：

```python
    async def chat(self, messages: list[dict[str, str]]) -> str:
        """多轮对话调用，messages 是完整历史（含 system/user/assistant），不附加任何业务提示词。"""
        client = self.get_client()
        model = get_required_env("DEEPSEEK_MODEL")
        completion = client.chat.completions.create(model=model, messages=messages)
        content = completion.choices[0].message.content if completion.choices else None
        if isinstance(content, str):
            return content.strip()
        raise ValueError("LLM returned empty chat content")
```

- [ ] **Step 5: 运行测试确认通过**

```bash
uv run pytest tests/test_deepseek_chat_method.py -v
```

Expected: PASS，2 passed。

- [ ] **Step 6: Commit**

```bash
git add app/core/prompts.py app/infrastructure/llm/deepseek_client.py tests/test_deepseek_chat_method.py
git commit -m "feat: add DeepSeekAnswerGenerator.chat() for multi-turn conversation"
```

---

### Task 5: 新增 `ConversationState` 和 `chat_node`

**Files:**
- Modify: `app/application/agent/state.py`
- Create: `app/application/agent/nodes/chat.py`
- Test: `tests/test_agent_chat_node.py`

**Interfaces:**
- Consumes: `DeepSeekAnswerGenerator.chat()`（Task 4）、`app.core.prompts.CONVERSATION_SYSTEM_PROMPT`（Task 4）
- Produces:
  - `app.application.agent.state.ConversationState`（`TypedDict`，字段 `messages: Annotated[list, add_messages]`）
  - `app.application.agent.nodes.chat.chat_node(state: ConversationState) -> dict`，返回 `{"messages": [{"role": "assistant", "content": str}]}`
  - Task 6 的 `build_conversation_graph` 依赖这两者。

- [ ] **Step 1: 写失败的测试**

创建 `tests/test_agent_chat_node.py`：

```python
from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from langchain_core.messages import AIMessage, HumanMessage

from app.application.agent.nodes.chat import chat_node


class ChatNodeTests(unittest.IsolatedAsyncioTestCase):
    """覆盖对话节点的消息历史转换；这样多轮上下文能正确传给 LLM 并按统一格式追加回复。"""

    async def test_chat_node_converts_history_and_appends_reply(self) -> None:
        state = {
            "messages": [
                HumanMessage(content="帮我想几个选题"),
                AIMessage(content="可以从读者痛点入手"),
                HumanMessage(content="再具体一点"),
            ]
        }

        with patch(
            "app.application.agent.nodes.chat._generator.chat",
            new=AsyncMock(return_value="比如「远程工作如何保持专注」这个角度"),
        ) as mock_chat:
            result = await chat_node(state)

        sent_messages = mock_chat.call_args.args[0]
        self.assertEqual(sent_messages[0]["role"], "system")
        self.assertEqual(sent_messages[1], {"role": "user", "content": "帮我想几个选题"})
        self.assertEqual(sent_messages[2], {"role": "assistant", "content": "可以从读者痛点入手"})
        self.assertEqual(sent_messages[3], {"role": "user", "content": "再具体一点"})
        self.assertEqual(
            result,
            {"messages": [{"role": "assistant", "content": "比如「远程工作如何保持专注」这个角度"}]},
        )


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试确认失败**

```bash
uv run pytest tests/test_agent_chat_node.py -v
```

Expected: FAIL，报 `ModuleNotFoundError: No module named 'app.application.agent.nodes.chat'`。

- [ ] **Step 3: 在 `state.py` 新增 `ConversationState`**

在 `app/application/agent/state.py` 文件顶部的 `from typing import TypedDict` 这一行改成：

```python
from typing import Annotated, TypedDict

from langgraph.graph.message import add_messages
```

然后在文件末尾（现有 `AgentState` 类定义之后）追加：

```python
class ConversationState(TypedDict):
    """对话页面使用的状态；messages 由 add_messages reducer 自动累积历史，不需要手动拼接。"""

    messages: Annotated[list, add_messages]
```

- [ ] **Step 4: 创建 `chat_node`**

创建 `app/application/agent/nodes/chat.py`：

```python
from __future__ import annotations

from ....core.prompts import CONVERSATION_SYSTEM_PROMPT
from ....infrastructure.llm.deepseek_client import DeepSeekAnswerGenerator
from ..state import ConversationState

_generator = DeepSeekAnswerGenerator()

_ROLE_MAP = {"human": "user", "ai": "assistant", "system": "system"}


async def chat_node(state: ConversationState) -> dict:
    """把完整对话历史交给 LLM 做多轮对话；不调用任何业务工具，只返回新的一条助手消息。"""

    history = [{"role": "system", "content": CONVERSATION_SYSTEM_PROMPT}]
    for message in state["messages"]:
        history.append({"role": _ROLE_MAP.get(message.type, "user"), "content": message.content})

    reply = await _generator.chat(history)
    return {"messages": [{"role": "assistant", "content": reply}]}
```

- [ ] **Step 5: 运行测试确认通过**

```bash
uv run pytest tests/test_agent_chat_node.py -v
```

Expected: PASS，1 passed。

- [ ] **Step 6: Commit**

```bash
git add app/application/agent/state.py app/application/agent/nodes/chat.py tests/test_agent_chat_node.py
git commit -m "feat: add ConversationState and chat_node for multi-turn dialogue"
```

---

### Task 6: 新增 `build_conversation_graph`

**Files:**
- Create: `app/application/agent/graphs/conversation.py`
- Test: `tests/test_conversation_graph.py`

**Interfaces:**
- Consumes: `ConversationState`、`chat_node`（Task 5）
- Produces: `build_conversation_graph(checkpointer) -> CompiledStateGraph`，接受任意实现 `BaseCheckpointSaver` 接口的对象（不关心具体是内存还是 SQLite），返回已编译的 Graph。Task 7（`server.py` 接线）依赖这个函数签名。

- [ ] **Step 1: 写失败的测试**

创建 `tests/test_conversation_graph.py`：

```python
from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from langgraph.checkpoint.memory import InMemorySaver

from app.application.agent.graphs.conversation import build_conversation_graph


class ConversationGraphTests(unittest.IsolatedAsyncioTestCase):
    """覆盖对话 Graph 的多轮历史持久化；这样同一个 thread_id 在多次调用间能正确累积消息。"""

    async def test_history_accumulates_across_invocations_with_same_thread_id(self) -> None:
        checkpointer = InMemorySaver()
        graph = build_conversation_graph(checkpointer)
        config = {"configurable": {"thread_id": "session-1"}}

        with patch(
            "app.application.agent.nodes.chat._generator.chat",
            new=AsyncMock(side_effect=["第一句回复", "第二句回复"]),
        ):
            await graph.ainvoke({"messages": [{"role": "user", "content": "你好"}]}, config=config)
            result = await graph.ainvoke({"messages": [{"role": "user", "content": "继续"}]}, config=config)

        self.assertEqual(len(result["messages"]), 4)
        self.assertEqual(result["messages"][-1].content, "第二句回复")

    async def test_different_thread_ids_do_not_share_history(self) -> None:
        checkpointer = InMemorySaver()
        graph = build_conversation_graph(checkpointer)

        with patch(
            "app.application.agent.nodes.chat._generator.chat",
            new=AsyncMock(return_value="回复"),
        ):
            await graph.ainvoke(
                {"messages": [{"role": "user", "content": "会话一"}]},
                config={"configurable": {"thread_id": "session-a"}},
            )
            result_b = await graph.ainvoke(
                {"messages": [{"role": "user", "content": "会话二"}]},
                config={"configurable": {"thread_id": "session-b"}},
            )

        self.assertEqual(len(result_b["messages"]), 2)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试确认失败**

```bash
uv run pytest tests/test_conversation_graph.py -v
```

Expected: FAIL，报 `ModuleNotFoundError: No module named 'app.application.agent.graphs.conversation'`。

- [ ] **Step 3: 创建 `conversation.py`**

创建 `app/application/agent/graphs/conversation.py`：

```python
from __future__ import annotations

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from ..nodes.chat import chat_node
from ..state import ConversationState


def build_conversation_graph(checkpointer: BaseCheckpointSaver):
    """构建对话页面用的单节点 Graph；checkpointer 由调用方注入和管理生命周期，graph 本身不持有连接。"""

    graph: StateGraph = StateGraph(ConversationState)
    graph.add_node("chat", chat_node)
    graph.add_edge(START, "chat")
    graph.add_edge("chat", END)
    return graph.compile(checkpointer=checkpointer)
```

- [ ] **Step 4: 运行测试确认通过**

```bash
uv run pytest tests/test_conversation_graph.py -v
```

Expected: PASS，2 passed。

- [ ] **Step 5: Commit**

```bash
git add app/application/agent/graphs/conversation.py tests/test_conversation_graph.py
git commit -m "feat: add build_conversation_graph with pluggable checkpointer"
```

---

### Task 7: 把 SQLite Checkpointer 接入 `server.py` 生命周期

**Files:**
- Modify: `app/server.py`

**Interfaces:**
- Consumes: `build_conversation_graph`（Task 6）、`langgraph.checkpoint.sqlite.aio.AsyncSqliteSaver`
- Produces: `app.state.conversation_graph`，供 Task 8 的路由直接读取使用。

- [ ] **Step 1: 修改 `server.py` 顶部 import**

把现有的：

```python
from __future__ import annotations

import os
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .api.routes.agent import router as agent_router
from .api.routes.config import router as config_router
from .api.routes.hotlist import router as hotlist_router
from .api.routes.session import router as session_router
from .api.routes.workflow import router as workflow_router
from .application.workflow_service import WorkflowService
from .core.config import GENERATED_IMAGES_DIR, load_env_file
from .models import RegeneratePayload, RunPayload, SessionPayload
from .services.session_service import cookie_status, read_latest_session, save_session
```

改成：

```python
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from .api.routes.agent import router as agent_router
from .api.routes.config import router as config_router
from .api.routes.hotlist import router as hotlist_router
from .api.routes.session import router as session_router
from .api.routes.workflow import router as workflow_router
from .application.agent.graphs.conversation import build_conversation_graph
from .application.workflow_service import WorkflowService
from .core.config import GENERATED_IMAGES_DIR, OUTPUT_DIR, load_env_file
from .models import RegeneratePayload, RunPayload, SessionPayload
from .services.session_service import cookie_status, read_latest_session, save_session
```

- [ ] **Step 2: 添加 lifespan 和 checkpoint 路径常量**

把现有的：

```python
ROOT_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIST_DIR = ROOT_DIR / "frontend" / "dist"

app = FastAPI()
workflow_service = WorkflowService()
GENERATED_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/generated-images", StaticFiles(directory=GENERATED_IMAGES_DIR), name="generated-images")
```

改成：

```python
ROOT_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIST_DIR = ROOT_DIR / "frontend" / "dist"
CONVERSATION_CHECKPOINT_DB = OUTPUT_DIR / "agent_checkpoints.sqlite"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时打开对话历史的 SQLite 连接并编译对话 Graph；关闭时释放连接。"""

    CONVERSATION_CHECKPOINT_DB.parent.mkdir(parents=True, exist_ok=True)
    async with AsyncSqliteSaver.from_conn_string(str(CONVERSATION_CHECKPOINT_DB)) as checkpointer:
        app.state.conversation_graph = build_conversation_graph(checkpointer)
        yield


app = FastAPI(lifespan=lifespan)
workflow_service = WorkflowService()
GENERATED_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/generated-images", StaticFiles(directory=GENERATED_IMAGES_DIR), name="generated-images")
```

- [ ] **Step 3: 验证应用仍能正常启动**

```bash
uv run python -c "
from app.server import app
print('lifespan attached:', app.router.lifespan_context is not None)
"
```

Expected: 输出 `lifespan attached: True`，没有报错。完整的启动验证在 Task 10 做。

- [ ] **Step 4: Commit**

```bash
git add app/server.py
git commit -m "feat: wire persistent SQLite checkpointer into app lifespan"
```

---

### Task 8: 新增 Session 管理路由

**Files:**
- Modify: `app/api/routes/session.py`

**Interfaces:**
- Consumes: `create_session`、`list_sessions`、`read_session`（Task 3）
- Produces: `GET /api/session/new` 替换为 `POST /api/session/new`、`GET /api/session/list`、`GET /api/session/{session_id}`；`GET /api/session/latest`、`POST /api/session/save` 保持原有路径和响应包装不变。

- [ ] **Step 1: 修改 `app/api/routes/session.py`**

把整个文件内容替换为：

```python
from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from ...models import SessionPayload
from ...services.session_service import (
    cookie_status,
    create_session,
    list_sessions,
    read_latest_session,
    read_session,
    save_session,
)

router = APIRouter(prefix="/api/session", tags=["session"])


@router.get("/latest")
async def get_latest_session() -> JSONResponse:
    """返回最近创建的会话；这样前端刷新后可以恢复上一次编辑状态。"""

    return JSONResponse({"ok": True, "data": {"session": read_latest_session()}})


@router.post("/new")
async def new_session() -> JSONResponse:
    """创建一个新的空会话；这样对话页面点「新建对话」时能立刻拿到一个可用的 sessionId。"""

    return JSONResponse({"ok": True, "data": create_session()})


@router.get("/list")
async def get_session_list() -> JSONResponse:
    """列出所有会话摘要；这样对话页面和工作区页面能渲染可切换的会话列表。"""

    return JSONResponse({"ok": True, "data": list_sessions()})


@router.post("/save")
async def save(payload: SessionPayload) -> JSONResponse:
    """保存当前前端会话；这样采集结果和人工编辑回答可以持久化到本地文件。"""

    file_path = save_session(payload)
    return JSONResponse({"ok": True, "data": {"filePath": file_path}})


@router.get("/cookie-status")
async def get_cookie_status() -> JSONResponse:
    """返回知乎 cookie 文件状态；这样前端可以提示采集能力是否具备必要凭据。"""

    return JSONResponse(
        {
            "ok": True,
            "data": cookie_status(os.getenv("ZHIHU_COOKIE_FILE", "").strip()),
        }
    )


@router.get("/{session_id}")
async def get_session_by_id(session_id: str) -> JSONResponse:
    """按 ID 读取指定会话的工作区数据；这样前端切换会话后能恢复对应的采集结果。"""

    session = read_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")
    return JSONResponse({"ok": True, "data": {"session": session}})
```

> 注意：`/{session_id}` 必须放在文件最后——FastAPI 按注册顺序匹配路由，如果它排在 `/list`、`/new`、`/cookie-status` 前面，这些固定路径会被错误地当成 `session_id` 的值捕获。

- [ ] **Step 2: 手动验证（按 Task 10 统一跑一次完整 curl 流程）**

本任务不单独写自动化测试（原因见 Global Constraints），验证并入 Task 10。

- [ ] **Step 3: Commit**

```bash
git add app/api/routes/session.py
git commit -m "feat: add session new/list/{id} routes for multi-session support"
```

---

### Task 9: 新增对话接口

**Files:**
- Modify: `app/api/routes/agent.py`

**Interfaces:**
- Consumes: `app.state.conversation_graph`（Task 7 在 `server.py` lifespan 里注入）、`update_session_title`（Task 3）
- Produces: `POST /api/agent/conversation`、`GET /api/agent/conversation/{session_id}/history`

- [ ] **Step 1: 在 `app/api/routes/agent.py` 末尾追加**

文件现有内容（`agent_chat` 及其依赖的 import、`AgentChatRequest`）保持不变，在顶部 import 区追加：

```python
from ...services.session_service import update_session_title
```

然后在文件末尾追加：

```python
class ConversationRequest(BaseModel):
    sessionId: str
    message: str

    model_config = {"populate_by_name": True}


@router.post("/api/agent/conversation")
async def agent_conversation(request: ConversationRequest, http_request: Request) -> JSONResponse:
    """对话页面专用接口；调用独立的 ConversationGraph，不影响精修/分析两个现有 Graph。"""

    graph = http_request.app.state.conversation_graph
    config = {"configurable": {"thread_id": request.sessionId}}
    existing_state = await graph.aget_state(config)
    is_first_message = not existing_state.values.get("messages")

    result = await graph.ainvoke(
        {"messages": [{"role": "user", "content": request.message}]},
        config=config,
    )
    reply = result["messages"][-1].content

    if is_first_message:
        update_session_title(request.sessionId, request.message[:20])

    return JSONResponse({"ok": True, "data": {"reply": reply}})


@router.get("/api/agent/conversation/{session_id}/history")
async def agent_conversation_history(session_id: str, http_request: Request) -> JSONResponse:
    """读取指定会话的完整对话历史；供前端进入对话页面时首次渲染消息流。"""

    graph = http_request.app.state.conversation_graph
    config = {"configurable": {"thread_id": session_id}}
    state = await graph.aget_state(config)
    role_map = {"human": "user", "ai": "assistant", "system": "system"}
    messages = [
        {"role": role_map.get(message.type, "user"), "content": message.content}
        for message in state.values.get("messages", [])
    ]
    return JSONResponse({"ok": True, "data": {"messages": messages}})
```

需要在文件顶部的 import 里把：

```python
from fastapi import APIRouter
```

改成：

```python
from fastapi import APIRouter, Request
```

- [ ] **Step 2: 手动验证（并入 Task 10）**

- [ ] **Step 3: Commit**

```bash
git add app/api/routes/agent.py
git commit -m "feat: add /api/agent/conversation chat and history endpoints"
```

---

### Task 10: 端到端手动验证

**Files:** 无代码改动，仅验证。

- [ ] **Step 1: 准备环境变量**

确认 `.env` 中已配置 `DEEPSEEK_API_KEY`/`DEEPSEEK_BASE_URL`/`DEEPSEEK_MODEL`（或对应的 GLM 配置），否则 `chat_node` 调用会因为 `get_required_env` 报错。

- [ ] **Step 2: 启动后端**

```bash
uv run python -m app.server
```

Expected: 终端输出 Uvicorn 启动日志，无报错；`output/agent_checkpoints.sqlite` 文件被创建。

- [ ] **Step 3: 创建一个新 session**

```bash
curl -s -X POST http://127.0.0.1:3000/api/session/new | python3 -m json.tool
```

Expected: 返回 `{"ok": true, "data": {"sessionId": "...", "title": "新对话", "createdAt": "..."}}`，记下这个 `sessionId`。

- [ ] **Step 4: 发一条对话消息**

```bash
curl -s -X POST http://127.0.0.1:3000/api/agent/conversation \
  -H "Content-Type: application/json" \
  -d '{"sessionId": "<上一步的 sessionId>", "message": "帮我想三个关于远程办公的选题方向"}' \
  | python3 -m json.tool
```

Expected: 返回 `{"ok": true, "data": {"reply": "..."}}`，`reply` 是模型给出的具体内容，不是报错信息。

- [ ] **Step 5: 发第二条消息，验证多轮记忆**

```bash
curl -s -X POST http://127.0.0.1:3000/api/agent/conversation \
  -H "Content-Type: application/json" \
  -d '{"sessionId": "<同一个 sessionId>", "message": "把第二个方向展开讲讲"}' \
  | python3 -m json.tool
```

Expected: 回复内容明显围绕"第二个方向"展开，证明模型看到了第一轮的上下文，不是从零开始回答。

- [ ] **Step 6: 读取对话历史**

```bash
curl -s http://127.0.0.1:3000/api/agent/conversation/<同一个 sessionId>/history | python3 -m json.tool
```

Expected: 返回 4 条消息（2 轮 user/assistant），顺序和内容跟上面两步一致。

- [ ] **Step 7: 验证 Session 列表**

```bash
curl -s http://127.0.0.1:3000/api/session/list | python3 -m json.tool
```

Expected: 列表里包含刚创建的 session，且其 `title` 已经从默认的"新对话"自动更新成了第一条消息的前 20 个字（"帮我想三个关于远程办公的选..."），证明 Task 9 里"首条消息自动回填标题"的逻辑生效。

- [ ] **Step 8: 验证现有功能未受影响**

```bash
curl -s http://127.0.0.1:3000/api/session/latest | python3 -m json.tool
curl -s -X POST http://127.0.0.1:3000/api/agent/chat \
  -H "Content-Type: application/json" \
  -d '{"sessionId": "manual-test", "message": "请分析当前热榜，给出内容策略建议"}' \
  | python3 -m json.tool
```

Expected: 两个接口都正常返回，不报错——证明现有的 `/api/agent/chat`（精修/分析）和 `/api/session/latest` 没有被破坏。

- [ ] **Step 9: 停止服务**

```bash
# Ctrl+C 终止 uv run python -m app.server 进程
```

---

## 完成标准

- `uv run pytest tests/ -v` 全部通过。
- Task 10 的 9 个步骤全部按预期返回。
- `git log` 里能看到 Task 1-9 每个任务对应的独立 commit。
