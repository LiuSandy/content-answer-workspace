# ChatAgentState 分析

> 基于代码实测（2026-08-16）。定义位于 `app/state.py:12-65`（TypedDict），
> 遗留别名 `AgentState = ChatAgentState`（:74）。它是 **chat 对话图**
> （`StateGraph(ChatAgentState)`，chat/graph.py:81）的共享状态 schema，
> 同时随 AsyncSqliteSaver 序列化进 checkpoint（server.py:71-87 白名单）。
>
> 设计原则（state.py:1-4）：**只保存本次图运行需要的数据**，不保存编辑器内容、
> 历史版本和凭证。

## 0. 全景

```text
chats.py 流式入口 / context.compose_run_inputs（组装输入）
        ↓
ChatAgentState（15 节点读写的共享黑板）
  ├─ preprocess        重置意图/HITL/采集字段 + 提取 URL
  ├─ route_intent      写入 intent 组
  ├─ memory_retriever  写 applied_memories
  ├─ knowledge_decision/retrieve_knowledge  写 RAG 组
  ├─ task_plan/multi_agent（借自 orchestrator）  写结果组
  ├─ platform_collect  写 platform_collect_result
  ├─ chat/chat_tools/hitl_decision  ReAct 环路 + interrupt
  └─ parse_url → normalize_and_persist → build_response  写采集组
        ↓
checkpoint（output/agent_checkpoints.sqlite，msgpack 白名单序列化）
        ↓
chats.py 运行后 aget_state 读 snapshot.values → 落库/SSE
```

字段按声明分为 **9 组**，下表逐组给出「写入 → 读取」链路与活跃度
（活跃度依据 app/ 内实际读写，详见 §3）。

## 1. 字段清单与读写链路

### 1.1 输入组（请求带入）

| 字段 | 类型 | 写入 | 读取 | 活跃度 |
|---|---|---|---|---|
| `chat_id` | str | context.py:38、chats.py:494 | tool_nodes.py:24,30,52,57、retrieve_knowledge.py:58 | ✅ 活跃 |
| `user_message_id` | str | context.py:39、chats.py:495 | **无读取** | ⚠️ 只写（落 checkpoint 留档） |
| `user_message` | str | context.py:40、chats.py:496 | preprocess/route_intent/memory_retriever/retrieve_knowledge/graph.py:45/task_plan/execute 等十余处 | ✅ 高频活跃 |

### 1.2 意图组（route_intent 产出，preprocess 每轮重置）

| 字段 | 写入 | 读取 | 活跃度 |
|---|---|---|---|
| `intent` | preprocess.py:13 重置；route_intent.py:35 等 7 处 | graph.py:30（路由）、chats.py:545,585,695,708（snapshot） | ✅ 核心 |
| `intent_confidence` | route_intent.py:37 等 | 无（仅测试 test_intent_eval.py:104） | ⚠️ 只写 |
| `intent_reason` | route_intent.py:38 等 | 无 | ⚠️ 只写 |
| `intent_platform` | route_intent.py:39 等 | platform_collect.py:48,87 | ✅ 活跃 |
| `intent_query` | route_intent.py:40 等 | platform_collect.py:49,88 | ✅ 活跃 |
| `intent_limit` | route_intent.py:41 等 | platform_collect.py:99 | ✅ 活跃 |
| `intent_sort` | route_intent.py:42 等 | platform_collect.py:104 | ✅ 活跃 |
| `knowledge_mode`（与意图一并产出） | route_intent.py:36 等 | route_intent.py:48（读上轮）、graph.py:44,56、retrieve_knowledge.py:26 | ✅ 核心（strict 拒答依据） |

意图路由值：`_route_after_intent`（graph.py:29-39）按 `intent ∈ {parse_url, task_plan, multi_agent}` 分流；`platform_collect` 由 `has_platform_search_route`（platform_collect.py:45-51，基于 intent_platform+intent_query+工具存在）独立判定，**不依赖 intent 值**。

