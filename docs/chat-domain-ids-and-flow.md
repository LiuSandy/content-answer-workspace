# 对话域 ID 详解与「一句话的完整旅程」

> 基于代码实测（2026-08-17）。核心文件：`app/api/routes/chats.py`、`app/context.py`、
> `app/services/chat_service.py`、`app/agents/chat/graph.py`、
> `frontend/src/features/chat/chat-panel.tsx`。

## 第一部分：对话域的 ID 全解

### 1.1 ID 总览表

| ID | 生成方式 | 存储位置 | 生命周期 | 一句话定位 |
|---|---|---|---|---|
| `chat_id` | DB UUID | chats 表 PK | 会话创建到删除 | "哪个会话" |
| `message_id` | DB UUID | messages 表 PK | 消息创建到删除 | "哪条消息"（消息树节点） |
| `parent_message_id` | 引用父消息 | messages 表 FK | 随消息 | "挂在谁下面"（消息树父指针） |
| `branch_root_message_id` | **回溯推导**（非存储） | 运行时计算 | 每次请求内 | "哪条分支"（路径最早消息） |
| `thread_id` | **运行时拼接**（非存储） | checkpoint 表分组键 | 分支终身 | "哪条分支的图状态" |
| `run_id` | 每次请求 `uuid4()` | messages.run_id 列 + SSE + 日志 | 单次请求 | "哪一次运行" |
| `checkpoint_id` | LangGraph 内部 | checkpoint 表版本链 | 每个节点一步 | "运行到哪一步的快照" |

### 1.2 逐个详解

#### chat_id —— 会话实体标识

- 前端路由 `/chat/:chatId`；创建会话时生成（chats 表 UUID PK）。
- 是所有消息、分支、thread 的命名空间：`thread_id` 以它为前缀。

#### message_id / parent_message_id —— 消息树

- 每条消息（user/assistant/tool）落库时生成 UUID；`parent_message_id` 指向父消息
  （models/chats.py:65-67，邻接表单列存树，`ondelete="SET NULL"`）。
- 消息类型（`message_type`）：`text / source_card / source_list / tool_status /
  error / choice_request / hitl_selection`。
- **树的形状由前端决定**：发消息时传 `parentMessageId`（= 当前叶子或编辑消息的父），
  后端原样落库。同一 parent 下的多条 user 消息 = 兄弟版本（分支）。

#### branch_root_message_id —— 分支根（推导值）

- 不存在任何表中：每次请求由 `get_message_path(chat_id, parent_id)` 回溯
  （chat_service.py:115-162，沿 parent 向上 + 旧数据虚拟父兜底），取
  **路径第一条消息的 id**（chats.py:461-462 `_branch_root_of`）。
- 作用：作为 thread_id 的组成部分，让"同一条分支"的所有轮次聚合到同一个
  checkpoint 链上。
- 空历史（会话第一条消息）时退化为当前用户消息 id。

#### thread_id —— LangGraph checkpoint 分组键

```python
branch_thread_id(chat_id, branch_root_message_id)  # app/context.py:13-15
# → f"{chat_id}_{branch_root_message_id}"
```

- **框架按它定位**：运行前恢复哪个 thread 的最新快照、运行中 checkpoint 写到哪条
  版本链、`aget_state` 读哪份状态。
- 设计要点：**以分支为键而不是以 chat 为键**——每条分支独立 checkpoint 链，
  兄弟分支互不污染；HITL 恢复时按 choice_request 回溯出同一 branch_root，
  精确还原暂停现场（chats.py:385-390）。

#### run_id —— 单次运行的追踪键

- 每次流式请求开头 `uuid4()`（chats.py:435；HITL 续跑 :388）。
- 四个用途：
  1. SSE `run.started/run.completed/run.failed` 载荷（前端关联流）；
  2. messages 表 `run_id` 列——本轮产生的所有消息打同一标记（前端去重防重复渲染）；
  3. 日志上下文 `set_log_context(run_id=...)`（:506，贯穿全部日志）；
  4. **后台记忆提取的幂等键**（:753-755，重试不会重复沉淀记忆）。
