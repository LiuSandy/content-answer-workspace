# Chat Collect Result Rendering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reliable Chat conversation run flow and render platform collect results with the final AI reply as one assistant task-result message.

**Architecture:** Add a backend in-memory `ChatConversationRunService` with per-run event logs, standard SSE replay, cancellation, and background ConversationGraph execution. Expose thin FastAPI run endpoints beside the legacy Chat stream route, then migrate the Chat page to an EventSource client that restores in-progress runs and assembles AI text plus platform collect results into one assistant task message.

**Tech Stack:** Python 3.11+, FastAPI, LangGraph, Pydantic v2, React 19, TypeScript, Vite, Tailwind CSS v4, Zustand, Bun, `uv run pytest`, `bun run typecheck`.

---

## 功能概述（Overview）

本计划实现 [docs/specs/feature-chat-collect-result-rendering.md](../specs/feature-chat-collect-result-rendering.md) 中定义的 Chat 采集结果任务消息渲染和 Chat 可靠 SSE 流式接口。

当前 Chat 平台采集任务会拆成工具过程、采集卡片、最终回答三类同级消息，且 `/api/agent/conversation/stream` 仍是旧式 `fetch + ReadableStream` data-only SSE 协议。本计划交付两个配套能力：

- 后端新增 Chat 对话运行 run：创建后后台执行，标准 `id/event/data` SSE 订阅，支持 `Last-Event-ID` 和 `?lastEventId=` 补发。
- 前端把同一轮 Chat 运行中的 AI 文本、平台采集结果、导入操作组合成一条 assistant 任务结果消息。

## 目标（Goal）

交付一个可验证的 Chat 两阶段流式流程：前端先创建 `runId`，再通过 `EventSource` 订阅标准 SSE 事件；服务端缓存业务事件并支持断线或刷新恢复。Chat 列表中平台采集结果与最终 AI 回答必须作为同一条 assistant 任务结果消息渲染，并支持勾选、全选、打开原链接、展开收起和导入工作台。

## 范围（Scope）

会修改：

- 新增 Chat 对话运行 service、route 和 route/service 测试。
- 新增或复用标准 SSE formatter，不破坏旧 data-only SSE。
- 调整 Chat 历史重建，使平台采集结果附着到最终 assistant 消息。
- 扩展前端 Chat 类型、API、EventSource 客户端和 sessionStorage 恢复状态。
- 调整 Chat 页面发送、恢复、错误、取消和消息组装逻辑。
- 新增任务结果消息组件和 inline 采集结果操作区。
- 新增前端纯函数测试和必要的后端回归测试。

不会修改：

- 平台采集工具的采集逻辑。
- 工作台单条回答生成 job 的既有语义。
- 回答精修、热榜分析、批量生成、润色等其它旧流式接口。
- URL 导入、主题采集、热榜页面的业务行为。
- Chat 结果区搜索框、平台筛选、分组筛选功能。
- 引用来源、分析结构、普通工具日志的专用格式化。

## 技术栈（Tech Stack）

- 后端：Python 3.11+、FastAPI、`StreamingResponse`、`asyncio.Lock`、`asyncio.Condition`、dataclasses、Pydantic v2、LangGraph、`uv run pytest`
- 前端：React 19、TypeScript、Vite、Tailwind CSS v4、Zustand、TanStack Query、Bun
- 验证：`uv run pytest ...`、`cd frontend && bun test ...`、`cd frontend && bun run typecheck`

## 涉及文件（Files）

- Create: `app/application/chat_conversation_run_service.py`
  - 管理 `ChatConversationRun`、`ChatSseEvent`、事件缓存、状态、取消、TTL 清理和后台 ConversationGraph 执行。
- Modify: `app/api/routes/agent.py`
  - 挂载 Chat run 创建、查询、订阅、取消接口；保留旧 `/api/agent/conversation/stream`。
  - 调整 `_build_history_messages`，让历史回放与实时任务结果消息一致。
- Modify: `app/api/sse_utils.py`
  - 复用或补齐标准 SSE `sse_named_event`，旧 `sse_event` 保持 data-only 行为。
- Create: `tests/test_chat_conversation_run_service.py`
  - 覆盖 run 生命周期、事件递增、补发、失败、取消、清理。
- Create: `tests/test_chat_conversation_run_routes.py`
  - 覆盖 run 创建、查询、SSE replay、`Last-Event-ID`、`?lastEventId=`、过期、取消和旧接口兼容。
- Create: `tests/test_agent_history_messages.py`
  - 覆盖历史消息重建为 assistant task result。
- Modify: `frontend/src/types/workflow.ts`
  - 增加 Chat run、SSE event、恢复状态和 assistant `collectResults` 类型。
- Modify: `frontend/src/features/workspace/workflow-api.ts`
  - 增加 create/get/cancel Chat run API；旧 `streamConversationMessage` 保留兼容。
- Create: `frontend/src/features/workspace/chat-conversation-run-client.ts`
  - EventSource 订阅、事件解析、sessionStorage 恢复状态读写。
- Create: `frontend/src/features/workspace/chat-collect-result-utils.ts`
  - 消息聚合、选择状态、可见条目、分组统计、工作台条目转换等纯函数。
- Create: `frontend/src/features/workspace/chat-collect-result-utils.test.ts`
  - 覆盖前端纯函数、事件去重、消息聚合和恢复状态。
- Create: `frontend/src/features/workspace/chat-collect-result-panel.tsx`
  - 渲染单个平台采集结果操作区。
- Create: `frontend/src/features/workspace/chat-task-result-message.tsx`
  - 渲染统一 assistant 任务结果消息。
