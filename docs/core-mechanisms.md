# 核心机制分析：LangGraph / Checkpoint / SSE / 乐观锁 / 消息树

> 基于代码实测（2026-08-16），所有结论附 `文件:行号`。

## 1. LangGraph 用了哪些组件

### 1.1 组件清单

| 组件 | 用途 | 位置 |
|---|---|---|
| `StateGraph` / `START` / `END` | 五个图的构建 | chat/orchestrator/researcher/writer/reviewer 各自 `graph.py` |
| `ToolNode` + `tools_condition`（prebuilt） | ReAct 工具环路 | `app/agents/chat/graph.py:25,73,96` |
| `add_messages` reducer + `Annotated` | messages 状态合并 | `app/state.py:8,19,70`（全仓唯一 reducer，子 Agent state 均为普通 TypedDict） |
| `interrupt(payload)` | HITL 原生暂停 | `app/agents/chat/nodes/hitl_decision.py:15,100` |
| `Command(resume=...)` | 从 interrupt 原位恢复 | `app/api/routes/chats.py:11,389` |
| `astream_events(version="v2")` | 流式事件规范化 | `app/agents/_shared/runtime.py:156`、`chat_conversation_run_service.py:193-197` |
| `ainvoke` | 编译图执行 | orchestrator/graph.py:60、researcher:40、writer:35、reviewer:43 |
| `aget_state` | checkpoint 快照探测 | `app/context.py:34`、`chats.py:542` 等 |
| `BaseCheckpointSaver` | 类型注解（checkpointer 注入） | `app/agents/chat/graph.py:4,79,155` |

未使用：`MessageGraph`、`Send`（map-reduce）、`RemoteGraph`。

### 1.2 图结构与 compile 方式

| 图 | 节点 | compile |
|---|---|---|
| **chat**（顶层对话图） | 15 个节点：preprocess→memory_retriever→route_intent，条件路由到 knowledge_decision / retrieve_knowledge / strict_refusal / task_plan / multi_agent / platform_collect / hitl_decision / chat / chat_tools(ToolNode) / parse_url / normalize_and_persist / build_response；4 处 `add_conditional_edges`（意图路由 104-114、RAG 决策 116-126、工具环路 138-142） | `graph.compile(checkpointer=checkpointer)`（chat/graph.py:150）——**唯一带 checkpointer 的图** |
| **orchestrator**（父图） | generate_plan→assign_tasks→(条件)→researcher→writer→reviewer→memory→finalize；researcher/writer/reviewer 是**已编译子图直接作节点**（23-25 行） | `compile()` 无 checkpointer（:40），模块级单例（:43） |
| **researcher** | prepare_tasks→(条件)→execute_tasks→build_report | `compile()`（:32），单例（:35） |
| **writer** | prepare_prompt→generate_draft→finalize_draft；另有请求级 `build_refinement_graph(session_svc)`（functools.partial 注入依赖，:48-62）——**app/ 内无调用方，遗留代码** | `compile()`（:27,62），单例（:30） |
| **reviewer** | prepare_review→run_review→(条件: finalize_review / preserve_draft)→END | `compile()`（:35），单例（:38） |

要点：chat 图进入多 Agent 时（`multi_agent_node`→`orchestrator_graph.ainvoke`）**不带 config/thread_id**，orchestrator 无持久化，中断即丢；多 Agent 结果以普通消息回写 chat 图。

## 2. Checkpoint 怎么配置的

### 2.1 配置（`app/bootstrap/lifecycle.py` lifespan）

- **Saver**：`AsyncSqliteSaver.from_conn_string(output/agent_checkpoints.sqlite)`（server.py:38 路径定义，84-87 构建）。
- **Serializer 白名单**（server.py:71-83）：`JsonPlusSerializer(allowed_msgpack_modules=[...])`，白名单显式列出：
  `CollectionRequest` / `ChatResponsePayload` / `AgentError` / `ToolResult` / `SourceItemDTO`（+ 整个 `app.shared.dto`）、`RetrievalResult` / `RetrievalRequest`、`ChatAgentState`（`app.modules.conversation.agent.state`）、`asyncpg.pgproto.pgproto`。
  **新增进入 checkpoint 的 DTO 时必须同步此白名单**（否则反序列化失败）。
- **挂载**：仅 chat 图——server.py:87 → `build_conversation_graph`（chat/graph.py:155 兼容别名）→ `compile(checkpointer=...)`（:150）。生命周期由 `async with` 管理，无手动 close。
- 测试统一用 `langgraph.checkpoint.memory.MemorySaver`（test_hitl_graph.py:12 等 5 个文件）；app/ 内无内存 saver。

### 2.2 thread_id 规则与续跑（分支 checkpoint）