- 与 thread_id 的关系：**一个 thread 可有多次 run**（每发一次消息就是新 run_id，
  但 thread_id 不变）。

#### checkpoint_id —— 版本链节点（框架内部）

- 每个节点执行完，框架写一条 checkpoint（含 `parent_checkpoint_id` 指向上一条），
  形成 superstep 粒度的版本链。业务代码不直接使用它（自动恢复永远取最新）。

### 1.3 关系图

```text
chat (chat_id)
 ├── 消息树:  user1 ── assistant1 ── user3(编辑重发, 兄弟) ── ...
 │                    └── user2 ── assistant2
 │     (message_id + parent_message_id 邻接表)
 │
 ├── 分支A: root=user1   → thread_id = "{chat_id}_user1"  ← checkpoint 版本链A
 │     run#1 (run_id=aaa): user2 轮
 │     run#2 (run_id=bbb): assistant2 之后的轮次...
 └── 分支B: root=user3   → thread_id = "{chat_id}_user3"  ← checkpoint 版本链B
       run#3 (run_id=ccc)
```

## 第二部分：输入一句话后发生了什么（完整时序）

以用户在已有会话的当前分支叶子处输入「帮我搜一下小红书上关于算法的帖子」为例。

### 阶段 0：前端发起（chat-panel.tsx）

1. `parentMessageId = overrideParentId ?? activeLeafMessageId`（:332）——挂在当前叶子下。
2. 乐观更新：立即插入临时消息 `"temp-user-msg"` 并设为叶子（:335-350）。
3. `lib/sse.ts` 的 `streamPost()` 发起
   `POST /api/chats/{chat_id}/messages/stream`（body: `{content, parentMessageId}`），
   开始逐块解析 SSE。

### 阶段 1：请求准备（chats.py:423-506）

4. 生成 `run_id = uuid4()`，推送 `run.started {runId, chatId}`（:435,438）。
5. 保存用户消息 → **message_id 诞生**，parent = 前端传入的 parentMessageId（:458-460）。
6. 顺带：会话标题若是默认"新对话"，用本消息前 20 字改名（:453-456）。
7. `get_message_path` 回溯父链 → **branch_root = 路径第一条消息 id**（:461-462）。
8. 读分支滚动摘要（R4，尽力而为 :464-471）。
9. `compose_run_inputs`（context.py:18-54）：
   - 拼 **thread_id = `{chat_id}_{branch_root}`**；
   - `aget_state` 探测该 thread 是否已有 checkpoint：
     **有** → inputs 只带本轮 1 条用户消息（增量）；**无** → 带完整分支历史（全量重建）。
10. config = `{thread_id, recursion_limit}`（:501）；绑定日志上下文（:506）。

### 阶段 2：图运行（run_agent_stream → astream_events，:512-539）

11. **框架自动**：按 thread_id 加载 checkpoint 最新快照，恢复完整 state（含历史
    messages；本轮输入组字段被新值覆盖，messages 经 add_messages **追加**）。
12. `preprocess`：提取 URL、清空 15 个瞬态字段（意图/采集/HITL），保留 messages、
    knowledge_mode 等 → 节点完成 → **框架写一条 checkpoint**。
13. `memory_retriever`：检索长期记忆 → applied_memories（失败不阻断）→ 落 checkpoint。
14. `route_intent` 三层识别（规则 → LLM structured output → 校验兜底，低置信降级 chat）
    → 本例判定为平台采集路径（intent_platform=xiaohongshu, intent_query=算法...）。
15. `_route_after_intent` 分流。各路径：
    - **chat**：knowledge_decision（是否 RAG）→ retrieve_knowledge? → chat 节点生成
      （流式 message.delta）→ 有工具调用则 chat_tools → hitl_decision → 回 chat；
    - **parse_url**：parse_url → normalize_and_persist → build_response；
    - **task_plan / multi_agent / platform_collect**：执行后直连 END。