- Modify: `frontend/src/features/workspace/chat-message-thread.tsx`
  - 接入任务结果消息、兼容旧 `collect` role、渲染 live run 状态。
- Modify: `frontend/src/features/workspace/chat-page.tsx`
  - 从旧 `streamConversationMessage` 迁移到 create run + EventSource subscribe；实现刷新恢复、重连状态、错误和取消状态。

## 任务拆分（Tasks）

### Task 1: 建立后端 Chat 对话运行事件服务

**目标：**
用 TDD 新增 `ChatConversationRunService`，提供后台运行所需的 run 状态、事件缓存、递增 id、补发、终态保留和取消语义。

**涉及文件：**
- Create: `app/application/chat_conversation_run_service.py`
- Create: `tests/test_chat_conversation_run_service.py`

**步骤：**

- [ ] Step 1: 写失败测试
  - 文件：`tests/test_chat_conversation_run_service.py`
  - 测试内容：
    - `create_run(session_id, message)` 返回 `pending` 或 `running` run，包含 `id`、`session_id`、`message`。
    - `append_event(run_id, "chunk", {"text": "A"})` 和 `append_event(run_id, "done", {"reply": "AB", "collectResults": []})` 生成 id 1、2。
    - `replay_events(run_id, last_event_id=1)` 只返回 id 2。
    - `heartbeat` 不进入 `events`，不占用业务 id。
    - `mark_error(run_id, "LLM failed")` 进入 `error`，最后事件为 `chat_error`。
    - `cancel_run(run_id)` 进入 `canceled`，最后事件为 `canceled`。
    - `cleanup_expired()` 不清理 `pending` 或 `running`，清理超过保留期的终态 run。
  - 运行命令：`uv run pytest tests/test_chat_conversation_run_service.py -v`
  - 预期结果：失败，失败原因是 `app.application.chat_conversation_run_service` 尚不存在。

- [ ] Step 2: 写最小实现
  - 文件：`app/application/chat_conversation_run_service.py`
  - 实现内容：
    - 定义 `TERMINAL_STATUSES = {"done", "error", "canceled"}`。
    - 定义 `ChatSseEvent` dataclass，字段为 `id`、`event`、`data`、`created_at`，并提供 `to_sse_data()`。
    - 定义 `ChatConversationRun` dataclass，字段为 `id`、`session_id`、`status`、`message`、`events`、`reply`、`collect_results`、`error`、`created_at`、`updated_at`、`expires_at`、`next_event_id`。
    - 定义 `ChatConversationRunService`，使用 `asyncio.Lock` 和 `asyncio.Condition` 保护事件追加和订阅等待。
    - 提供方法：
      - `async create_run(session_id: str, message: str) -> ChatConversationRun`
      - `get_run(run_id: str) -> ChatConversationRun | None`
      - `get_run_snapshot(run_id: str) -> dict | None`
      - `replay_events(run_id: str, last_event_id: int = 0) -> list[ChatSseEvent]`
      - `async append_event(run_id: str, event: str, data: dict) -> ChatSseEvent`
      - `async wait_for_event(run_id: str, after_event_id: int, timeout: float = 15.0) -> list[ChatSseEvent]`
      - `async complete_run(run_id: str, reply: str, collect_results: list[dict]) -> ChatSseEvent`
      - `async mark_error(run_id: str, message: str) -> ChatSseEvent`
      - `async cancel_run(run_id: str) -> ChatConversationRun`
      - `cleanup_expired() -> None`
    - `append_event` 只允许业务事件：`tool_start`、`tool_end`、`collect_result`、`chunk`、`done`、`chat_error`、`canceled`。
    - `complete_run` 必须写入 `done` 事件，`data` 为 `{"reply": reply, "collectResults": collect_results}`。
    - `mark_error` 必须写入 `chat_error` 事件，不使用业务 `error` event。

- [ ] Step 3: 运行测试
  - 命令：`uv run pytest tests/test_chat_conversation_run_service.py -v`
  - 预期结果：全部测试通过。

- [ ] Step 4: 重构
  - 将 snapshot camelCase 转换集中在 `ChatConversationRun.to_snapshot()`。
  - 将终态过期时间设置集中在私有方法 `_mark_terminal(run, status)`。
  - 不引入跨进程存储。

- [ ] Step 5: 再次验证
  - 命令：`uv run pytest tests/test_chat_conversation_run_service.py -v`
  - 预期结果：全部测试通过。

- [ ] Step 6: 提交
  - 提交信息：`feat: add chat conversation run store`

### Task 2: 后端 Chat run 路由和标准 SSE 订阅

**目标：**
新增 Chat run API：创建、查询、标准 SSE 订阅、取消；支持 `Last-Event-ID` 和 `?lastEventId=` 补发，并保留旧 Chat stream 兼容。

**涉及文件：**
- Modify: `app/api/routes/agent.py`
- Modify: `app/api/sse_utils.py`
- Create: `tests/test_chat_conversation_run_routes.py`

**步骤：**

- [ ] Step 1: 写失败测试
  - 文件：`tests/test_chat_conversation_run_routes.py`
  - 测试内容：
    - `POST /api/agent/conversation/runs` 返回 `{"ok": true, "data": {"runId": "...", "status": "pending" 或 "running"}}`。
    - `GET /api/agent/conversation/runs/{runId}` 返回 `status`、`lastEventId`、`collectResults`、`expiresAt`。
    - `GET /api/agent/conversation/runs/{runId}/stream?lastEventId=1` 只补发 id 大于 1 的事件。
    - 带 `Last-Event-ID: 1` 请求头时优先使用请求头。
    - 已完成 run 订阅补发到 `done` 后关闭。
    - 不存在 run 返回统一错误 envelope 或可解析的 SSE `chat_error` 语义，前端能展示“对话运行不存在或已过期，请重新发送”。
    - `DELETE /api/agent/conversation/runs/{runId}` 返回 `canceled`。
    - 旧 `POST /api/agent/conversation/stream` 仍输出 `data: {"type": ...}`，不输出 `event: chunk`。
  - 运行命令：`uv run pytest tests/test_chat_conversation_run_routes.py -v`
  - 预期结果：失败，失败原因是 run 路由尚不存在。