- `branch_thread_id = f"{chat_id}_{branch_root_message_id}"`（`app/context.py:13-15`）；branch_root 取分支路径最早消息（chats.py:62-64 `_branch_root_of`）。**同一分支复用同一 thread_id**。
- `compose_run_inputs`（context.py:18-54）先 `aget_state` 探测：**有 checkpoint → 只传增量用户消息**（:45-47）；**无 → 从 DB 重建完整分支历史**（:48-52）。config 另带 `recursion_limit`（chats.py:391,501）。
- HITL 恢复：`POST /api/chats/{id}/choices`（chats.py:313-418）以 choice_request 为叶子回溯出 branch_root（:385-386）→ 同一 thread_id → `Command(resume=selection)`（:389）原位恢复。

## 3. SSE 推了哪些事件

封装层 `app/platform/http/sse.py`：`sse_named_event(event, data)`（标准 `event:`/`data:`/可选 `id:`）与 `make_sse_response`（`text/event-stream`、`no-cache`、`X-Accel-Buffering: no`）。事件名与载荷由各模块路由生成器定义：

### 3.1 对话主链路（`POST /api/chats/{id}/messages/stream`，chats.py:423-788）

| 事件 | data 载荷 | 用途 | 前端消费 |
|---|---|---|---|
| `run.started` | `{runId, chatId}` | 流开始 | editor 面板用；chat 面板不消费 |
| `agent.status` | `{status: routing_intent\|generating}` | 节点状态 | chat-panel.tsx:362 |
| `tool.started` | `{tool_type: parse_url\|collect}` | 工具开始 | chat-panel.tsx:368 |
| `rag.sources` | `{sources[], traceId}` | RAG 命中来源（受 `RAG_SOURCE_DISPLAY` 开关） | chat-panel.tsx:395 |
| `rag.fallback` | `{reason, traceId}` | 证据不足降级 | chat-panel.tsx:399 |
| `task_plan.created` | `{planId, goal, status, preview}` | 任务计划创建 | chat-panel.tsx:374 |
| `multi_agent.status` | `{status, agents[], finalContent}` | 多 Agent 进度 | chat-panel.tsx:378 |
| `message.delta` | `{delta}` | 流式文本增量 | chat-panel.tsx:389 |
| `agent.error` | `{errorCode: agent_timeout, message}` | 超时稳定终态 | chat-panel.tsx:401 |
| `choice.requested` | `{type: choice_request, question, options[3], context}` | HITL 中断请求选择 | 前端**不按事件名消费**，按 `messageType === "choice_request"` 渲染卡片 |
| `source.list.completed` | `{tool_type, total_found, items[]}` | 采集结果落库通知 | chat-panel.tsx:392 |
| `run.completed` | `{runId}` | 正常结束（不断流，仅 UI 状态） | editor-panel.tsx:379 |
| `run.failed` | `{error_code, message}` | 失败/递归超限终态 | chat-panel.tsx:404、editor-panel.tsx:382 |

事件源规范化器：`run_agent_stream`/`_normalize_event`（`app/agents/_shared/runtime.py:71-141`），消费 LangGraph `astream_events` v2。

### 3.2 其他 SSE 端点

- **HITL 续跑** `POST /api/chats/{id}/choices`（chats.py:313-418）：复用上表事件（`run.started` 带 `resumedFromChoice: true`）。
- **多 Agent** `GET /api/multi-agent/{run_id}/stream`（multi_agent.py:104-121）：`run.started` / `agent.status`（含 agents 明细）/ `run.completed` / `run.interrupted`；每秒 `sleep(1)` 重推 status 充当心跳。
- **任务计划** `POST /api/task-plans/{plan_id}/stream`（task_plans.py:116-165）：`layer.started/completed`、`task.completed/failed`、`plan.interrupted/completed`（**前端未消费**，卡片走轮询 task-plan-api.ts:63）。
- **文档生成/精修/重写**（documents.py:343-555）：`document.delta`、`document.completed`、`review.started/completed`、`rewrite.started`、`run.*`。
- **opportunities.py:122-135**：未走 sse.py 的手工 SSE（`opportunities`/`error` 事件，轮询推送）。

### 3.3 心跳与结束

主链路**无心跳**；防挂靠 `run_agent_stream` 的每事件超时预算 `asyncio.wait_for`（runtime.py:160），超时产出 `agent.error`。前端以流 EOF 终止循环（lib/sse.ts:75），`run.completed` 仅驱动 UI 状态。未接线代码：`chat_conversation_run_service.py` 定义了可恢复 run 缓存（事件集 :17-36），全仓无路由引用。

## 4. 乐观锁代码在哪

机制：`answer_documents.lock_version`（models/documents.py:57，初始 1）+ 写入前比对 `expected_lock_version`，不一致抛 `DocumentConflictError`（contracts/errors.py:46）→ 全局异常处理器映射 **409**（server.py:161）。