16. 每个节点完成都落一条 checkpoint（版本链延伸；若中途 `interrupt()`，中断快照含
    `tasks[].interrupts` 一并落盘）。
17. 全程 SSE 事件实时透传：`agent.status` / `tool.started` / `rag.sources` /
    `message.delta`（前端逐步拼进聊天气泡）...（:513-539）

### 阶段 3：收尾落库（chats.py:541-757）

18. `aget_state(config)` 读最终快照 values（:542-546）。
19. 按 intent 分支持久化（**assistant 消息的 parent = 本轮 user_msg.id**，树长出一层）：
    - HITL 中断 → 保存 `choice_request` 消息 + 推 `choice.requested` 后 return（:573-584）；
    - chat → 拼接全部 delta 存 `text` 消息（含 ragSources/traceId payload，:585-602）；
      若有平台采集结果再存 `source_list` 消息 + 推 `source.list.completed`（:611-694）；
    - task_plan / multi_agent → 存对应结构化消息（:695-720）；
    - parse_url 链 → 按 response_payload 存（:721-747）。
20. 更新分支滚动摘要（下一轮注入用，R4，:750-751）。
21. 后台调度长期记忆提取（幂等键 = run_id，R5，不阻塞响应 :753-755）。
22. 推 `run.completed {runId}`（:757）→ 流 EOF。
23. 异常兜底：GraphRecursionLimit / 失败 → 存 `error` 消息 + 推 `run.failed`（:759-784）。

### 阶段 4：前端收尾（chat-panel.tsx）

24. 流结束 → `refreshAfterStream` 拉取最新消息树，替换临时消息，把最新真实消息设为
    `activeLeafMessageId`（:452）——本轮结束，树的叶子前移。

### 附：HITL 分支（点击选择后）

```text
user_msg → choice_request（已落库）
用户点选 → POST /api/chats/{id}/choices {messageId, selection}
  → 校验选项合法 + 幂等检查（同 parent 同 selection 直接返回，:356-365）
  → ChatRuntime 并发锁（:367-378）
  → 保存 hitl_selection 消息（parent=choice_request，:380-384）
  → 以 choice_request 为叶子回溯 branch_root（:385-386）
  → thread_id 与暂停时完全一致（:390）
  → Command(resume=selection) 原位恢复（:389）——不重跑意图识别
  → 续跑产物 assistant 消息（parent=hitl_selection，:404-412）
```

## 第三部分：一图流总结

```text
输入"帮我搜一下小红书上关于算法的帖子"
 │
 ├─ run_id 诞生 ──────────── 追踪本次请求（SSE/日志/幂等）
 ├─ message_id(user) 诞生 ── 挂到 parent_message_id 下（消息树 +1 节点）
 ├─ branch_root 推导 ─────── 路径最早消息 id
 ├─ thread_id 拼出 ───────── {chat_id}_{branch_root}（定位 checkpoint 链）
 │
 ├─ [框架] 恢复 thread 最新快照（messages 完整保留）
 ├─ preprocess → memory_retriever → route_intent（每步落 checkpoint）
 ├─ 分流 → platform_collect（或 chat/RAG/ReAct/...）
 ├─ SSE: agent.status → tool.started → message.delta...
 │
 ├─ [框架] aget_state 最终快照
 ├─ message_id(assistant) 诞生 ── parent=user_msg（消息树再 +1）
 ├─ 分支摘要更新 / 后台记忆提取（run_id 幂等）
 └─ run.completed → 前端刷新，叶子前移
```

## 相关文档

- ID 与 checkpoint 机制细节：`docs/core-mechanisms.md`
- 消息树前后端构建：`docs/core-mechanisms.md` §5
- 图与节点：`docs/agents-overview.md`；state 字段：`docs/chat-agent-state.md`