- [ ] Step 2: 写最小实现
  - 文件：`app/api/routes/agent.py`
  - 实现内容：
    - 增加模块级 `_chat_run_service = ChatConversationRunService()`。
    - 增加 `set_chat_conversation_run_service(service)` 测试注入函数。
    - 新增 `POST /api/agent/conversation/runs`，接收现有 `ConversationRequest`，创建 run，启动后台任务，立即返回统一 envelope。
    - 新增 `GET /api/agent/conversation/runs/{run_id}`，返回 snapshot；不存在时返回 `{"ok": false, "error": {"message": "对话运行不存在或已过期，请重新发送"}}`。
    - 新增 `GET /api/agent/conversation/runs/{run_id}/stream`，参数 `lastEventId`，请求头 `Last-Event-ID`，使用标准 `sse_named_event(event.event, event.data, event.id)` 输出。
    - 新增 `DELETE /api/agent/conversation/runs/{run_id}`，调用 `cancel_run`。
    - SSE 订阅逻辑必须先 replay 缺失事件，再等待新事件；遇到 `done`、`chat_error`、`canceled` 后关闭连接。
    - 周期性发送 `heartbeat`，不带 id，不写入 service 事件缓存。
  - 文件：`app/api/sse_utils.py`
  - 实现内容：
    - 保留 `sse_event(payload)` 的旧 data-only 输出。
    - 如果 `sse_named_event` 已存在，只复用；不得改动旧函数行为。

- [ ] Step 3: 运行测试
  - 命令：`uv run pytest tests/test_chat_conversation_run_routes.py -v`
  - 预期结果：全部测试通过。

- [ ] Step 4: 重构
  - 将 `Last-Event-ID` 和 `lastEventId` 解析提取成私有函数，例如 `_parse_last_event_id(header, query)`。
  - 路由只负责 envelope、SSE 包装和 service 调用；后台执行逻辑留给 Task 3。
  - 保持旧 `/api/agent/conversation/stream` 路由不删除。

- [ ] Step 5: 再次验证
  - 命令：`uv run pytest tests/test_chat_conversation_run_routes.py tests/test_generation_job_routes.py -v`
  - 预期结果：全部测试通过，且工作台 generation job 标准 SSE 不受影响。

- [ ] Step 6: 提交
  - 提交信息：`feat: expose reliable chat run routes`

### Task 3: 后台执行 ConversationGraph 并写入 run 事件

**目标：**
让 Chat run 后台执行真实 ConversationGraph，输出 `tool_start`、`tool_end`、`collect_result`、`chunk`、`done`、`chat_error`、`canceled` 事件；SSE 连接断开不取消后台执行。

**涉及文件：**
- Modify: `app/application/chat_conversation_run_service.py`
- Modify: `app/api/routes/agent.py`
- Modify: `tests/test_chat_conversation_run_service.py`
- Modify: `tests/test_chat_conversation_run_routes.py`

**步骤：**

- [ ] Step 1: 写失败测试
  - 文件：`tests/test_chat_conversation_run_service.py`
  - 测试内容：
    - 使用 fake graph 的 `astream_events` 依次返回 `on_tool_start`、`on_tool_end`、`on_chat_model_stream`。
    - 执行 run 后事件顺序为 `tool_start`、`tool_end`、`collect_result`、`chunk`、`done`。
    - `collect_result.data` 包含 `platform`、`topic`、`items`。
    - `done.data.reply` 等于所有 chunk 拼接结果。
    - fake graph 抛异常时 run 状态为 `error`，最后事件是 `chat_error`。
    - run 已取消后，后续 token 不再追加为 `chunk` 或 `done`。
  - 运行命令：`uv run pytest tests/test_chat_conversation_run_service.py -v`
  - 预期结果：失败，失败原因是后台执行方法尚不存在。

- [ ] Step 2: 写最小实现
  - 文件：`app/application/chat_conversation_run_service.py`
  - 实现内容：
    - 新增 `async run_conversation(run_id, graph, update_title)`。
    - 在 service 内读取 run 的 `session_id` 和 `message`，使用 `config = {"configurable": {"thread_id": run.session_id}}`。
    - 执行前查询 `graph.aget_state(config)` 判断是否第一条消息；第一条完成后调用 `update_title(session_id, message[:20])`。
    - 使用 `graph.astream_events({"messages": [{"role": "user", "content": run.message}]}, config=config, version="v2")`。
    - `on_tool_start` 写 `tool_start`，data 为 `{"text": tool_start_step(name), "name": name}`。
    - `on_tool_end` 写 `tool_end`，data 为 `{"text": tool_end_step(name), "name": name}`；如果工具属于 `_COLLECT_TOOLS` 且输出 JSON 有非空 `items`，追加 `collect_result`。
    - `on_chat_model_stream` 将 chunk 文本追加到 `full_reply` 并写 `chunk`。
    - 正常结束调用 `complete_run(run_id, full_reply, collect_results)`。
    - 异常调用 `mark_error(run_id, str(exc))`。
    - 每次追加事件前检查 run 是否已 `canceled`；已取消则停止写入。
  - 文件：`app/api/routes/agent.py`
  - 实现内容：
    - `POST /api/agent/conversation/runs` 创建 run 后用 `asyncio.create_task(_chat_run_service.run_conversation(...))` 启动后台执行。
    - 后台任务不得依赖 SSE 订阅连接。