### 1.3 采集组（URL 解析链与工具）

| 字段 | 写入 | 读取 | 活跃度 |
|---|---|---|---|
| `extracted_urls` | preprocess.py:12 | tool_nodes.py:19、route_intent.py:70,74 | ✅ 活跃 |
| `platform_collect_result` | preprocess.py:20 重置；platform_collect.py:135 | chats.py:611（落库 source_list） | ✅ 活跃 |
| `tool_result` | preprocess.py:21 重置；tool_nodes.py:21,38,67 | tool_nodes.py:51,88-102 | ✅ 活跃 |
| `response_payload` | preprocess.py:23 重置；tool_nodes.py:86,106,108 | chats.py:546,721-730（兼容 dict/对象两形态） | ✅ 活跃 |
| `collection_request` | 仅 preprocess.py:24 置 None | 无实际读写 | ❌ 死字段 |
| `error` | 仅 preprocess.py:22 置 None | tool_nodes.py:79-84（build_response error 分支） | ❌ 死字段：全仓无节点构造 AgentError，该分支不可达 |

### 1.4 复合任务/多 Agent 结果组

| 字段 | 写入 | 读取 | 活跃度 |
|---|---|---|---|
| `task_plan_result` | orchestrator/nodes/task_plan.py:43,56 | runtime.py:107（SSE task_plan.created）、chats.py:697 | ✅ 活跃 |
| `multi_agent_result` | orchestrator/nodes/execute.py:37,48 | runtime.py:122（SSE multi_agent.status）、chats.py:710 | ✅ 活跃 |

### 1.5 RAG 组

| 字段 | 写入 | 读取 | 活跃度 |
|---|---|---|---|
| `rag_decision` | graph.py:46（knowledge_decision_node） | graph.py:50（路由） | ✅ 核心 |
| `decision_reason` | graph.py:46 | retrieve_knowledge.py:56（TraceService） | ✅ 活跃 |
| `retrieval_result` | retrieve_knowledge.py:79,86 | graph.py:57（路由）、chat.py:144-148（grounded context）、runtime.py:40（SSE rag.sources） | ✅ 核心 |
| `trace_id` | retrieve_knowledge.py:80,87 | runtime.py:43,56,65 | ✅ 活跃（经 SSE） |
| `fallback_reason` | retrieve_knowledge.py:81,88 | 消费走 retrieval 对象属性（runtime.py:62、chats.py:137），state 键本身无读取 | ⚠️ 冗余 |
| `workspace_id` | **生产无写入**（仅测试构造） | retrieve_knowledge.py:23、memory_retriever.py:24（兜底 "default"） | ⚠️ 恒为 default |
| `owner_id` | **生产无写入** | retrieve_knowledge.py:24（兜底 "default"） | ⚠️ 恒为 default |

### 1.6 记忆组

| 字段 | 写入 | 读取 | 活跃度 |
|---|---|---|---|
| `applied_memories` | memory_retriever.py:27,36,48 | chat.py:153（拼进 system prompt） | ✅ 活跃 |

### 1.7 HITL 组（人工选择）

| 字段 | 写入 | 读取 | 活跃度 |
|---|---|---|---|
| `hitl_pending` | preprocess.py:27（False）、hitl_decision.py:97,103 | 无读取；从未写 True | ❌ 死字段（实际暂停靠 interrupt()，hitl_decision.py:100） |
| `hitl_choice` | preprocess.py:28、hitl_decision.py:97,104 | 无读取（chats.py:566-583 读的是 snapshot.tasks[].interrupts，非此字段） | ❌ 死字段 |
| `hitl_selection` | hitl_decision.py:105（interrupt 恢复值） | 无读取（选择内容经 messages 的 HumanMessage :102 进入下一轮） | ⚠️ 冗余（信息已由 messages 承载） |