| 位置 | 内容 |
|---|---|
| `app/services/document_service.py:318-319` | **核心校验** `_check_lock`：`if doc.lock_version != expected: raise DocumentConflictError(...)`；创建时 `lock_version=1`（:38），每次成功写入自增（:56,110,277） |
| `app/services/document_service.py:49-110` | 自动保存 `save_content` / AI 操作 `apply_operation` 均先 `_check_lock` |
| `app/services/outline_service.py:69-70,144-146,244-247,344-346` | 大纲快照的独立锁校验（confirmed 快照防旧版本覆盖） |
| `app/services/writing_service.py:181-194,259-269` | **冲突自动重试**：捕获 409 后重读最新 `lock_version` 重放一次 |
| `app/services/quality_service.py:223-274`、`version_service.py` | 质检采纳/版本恢复沿用 `expected_lock_version` |
| `app/agents/writer/nodes/{answer_generation,inline_refinement,full_rewrite}.py` | AI 写入路径同样携带并校验（full_rewrite.py:43 直接调 `_check_lock`） |
| `app/api/routes/documents.py:153-182` | `PUT /api/documents/{id}` 入口（DTO 字段 `expectedLockVersion`，contracts/dto.py:302） |
| 前端 | `editor-panel.tsx:243-289`（自动保存带 lockVersion）、:305-326（精修/重写）、`outline-dialog.tsx:87-130`（大纲四操作）；lockVersion 取自 queryClient 缓存最新值避免用旧值（commit ef6a220） |

## 5. 消息树怎么构建的

### 5.1 存储（邻接表）

`messages.parent_message_id`（models/chats.py:65-67）：`UUID FK→messages.id, ondelete="SET NULL"`。单列父指针，无 path 物化、无递归 CTE、无独立 branch 表。消息类型含 `text / source_card / source_list / tool_status / error / choice_request / hitl_selection`（chats.py:58-59,339,360）。

### 5.2 后端构建（`app/services/chat_service.py`）

- 写入：`save_user_message` / `save_assistant_message`（:69-113），`parent_message_id` 直接落库。
- 路径查询 `get_message_path(chat_id, leaf_id)`（:115-162）：取全部消息按时间排序 → 从 leaf 沿 `parent_message_id` 回溯（visited 防环）→ **虚拟父子兜底**：parent 为 NULL 的旧数据虚拟链接到时间线前驱（:149-159，兼容重构前的线性历史）→ reverse 返回根→叶列表。
- 分支 = 同一 parent 下的兄弟消息，无独立服务。

### 5.3 发送/续跑的 branch_root 选择（`app/api/routes/chats.py`）

- `send_message_stream`（:423）：`parentMessageId`（:440-446）→ 保存用户消息 → `get_message_path` 回溯 → `branch_root = 路径第一条消息 id`（:461-462，空历史退化为当前消息）。
- 前端传**当前叶子** = 续跑同分支（thread_id 复用）；传**兄弟的 parent**（编辑重发）= 消息树开新分支（checkpoint 仍延续同 branch_root）。
- `compose_run_inputs`（context.py）据 checkpoint 存在与否传增量/全量（见第 2 节）。

### 5.4 前端（`frontend/src/features/chat/chat-panel.tsx`）

- `resolveParentIds`（:57-89）：平面列表→树，为旧数据补虚拟父指针（assistant 指向前一条；user 按下一条的 DB parent 判断是否分支首）。
- `getActivePathAndInit`（:218-264）：叶子 = 未被任何消息引用为 parent 的消息；默认取最新叶子；从 `activeLeafMessageId` 回溯出渲染序列。
- `activeLeafMessageId`（chat-store.ts）：当前分支锚点——发消息的 parent（:332）、乐观更新临时消息立即设为叶子（:350）、流结束刷新后指向最新真实消息（:452）。
- 兄弟版本切换 `handleSwitchSibling`（:520-548）：同 parent 的 user 兄弟按时间排序 prev/next 移动，`findActiveLeafDescendant` 沿"第一个孩子"下钻到子树叶子；UI 为 `n / total` 箭头（:892-912）。
- 逻辑测试镜像：`chat-logic.test.ts:20-90`。

### 5.5 HITL 选择如何挂树（chats.py:313-418）

```text
user_msg → choice_request(assistant, parent=user_msg)
                       ↓ 用户点选
         hitl_selection(user, parent=choice_request)   ← 幂等：同 parent 同 selection 直接返回(:356-365)
                       ↓ Command(resume) 原位恢复(:389)
         assistant 回复(parent=hitl_selection)          ← 续跑产物(:404-412)
```

选择消息以 choice_request 为叶子回溯 branch_root（:385-386）→ 精确还原暂停时的分支 checkpoint。注意：`SelectionDTO`（dto.py:289-296）是**编辑器文字选区**（InlineRefine 用），与 HITL 无关。