- [ ] Step 3: 运行测试
  - 命令：`uv run pytest tests/test_chat_conversation_run_service.py tests/test_chat_conversation_run_routes.py -v`
  - 预期结果：全部测试通过。

- [ ] Step 4: 重构
  - 将采集工具 JSON 解析提取为私有函数 `_extract_collect_result(tool_name, raw_output)`，返回 `dict | None`。
  - 该函数只接受 `_COLLECT_TOOLS` 中的工具名，且只在 `items` 非空时返回结果。
  - 不改变平台工具输出结构。

- [ ] Step 5: 再次验证
  - 命令：`uv run pytest tests/test_chat_conversation_run_service.py tests/test_chat_conversation_run_routes.py tests/test_conversation_graph.py -v`
  - 预期结果：全部测试通过。

- [ ] Step 6: 提交
  - 提交信息：`feat: run chat conversations in background`

### Task 4: 历史消息重建为统一 assistant 任务结果

**目标：**
刷新页面或重新进入 Chat 后，历史消息结构与实时 run 完成后的结构一致：平台采集结果附着在最终 assistant 消息的 `collectResults` 上。

**涉及文件：**
- Modify: `app/api/routes/agent.py`
- Create: `tests/test_agent_history_messages.py`

**步骤：**

- [ ] Step 1: 写失败测试
  - 文件：`tests/test_agent_history_messages.py`
  - 测试内容：
    - HumanMessage + AI tool call + collect ToolMessage + final AIMessage 被重建为两条前端消息：user、assistant。
    - assistant 消息包含 `content`、`collectResults`、`steps`。
    - 非平台采集工具仍保留独立 `tool` 消息，再接普通 assistant 消息。
    - collect ToolMessage 有 items 但最终 AI 文本为空时，输出 assistant 消息 `content: ""` 和 `collectResults`。
  - 运行命令：`uv run pytest tests/test_agent_history_messages.py -v`
  - 预期结果：失败，失败原因是当前 `_build_history_messages` 仍输出独立 `collect` role。

- [ ] Step 2: 写最小实现
  - 文件：`app/api/routes/agent.py`
  - 实现内容：
    - `_build_history_messages` 将平台采集工具结果暂存为 `pending_collect_results: list[dict]`。
    - 遇到最终 AI 文本时：
      - 如果存在 `pending_collect_results`，追加一条 `{"role": "assistant", "content": message.content, "steps": pending_steps, "collectResults": pending_collect_results}`。
      - 如果不存在 collect results 但存在 pending steps，先追加 `tool` 消息，再追加普通 assistant。
      - 清空 pending 状态。
    - 遇到新 human 前，如果存在 pending collect results 但没有最终 AI 文本，追加 `content` 为空的 assistant task result。
    - 旧 `collect` role 只作为前端兼容，不再由历史重建主动生成。

- [ ] Step 3: 运行测试
  - 命令：`uv run pytest tests/test_agent_history_messages.py -v`
  - 预期结果：全部测试通过。

- [ ] Step 4: 重构
  - 后端采集结果解析函数与 Task 3 的 `_extract_collect_result` 复用同一逻辑，避免实时和历史解析不一致。
  - 保持 `agent_conversation_history` 响应 envelope 不变。

- [ ] Step 5: 再次验证
  - 命令：`uv run pytest tests/test_agent_history_messages.py tests/test_conversation_graph.py -v`
  - 预期结果：全部测试通过。

- [ ] Step 6: 提交
  - 提交信息：`feat: merge chat collect results in history`

### Task 5: 前端 Chat run 类型、API 和 EventSource 客户端

**目标：**
给前端提供可靠 Chat run 客户端：创建、查询、取消、EventSource 订阅、事件去重、sessionStorage 恢复状态读写。

**涉及文件：**
- Modify: `frontend/src/types/workflow.ts`
- Modify: `frontend/src/features/workspace/workflow-api.ts`
- Create: `frontend/src/features/workspace/chat-conversation-run-client.ts`
- Create: `frontend/src/features/workspace/chat-collect-result-utils.test.ts`

**步骤：**

- [ ] Step 1: 写失败测试
  - 文件：`frontend/src/features/workspace/chat-collect-result-utils.test.ts`
  - 测试内容：
    - `buildChatRunStreamUrl("run-1", 3)` 返回 `/api/agent/conversation/runs/run-1/stream?lastEventId=3`。
    - `saveStoredChatRun` 和 `readStoredChatRun` 能保存并读取 `runId`、`sessionId`、`lastEventId`、`streamingContent`、`toolSteps`、`collectResults`、`status`。
    - 破损 JSON 读取返回 `null`，并清理存储值。
    - `shouldApplyChatRunEvent(2, 2)` 返回 `false`，`shouldApplyChatRunEvent(3, 2)` 返回 `true`。
  - 运行命令：`cd frontend && bun test src/features/workspace/chat-collect-result-utils.test.ts`
  - 预期结果：失败，失败原因是 Chat run client 和相关类型尚不存在。