HITL 真正生效的机制：`interrupt(payload)` 暂停 → checkpoint 持久化 tasks[].interrupts →
`POST /choices` 以 `Command(resume=selection)`（chats.py:389）原位恢复。这组三个字段是
interrupt 机制之前的旧设计残留。

### 1.8 分支组（roadmap R4）

| 字段 | 写入 | 读取 | 活跃度 |
|---|---|---|---|
| `branch_summary` | chats.py:464-480（SummaryUpdater 读 DB → extra 注入） | chat.py:162-169（注入 system prompt） | ✅ 活跃 |
| `composer_meta` | chat.py:169-171（组装元数据） | 无读取（诊断字段） | ⚠️ 只写（诊断留档） |

## 2. 用在什么地方（使用面）

| 使用点 | 说明 |
|---|---|
| `StateGraph(ChatAgentState)` | chat/graph.py:81——图的 state schema；节点返回的 partial dict 由 LangGraph 合并 |
| checkpoint 序列化 | server.py:71-87：`ChatAgentState` 与其中 DTO 类型（CollectionRequest/ChatResponsePayload/AgentError/ToolResult/SourceItemDTO/RetrievalResult 等）登记在 `JsonPlusSerializer` msgpack 白名单，整个 state 随 AsyncSqliteSaver 持久化 |
| 运行后 snapshot 读取 | chats.py:542-571：`aget_state` 后读 `intent / response_payload / messages / platform_collect_result / task_plan_result / multi_agent_result` 与 `tasks[].interrupts`，驱动消息落库与 SSE |
| 续跑输入组装 | context.py:18-54：探测 `snapshot.values.get("messages")` 决定增量/全量输入 |
| 节点输入输出 | `runtime.py` 经 astream_events 读取节点输出 dict（retrieval_result/trace_id/task_plan_result/multi_agent_result/messages）转 SSE 事件 |
| 遗留别名 `AgentState` | writer 精修图以它为 schema（writer/graph.py:15,52；fetch_answer/save_answer/apply_instruction），注意该图 app/ 内无调用方 |
| `ConversationState`（state.py:68-70） | 仅 `messages` 单键的兼容壳，**全仓无消费者**（无 StateGraph 使用），纯遗留 |

## 3. 活跃度汇总（维护提示）

| 类别 | 字段 |
|---|---|
| ✅ 核心活跃（路由/上下文依赖） | messages、intent、knowledge_mode、rag_decision、retrieval_result、user_message、chat_id、branch_summary、applied_memories |
| ✅ 活跃（采集/结果/SSE） | intent_platform/query/limit/sort、extracted_urls、platform_collect_result、tool_result、response_payload、task_plan_result、multi_agent_result、trace_id、decision_reason |
| ⚠️ 只写留档（进 checkpoint 但从不读回，下轮被 preprocess 重置） | user_message_id、intent_confidence、intent_reason、composer_meta、fallback_reason(state 键)、hitl_selection |
| ⚠️ 恒为默认（生产无写入者） | workspace_id、owner_id（节点内兜底 "default"；多工作区/多用户时需在入口注入） |
| ❌ 死字段（无有效生产者或消费者） | collection_request、error、hitl_pending、hitl_choice |

另两个相关死值：`intent` Literal 与 `IntentRoute`（dto.py:150）中的 `"collect"`——
规则层不产出、LLM 层产出会被 `_VALID_INTENTS` 过滤为 chat（route_intent.py:25,95）、
路由无分支；runtime.py:86 的 `"collect"` 事件映射同为死代码。平台采集实际由
`has_platform_search_route` 确定性判定。

## 4. 相关文档

- 图结构与节点：`docs/agents-overview.md`
- checkpoint/SSE/消息树机制：`docs/core-mechanisms.md`
- HITL 子图化设计：`docs/superpowers/specs/2026-08-14-agent-subgraphs-design.md`