- [ ] Step 2: 写最小实现
  - 文件：`frontend/src/types/workflow.ts`
  - 实现内容：
    - `ChatCollectItem.url` 改为可选，新增可选 `group`、`category`。
    - `ChatMessage` 增加 `collectResults?: ChatCollectResult[]`，保留 `collectResult?: ChatCollectResult` 兼容旧 role。
    - 新增 `ChatConversationRunStatus = "pending" | "running" | "done" | "error" | "canceled"`。
    - 新增 `CreateChatConversationRunResponse`、`ChatConversationRunSnapshot`。
    - 新增 `ChatConversationRunSseEvent` union，事件包括 `tool_start`、`tool_end`、`collect_result`、`chunk`、`done`、`chat_error`、`canceled`。
  - 文件：`frontend/src/features/workspace/workflow-api.ts`
  - 实现内容：
    - `createChatConversationRun(payload: ConversationPayload)` 调用 `POST /api/agent/conversation/runs`。
    - `getChatConversationRun(runId: string)` 调用 `GET /api/agent/conversation/runs/{runId}`。
    - `cancelChatConversationRun(runId: string)` 调用 `DELETE /api/agent/conversation/runs/{runId}`。
    - 保留 `streamConversationMessage`，但新 Chat 页面不再默认使用。
  - 文件：`frontend/src/features/workspace/chat-conversation-run-client.ts`
  - 实现内容：
    - `buildChatRunStreamUrl(runId, lastEventId)`。
    - `subscribeChatConversationRun(runId, lastEventId, callbacks)`，内部使用 `new EventSource(url)`。
    - 对每个业务 event 解析 `MessageEvent.lastEventId` 和 `event.data`。
    - 暴露 `close()`。
    - `saveStoredChatRun`、`readStoredChatRun`、`clearStoredChatRun` 使用 `sessionStorage`。
    - `shouldApplyChatRunEvent(eventId, lastEventId)` 用于去重。
    - `source.onerror` 只触发 `onRecovering` 回调，不触发业务失败。

- [ ] Step 3: 运行测试
  - 命令：`cd frontend && bun test src/features/workspace/chat-collect-result-utils.test.ts`
  - 预期结果：全部测试通过。

- [ ] Step 4: 重构
  - 与 `generation-job-client.ts` 保持命名风格一致，但不复用 workbench job 的 item/answer 状态。
  - 不修改 `frontend/src/lib/sse.ts`。

- [ ] Step 5: 再次验证
  - 命令：`cd frontend && bun run typecheck`
  - 预期结果：TypeScript 无错误。

- [ ] Step 6: 提交
  - 提交信息：`feat: add reliable chat run client`

### Task 6: 前端任务消息纯函数和采集结果操作区

**目标：**
提供可测试的消息聚合、选择、展开、分组统计、工作台导入转换能力，并渲染 inline 采集结果面板。

**涉及文件：**
- Create: `frontend/src/features/workspace/chat-collect-result-utils.ts`
- Modify: `frontend/src/features/workspace/chat-collect-result-utils.test.ts`
- Create: `frontend/src/features/workspace/chat-collect-result-panel.tsx`

**步骤：**

- [ ] Step 1: 写失败测试
  - 文件：`frontend/src/features/workspace/chat-collect-result-utils.test.ts`
  - 测试内容：
    - `appendConversationTurn` 在存在 `collectResults` 时只追加一条 assistant 消息，包含 `content`、`steps`、`collectResults`。
    - 没有 `collectResults` 时，普通 tool steps 仍作为 `tool` 消息，再接 assistant。
    - 默认只展示前 `DEFAULT_VISIBLE_COLLECT_RESULTS` 条，展开后展示全部。
    - `toggleCollectSelection` 支持选中和取消。
    - `getCollectGroupStats` 只返回只读统计，不过滤列表。
    - 缺少 URL 的条目不影响 `toWorkbenchItems`，其 `url` 为空字符串。
    - 空选择返回空导入目标，导入按钮可禁用。
  - 运行命令：`cd frontend && bun test src/features/workspace/chat-collect-result-utils.test.ts`
  - 预期结果：失败，失败原因是 helper 尚不存在。

- [ ] Step 2: 写最小实现
  - 文件：`frontend/src/features/workspace/chat-collect-result-utils.ts`
  - 实现内容：
    - `DEFAULT_VISIBLE_COLLECT_RESULTS = 5`。
    - `appendConversationTurn(previous, { toolSteps, collectResults, reply })`。
    - `collectItemKey(result, item, index)` 使用 URL 优先，缺少 URL 时使用平台、主题、标题和 index。
    - `getVisibleCollectItems(result, expanded)`。
    - `toggleCollectSelection(selected, key)`。
    - `getSelectedCollectItems(result, selected)`。
    - `getCollectGroupStats(result)` 使用 `group || category`，空值不显示。
    - `toWorkbenchItems(result, selectedItems, now)` 生成 `WorkbenchItem[]`，复用工作台字段。
  - 文件：`frontend/src/features/workspace/chat-collect-result-panel.tsx`
  - 实现内容：
    - Props 为 `{ result: ChatCollectResult }`。
    - 使用本地 `expanded`、`selected`、`importFeedback` state。
    - 使用 `useWorkbenchStore((s) => s.addItems)` 导入。
    - 顶部显示 `已选 X / N 条`、全选/取消全选、导入已选。
    - `selected.size === 0` 时禁用导入按钮。
    - 每条结果显示 checkbox、标题、可用元信息、打开原链接；缺少 URL 时隐藏打开操作。
    - 分组标签只显示统计，不绑定筛选事件。
    - 不渲染搜索框、平台筛选、分组筛选控件。
    - 布局使用 `flex flex-wrap` 和 `break-words`，保证窄屏不重叠。

- [ ] Step 3: 运行测试
  - 命令：`cd frontend && bun test src/features/workspace/chat-collect-result-utils.test.ts`
  - 预期结果：全部测试通过。

- [ ] Step 4: 重构
  - 如果旧 `chat-collect-result-card.tsx` 仍被引用，改为委托 `ChatCollectResultPanel` 或保留兼容导出。
  - 不在 panel 中重新实现工作台去重逻辑，只使用 `addItems` 返回值。

- [ ] Step 5: 再次验证
  - 命令：`cd frontend && bun run typecheck`
  - 预期结果：TypeScript 无错误。

- [ ] Step 6: 提交
  - 提交信息：`feat: add chat collect result panel`

### Task 7: Assistant 任务结果消息组件和消息列表接入

**目标：**
让 `assistant` 消息携带 `collectResults` 时渲染为统一任务结果容器；普通 assistant 文本消息保持 Markdown 气泡。

**涉及文件：**
- Create: `frontend/src/features/workspace/chat-task-result-message.tsx`
- Modify: `frontend/src/features/workspace/chat-message-thread.tsx`
- Modify: `frontend/src/features/workspace/chat-collect-result-utils.test.ts`

**步骤：**

- [ ] Step 1: 写失败测试
  - 文件：`frontend/src/features/workspace/chat-collect-result-utils.test.ts`
  - 测试内容：
    - `appendConversationTurn` 支持同一 assistant 消息携带多个平台结果集合。
    - `appendConversationTurn` 会过滤实时临时步骤 `✍️ 正在整理最终回答…`。
  - 运行命令：`cd frontend && bun test src/features/workspace/chat-collect-result-utils.test.ts`
  - 预期结果：测试失败或暴露 helper 行为不完整。

- [ ] Step 2: 写最小实现
  - 文件：`frontend/src/features/workspace/chat-task-result-message.tsx`
  - 实现内容：
    - Props 为 `{ message: ChatMessage }`。
    - 顶部摘要显示任务完成状态、平台列表、总结果数。
    - 中部使用现有 Markdown 渲染能力显示 `message.content`。
    - 下方对 `message.collectResults ?? []` 渲染 `ChatCollectResultPanel`。
    - 不在该组件内显示搜索框、平台筛选或分组筛选。
  - 文件：`frontend/src/features/workspace/chat-message-thread.tsx`
  - 实现内容：
    - `message.role === "assistant" && message.collectResults?.length` 时渲染 `ChatTaskResultMessage`。
    - 普通 `assistant` 文本消息保持现有气泡。
    - 旧 `message.role === "collect" && message.collectResult` 分支保留兼容，渲染为 `ChatCollectResultPanel`。
    - 支持发送中的 live task result：`streamingContent` 或 `liveCollectResults.length > 0` 时显示临时 assistant task result。

- [ ] Step 3: 运行测试
  - 命令：`cd frontend && bun test src/features/workspace/chat-collect-result-utils.test.ts`
  - 预期结果：全部测试通过。

- [ ] Step 4: 重构
  - 保持 `ThinkingDots`、`ChatToolProcess`、普通 streaming Markdown 的旧行为。
  - 删除未使用 import。

- [ ] Step 5: 再次验证
  - 命令：`cd frontend && bun run typecheck`
  - 预期结果：TypeScript 无错误。

- [ ] Step 6: 提交
  - 提交信息：`feat: render chat task result messages`

### Task 8: Chat 页面迁移到 reliable run 流程和刷新恢复

**目标：**
将 Chat 页面默认发送流程从旧 `streamConversationMessage` 迁移为 `createChatConversationRun + subscribeChatConversationRun`，并实现 run 状态恢复、去重、错误、取消和完成提交。

**涉及文件：**
- Modify: `frontend/src/features/workspace/chat-page.tsx`
- Modify: `frontend/src/features/workspace/chat-message-thread.tsx`
- Modify: `frontend/src/features/workspace/chat-conversation-run-client.ts`
- Modify: `frontend/src/features/workspace/chat-collect-result-utils.test.ts`

**步骤：**

- [ ] Step 1: 写失败测试
  - 文件：`frontend/src/features/workspace/chat-collect-result-utils.test.ts`
  - 测试内容：
    - `applyChatRunEvent` 或等价 reducer 收到 `chunk` 时追加文本并更新 `lastEventId`。
    - 收到重复 id 时不追加文本。
    - 收到 `collect_result` 时追加到 `collectResults`。
    - 收到 `done` 时状态为 `done`，最终 `reply` 覆盖 streaming 内容用于提交。
    - 收到 `chat_error` 时状态为 `error`，不生成最终 assistant 消息。
    - 收到 `canceled` 时状态为 `canceled`。
  - 运行命令：`cd frontend && bun test src/features/workspace/chat-collect-result-utils.test.ts`
  - 预期结果：失败，失败原因是 reducer 尚不存在。

- [ ] Step 2: 写最小实现
  - 文件：`frontend/src/features/workspace/chat-conversation-run-client.ts`
  - 实现内容：
    - 新增纯函数 `applyChatRunEvent(state, event)`，用于 ChatPage 和测试共用。
    - `id <= lastEventId` 的事件直接忽略。
    - `EventSource.onerror` 进入 `recovering`，不进入 `error`。
  - 文件：`frontend/src/features/workspace/chat-page.tsx`
  - 实现内容：
    - `handleSend`：
      - 追加 user 消息。
      - 调用 `createChatConversationRun({ sessionId, message })`。
      - 保存 `{ runId, sessionId, lastEventId: 0, status: "streaming", streamingContent: "", toolSteps: [], collectResults: [] }` 到 sessionStorage。
      - 调用 `subscribeChatConversationRun(runId, 0, callbacks)`。
    - callbacks：
      - `tool_start`、`tool_end` 更新工具步骤。
      - `collect_result` 追加 live collect results。
      - `chunk` 追加 streaming content。
      - `done` 使用 `appendConversationTurn` 生成最终 assistant task result，清理 live 状态和 storage。
      - `chat_error` 显示错误 assistant 消息，不把 partial content 提交为最终消息。
      - `canceled` 显示取消状态，关闭订阅，清理或标记 storage。
      - `onRecovering` 保留已有内容并显示“正在恢复连接”状态。
    - `useEffect`：
      - 页面加载后读取 `readStoredChatRun()`。
      - 若 session 匹配当前 `activeSessionId`，先 `getChatConversationRun(runId)`。
      - `done` 直接用 snapshot 渲染完整任务结果。
      - `running` 或 `pending` 用 snapshot/local state 恢复后继续订阅。
      - `error`、`canceled`、不存在或过期时清理 storage 并提示。
    - `finally` 中刷新 session list query。
    - 不再默认调用旧 `streamConversationMessage`。

- [ ] Step 3: 运行测试
  - 命令：`cd frontend && bun test src/features/workspace/chat-collect-result-utils.test.ts`
  - 预期结果：全部测试通过。

- [ ] Step 4: 重构
  - 将订阅 cleanup 放入 `useRef<ChatConversationRunSubscription | null>`。
  - 切换 session 或组件卸载时关闭旧 EventSource。
  - 保持发送按钮在 `creating`、`streaming`、`recovering` 状态 disabled。

- [ ] Step 5: 再次验证
  - 命令：`cd frontend && bun run typecheck`
  - 预期结果：TypeScript 无错误。

- [ ] Step 6: 提交
  - 提交信息：`feat: use reliable chat conversation runs`

### Task 9: 端到端验证、禁止项检查和回归测试

**目标：**
确认 spec 的渲染、SSE、恢复、错误、取消和兼容验收标准都有对应验证。

**涉及文件：**
- Verify: `docs/specs/feature-chat-collect-result-rendering.md`
- Verify: `app/application/chat_conversation_run_service.py`
- Verify: `app/api/routes/agent.py`
- Verify: `frontend/src/features/workspace/chat-page.tsx`
- Verify: `frontend/src/features/workspace/chat-message-thread.tsx`
- Verify: `frontend/src/features/workspace/chat-task-result-message.tsx`
- Verify: `frontend/src/features/workspace/chat-collect-result-panel.tsx`

**步骤：**

- [ ] Step 1: 运行后端 Chat run 测试
  - 命令：`uv run pytest tests/test_chat_conversation_run_service.py tests/test_chat_conversation_run_routes.py tests/test_agent_history_messages.py -v`
  - 预期结果：全部测试通过。

- [ ] Step 2: 运行后端相关回归测试
  - 命令：`uv run pytest tests/test_conversation_graph.py tests/test_agent_chat_node.py tests/test_generation_job_routes.py tests/test_generation_job_service.py -v`
  - 预期结果：全部测试通过。

- [ ] Step 3: 运行前端纯函数测试
  - 命令：`cd frontend && bun test src/features/workspace/chat-collect-result-utils.test.ts`
  - 预期结果：全部测试通过。

- [ ] Step 4: 运行前端类型检查
  - 命令：`cd frontend && bun run typecheck`
  - 预期结果：TypeScript 无错误。

- [ ] Step 5: 静态检查禁止项
  - 命令：`rg -n "placeholder=\\\"搜索|搜索标题|平台筛选|分组筛选|按平台|按分组" frontend/src/features/workspace/chat-task-result-message.tsx frontend/src/features/workspace/chat-collect-result-panel.tsx frontend/src/features/workspace/chat-message-thread.tsx`
  - 预期结果：无输出，退出码为 1；表示任务结果消息没有搜索框、平台筛选和分组筛选。

- [ ] Step 6: 手动验收 Chat 采集任务消息
  - 操作：启动后端和前端，在 Chat 中发送“需要你帮忙在知乎平台采集一些关于个人网站搭建的问题”。
  - 预期结果：
    - 前端先创建 run，再通过 EventSource 收到标准 SSE 事件。
    - Chat 中最终只出现一条 assistant 任务结果消息承载 AI 总结和采集结果。
    - 结果区默认展示前 5 条。
    - 展开后展示全部，收起后恢复前 5 条。
    - 勾选、全选、取消全选更新已选数量。
    - 选中 0 条时“导入已选”禁用。
    - 点击打开原链接只对有 URL 的条目出现。
    - 点击导入已选后工作台新增对应条目，并显示新增和重复跳过反馈。
    - 结果区没有搜索框、平台筛选、分组筛选。

- [ ] Step 7: 手动验收 Chat SSE 恢复
  - 操作：Chat run 运行中刷新页面。
  - 预期结果：
    - 前端读取本地 `runId` 和 `lastEventId`。
    - 查询 run 状态。
    - run 仍运行时继续订阅并补发缺失事件。
    - run 已完成时直接显示完整任务结果消息。
    - run 不存在或过期时清理本地记录并提示可重新发送。

- [ ] Step 8: 手动验收错误和取消
  - 操作：通过测试环境或 mock 触发 `chat_error` 和 `canceled`。
  - 预期结果：
    - `chat_error` 显示错误，不提交 partial content 为最终 assistant 消息。
    - `canceled` 关闭订阅，显示取消状态，不继续更新该 run。

- [ ] Step 9: 提交
  - 提交信息：`test: verify reliable chat result rendering`

## TDD 执行步骤（TDD Steps）

本计划所有行为变更任务按以下顺序执行：

1. Task 1 先写后端 service 失败测试，再实现 run store。
2. Task 2 先写 route 失败测试，再暴露创建、查询、订阅、取消接口。
3. Task 3 先写后台执行失败测试，再接入 ConversationGraph 事件流。
4. Task 4 先写历史重建失败测试，再合并 collect results 到 assistant 消息。
5. Task 5 先写前端 run client 和 storage 失败测试，再实现 EventSource 客户端。
6. Task 6 先写采集结果 helper 失败测试，再实现 panel。
7. Task 7 先写任务消息聚合测试，再接入消息列表。
8. Task 8 先写 run reducer 测试，再迁移 ChatPage 到 reliable run。
9. Task 9 只做验证，不新增业务行为。

每个任务必须完成：写失败测试、运行并确认失败、写最小实现、运行测试通过、重构、再次验证。实现阶段不得先写业务代码再补测试。

## 验证命令（Verification Commands）

- `uv run pytest tests/test_chat_conversation_run_service.py -v`
  - 预期：Chat run service 生命周期、事件缓存、失败、取消、清理测试通过。
- `uv run pytest tests/test_chat_conversation_run_routes.py -v`
  - 预期：Chat run 创建、查询、SSE replay、取消、旧 stream 兼容测试通过。
- `uv run pytest tests/test_agent_history_messages.py -v`
  - 预期：历史消息重建为 assistant task result。
- `uv run pytest tests/test_chat_conversation_run_service.py tests/test_chat_conversation_run_routes.py tests/test_agent_history_messages.py -v`
  - 预期：Chat run 后端相关测试全部通过。
- `uv run pytest tests/test_conversation_graph.py tests/test_agent_chat_node.py tests/test_generation_job_routes.py tests/test_generation_job_service.py -v`
  - 预期：Agent graph 和工作台 reliable SSE 回归测试通过。
- `cd frontend && bun test src/features/workspace/chat-collect-result-utils.test.ts`
  - 预期：前端 run client、恢复状态、消息聚合、选择、分组统计、导入转换测试通过。
- `cd frontend && bun run typecheck`
  - 预期：TypeScript 无错误。
- `rg -n "placeholder=\"搜索|搜索标题|平台筛选|分组筛选|按平台|按分组" frontend/src/features/workspace/chat-task-result-message.tsx frontend/src/features/workspace/chat-collect-result-panel.tsx frontend/src/features/workspace/chat-message-thread.tsx`
  - 预期：无输出，退出码为 1。

## 提交计划（Commit Plan）

建议每个任务完成并验证后提交一次：

1. `feat: add chat conversation run store`
2. `feat: expose reliable chat run routes`
3. `feat: run chat conversations in background`
4. `feat: merge chat collect results in history`
5. `feat: add reliable chat run client`
6. `feat: add chat collect result panel`
7. `feat: render chat task result messages`
8. `feat: use reliable chat conversation runs`
9. `test: verify reliable chat result rendering`

执行者如果需要合并提交，最终提交必须清楚表达 Chat 可靠 SSE 和采集结果任务消息渲染两个核心改动。

## 风险与回滚（Risks and Rollback）

- 风险：后台 run、SSE 缓存、LangGraph 历史三者状态不一致。
  - 回滚：保留旧 `/api/agent/conversation/stream` 和旧 `streamConversationMessage`，将 ChatPage 默认入口切回旧流。
- 风险：`EventSource.onerror` 被误判为业务失败。
  - 回滚：前端只在收到 `chat_error`、`canceled`、明确 run 查询失败或恢复超时时进入错误或中断。
- 风险：内存缓存无法跨服务重启恢复。
  - 回滚：查询不到 run 时清理本地 storage，提示用户重新发送；不把该场景伪装成恢复成功。
- 风险：实时流式和历史回放聚合逻辑不一致。
  - 回滚：复用同一个 collect result 提取函数，并用 `tests/test_agent_history_messages.py` 锁定历史输出。
- 风险：inline 结果区在大量结果时撑高 Chat 列表。
  - 回滚：默认展示固定为 5 条，必须保留展开和收起。
- 风险：平台工具字段不一致导致渲染异常。
  - 回滚：缺少 URL、摘要、作者、指标、分组时使用空值兜底，不阻塞整条任务消息渲染。
- 风险：旧历史中存在独立 `collect` role。
  - 回滚：前端保留旧 `collect` role 兼容分支，避免历史页面空白。
- 风险：标准 SSE 改动影响工作台 generation job。
  - 回滚：只复用 `sse_named_event`，不改 `sse_event`；运行 `tests/test_generation_job_routes.py` 防止回归。

## 完成标准（Definition of Done）

- [ ] `docs/specs/feature-chat-collect-result-rendering.md` 的所有验收标准 1-27 都有对应实现或验证。
- [ ] Chat 发送默认使用 `POST /api/agent/conversation/runs` + `EventSource` 订阅。
- [ ] Chat SSE 业务事件使用标准 `id/event/data`，并支持 `Last-Event-ID` 和 `?lastEventId=` 补发。
- [ ] `heartbeat` 不占用业务 id，不更新前端 `lastEventId`。
- [ ] `chat_error` 与 `EventSource.onerror` 语义分离。
- [ ] 页面刷新后可恢复运行中 run，已完成 run 可直接显示最终任务结果。
- [ ] 实时流式完成后，平台采集结果和最终 AI 回答合并为一条 assistant 任务结果消息。
- [ ] 历史回放后，平台采集结果和最终 AI 回答仍合并为一条 assistant 任务结果消息。
- [ ] 普通 assistant 文本消息仍按 Markdown 气泡渲染。
- [ ] 非平台采集工具结果不进入 collect result panel。
- [ ] 结果区无搜索框、平台筛选控件、分组筛选控件。
- [ ] 结果区支持勾选、全选、取消全选、打开原链接、展开、收起和导入已选。
- [ ] 后端 Chat run、历史重建、Agent graph、工作台 generation job 回归测试通过。
- [ ] 前端纯函数测试和 `bun run typecheck` 通过。
- [ ] 用户确认视觉、恢复和导入交互符合 spec。
