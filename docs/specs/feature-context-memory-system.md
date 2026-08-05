# 功能规范：上下文管理与记忆系统（Context & Memory System）

**版本：** 2.1
**日期：** 2026-08-05
**状态：** 待评审
**作者：** 架构设计
**关联：** `docs/specs/feature-agent-platform-split.md`、`docs/specs/content-creation-pipeline.md`、
`docs/specs/feature-full-agent-upgrade.md`（功能二「长期记忆」已落地）

> **2.0 修订说明**：1.0 版基于本地旧代码撰写（断言"无 user_memories 表"）。
> 远程分支已实现 `full-agent-upgrade.md` 功能二（user_memories 表 + 提取/检索/管理
> API + 设置页面板 + 对话 Badge），`memory_retriever` 节点已挂载图运行开始。
> 2.0 版重新校准：**已实现标 ✅，未实现标 ◻️**，聚焦剩余缺口。
>
> **2.1 修订说明**：评审补充遗漏边界与方案优化——
> ① checkpoint thread 复用后的**并发写冲突**策略（§3.4）；
> ② 上下文预算改为**按 model profile 配置**而非硬编码 8000（§3.2/§3.5）；
> ③ 滚动摘要**增量合并算法 + 失败重试**细化（§3.3）；
> ④ 记忆向量检索需要 **HNSW 索引迁移**，去重依赖相似度查询（§4.2/§4.3/§6）。

---

## 1. 背景与目标

### 1.1 现状盘点（2026-08-05 代码校准）

| 层 | 现有实现 | 状态 |
| :--- | :--- | :--- |
| 对话历史持久化 | `messages` 表 + `parent_message_id` 分支树（`chat_service.py:114` 回溯） | ✅ 正确，但**全量注入**无预算 |
| LangGraph checkpoint | `AsyncSqliteSaver` → `agent_checkpoints.sqlite` | ⚠️ `thread_id = f"{chat_id}_{user_msg.id}"` 每次新建（`chats.py:262`），**checkpoint 未跨请求复用** |
| RAG 知识上下文 | `ContextBuilder` token 预算 + `[S1]` 标签注入 | ✅ 正确，仅聊天链路在用 |
| 长期记忆表 | `user_memories`（`persistence/models/user_memories.py`）+ Alembic 迁移 | ✅ 已实现 |
| 记忆提取 | `memory_service.extract_memories`（LLM 抽取 + 向量化落库） | ✅ 已实现（仅 multi_agent 的 MemoryAgent 调用，**未接入主对话图**） |
| 记忆检索注入 | `memory_retriever.py` 节点（≤200ms，失败不阻断） | ✅ 已实现（`conversation.py` 挂载） |
| 记忆管理 | `/api/memories` GET/DELETE/PUT + 设置页 `memory-panel.tsx` + 对话 Badge | ✅ 已实现 |
| 记忆向量检索 | `retrieve_memories` 用 content LIKE + activation_count 排序（embedding 列未用于检索） | ⚠️ 退化版，未用 pgvector cosine |
| 上下文预算组装 | 无 `ContextComposer`，`chats.py` 全量拼历史 | ◻️ **缺失** |
| 滚动摘要 | 无 `conversation_summaries` 表 | ◻️ **缺失** |
| 隐式记忆 / 风格学习 | 无 StyleLearner | ◻️ **缺失** |
| L3 素材库 | `SourceType` 无 `material` 值 | ◻️ **缺失** |
| 创作衔接（chat→背景摘要） | 无 | ◻️ **缺失** |
| 运行缓存 | `ChatConversationRunService`（30min/200 run） | ❌ 死代码，无调用 |

### 1.2 问题定义

1. **上下文窗口无管理**：历史全量进 prompt，长对话必爆窗口，且旧消息稀释注意力（未解决）
2. **checkpoint 名存实亡**：thread 每次新建，LangGraph 状态延续能力被浪费（未解决）
3. **跨会话记忆**：✅ 已解决显式记忆提取/检索注入；◻️ 向量语义检索、隐式记忆确认、
   风格学习未落地
4. **对话结束提取**：记忆提取只挂在 multi_agent，普通对话结束后不提取（半成品）

### 1.3 目标

在已落地的 L2 记忆基础上补齐：

- **L1 工作记忆**：`ContextComposer` 四层预算组装 + 滚动摘要（核心缺口）
- **L2 长期记忆完善**：向量检索、对话结束提取接入主图、隐式记忆确认流程、风格学习
- **L3 知识记忆**：素材库（`source_type=material`）
- **创作衔接**：chat 讨论 → 文章背景摘要（`content-creation-pipeline` 闭环）

---

## 2. 分层记忆模型总览

```text
┌─────────────────────────────────────────────────────────────┐
│  L3 知识记忆  │ 知识文档 + 素材库（pgvector 混合检索）       │
├─────────────────────────────────────────────────────────────┤
│  L2 长期记忆  │ user_memories：显式事实/隐式偏好/工作习惯    │
│               │ 向量检索 top-K → 注入 System Prompt         │
├─────────────────────────────────────────────────────────────┤
│  L1 工作记忆  │ 会话历史：最近 N 轮全文 + 早期滚动摘要       │
│               │ ContextComposer 按 Token 预算分层裁剪        │
├─────────────────────────────────────────────────────────────┤
│  L0 运行时记忆 │ LangGraph checkpoint：thread 内状态延续     │
│               │ 工具中间结果、分支隔离（可中断恢复）         │
└─────────────────────────────────────────────────────────────┘
```

**写入时机与触发源：**

| 记忆 | 触发 | 写入方 | 状态 |
| :--- | :--- | :--- | :--- |
| L0 运行时 | 每次图运行 | LangGraph checkpointer 自动 | ✅ |
| L1 全文 | 每轮对话 | ChatService 落库（已有） | ✅ |
| L1 摘要 | 每 M 轮 或 token 超阈值 | `SummaryUpdater` 异步 | ◻️ |
| L2 显式 | 对话结束提取 | `MemoryExtractorNode`（已实现 `extract_memories`，**主对话图未接入**） | ◻️ 接入 |
| L2 隐式 | 文档版本 diff 落库后 | `StyleLearnerService` | ◻️ |
| L3 | 文档上传/确认 | IndexingService（已有） | ✅ |

---

## 3. L1 工作记忆：上下文窗口管理 ◻️

> 本节整体为**核心缺口**：当前 `chats.py` 仍全量拼接历史，无预算分层。

**边界约定**：上下文管理负责"本次运行读什么、按什么顺序读"，记忆系统负责"长期存什么"。
上下文管理不写库，只组装只读快照。

### 3.1 上下文来源分类

| 来源 | 注入点 | 优先级（高→低） | 说明 |
| :--- | :--- | :--- | :--- |
| 当前指令 | 用户消息 | 1 | 永不裁剪，始终完整 |
| RAG 证据 | chat 节点 system 块 | 2 | 检索命中才注入，带 `[S1]` 标签 |
| 长期记忆 | chat 节点 system 块 | 3 | top-K 命中注入 `<记忆>` 块 |
| 最近全文 | 消息序列 | 4 | 最近 N 轮完整消息 |
| 滚动摘要 | 消息序列前部 | 5 | 早期历史压缩 |
| 系统 Prompt | system 消息 | 6 | 角色与平台风格，恒定 |

**裁决规则**：发生冲突时按上表优先级裁决——当前指令 > RAG 证据 > 记忆 > 摘要 > 通用知识。

### 3.2 ContextComposer（上下文组装器）

新建 `app/application/context/composer.py`，取代当前 `chats.py:209` 的
全量历史拼接。

```
历史路径（messages 树回溯）
    │
    ▼
ContextComposer.assemble(history, memory_hits, budget)
    │
    ├── 层 A：摘要块   早期历史摘要（conversation_summaries 表）≈ 20% 预算
    ├── 层 B：全文块   最近 N 轮完整消息（默认 6 轮）≈ 60% 预算
    ├── 层 C：记忆块   长期记忆命中 top-K ≈ 10% 预算
    └── 层 D：系统块   System Prompt + RAG 证据 ≈ 10% 预算
    ▼
组装为 LangGraph messages 输入
```

**预算规则：**
- 总预算 `CONTEXT_TOKEN_BUDGET` **按 model profile 配置（2.1 评审）**，不硬编码：
  DeepSeek 上下文窗口远大于 8000，默认 8000 过于保守会过早压缩全文、丢失有效记忆；
  预算进入 `prompts/model_profiles.yml` 的模型规格（如 deepseek-chat 可设 12000），
  `estimate_tokens` 估算逻辑复用 `context_builder.py:19`（CJK ≈ 1 token，其余 4 字符 1 token）
- 超出预算按层裁剪，层内从旧到新截断
- 最近 1 轮用户消息永不裁剪（保证当前问题完整）

### 3.3 滚动摘要（Rolling Summary）

新建表 `conversation_summaries`（见 §6）：

| 字段 | 说明 |
| :--- | :--- |
| chat_id | 所属会话 |
| summary | 语义摘要文本 |
| covered_message_ids | 已覆盖的消息 ID 列表（JSONB） |
| token_count | 摘要估算 token |
| created_at / updated_at | 时间戳 |

**更新策略：**
- 触发：单分支消息数超过 `SUMMARY_EVERY_N_ROUNDS`（默认 8）或历史原始 token 超阈值时
- 算法：`SummaryUpdater` 调用 LLM（复用 Prompt Registry，`prompts/chat/summary.yml`），输入
  旧摘要 + 新增长段，输出更新后的摘要；**摘要只压缩，不删 DB 原文**
- **增量合并（2.1 评审）**：输入 = 旧摘要（若有）+ 上次 `covered_message_ids` 之后的
  新增长段（用消息 `created_at` 定位增量窗口，避免每次全量重算）；40 轮长对话只对
  新段做增量压缩，控制 LLM 调用次数与成本
- **失败重试**：摘要生成失败不阻断对话流；下次触发时以上次 `covered_message_ids`
  为基准重试（指数退避 1 次），成功后推进覆盖窗口
- 执行：异步 `BackgroundTasks`，不阻塞对话流

### 3.4 checkpoint 修复（L0）◻️

- `thread_id` 改为 `chat_id`（当前 `chats.py:262` 为 `f"{chat_id}_{user_msg.id}"`），
  同一会话共享 thread，LangGraph 状态跨请求延续
- 分支隔离：新分支用 `chat_id__{branch_root_message_id}`，通过 `parent_message_id` 判断是否进入既有 thread
- 收益：中断恢复、工具状态延续、消息序列由 checkpoint 维护（DB 仍为权威存储，双写一致性见风险）
- 现状：`multi_agent` / `task_plan` 等长任务当前无 checkpoint 复用，断线即丢进度

**并发写冲突（2.1 评审补录）**：改为共享 thread 后，**同一 chat 两条并发请求会写
同一个 checkpoint thread**，LangGraph checkpointer 无锁，存在 last-write-wins /
半写状态风险。处理方案：
- **每 chat 串行锁**：`chats.py` 维护 `asyncio.Lock`（按 chat_id）串行化同一会话的
  图运行；不同 chat 互不影响
- **run 级隔离兜底**：若串行锁不满足（如需要并行分支），用独立 thread
  `chat_id__{run_id}` 运行并以 DB 为权威重建状态，避免直接并发写同一 thread
- 验收：同一 chat 并发两条消息不产生状态错乱，checkpoint 可正常恢复

### 3.5 预算降级策略

总预算 `CONTEXT_TOKEN_BUDGET`（按 model profile 配置，默认 8000，见 §3.2）不足时，
按以下顺序逐层降级，**永不触碰优先级 1（当前指令）**：

```
① 裁剪摘要块（可完全移除，用"此前有 X 轮对话"一行占位）
② 裁剪记忆块（优先丢弃低 access_count 的命中）
③ 裁剪全文块（从最旧一轮开始，最少保留最近 2 轮 + 当前指令）
④ 裁剪 RAG 证据（保留首个 [S1] 块保证证据非空，对齐 context_builder 规则）
⑤ 系统 Prompt 不裁剪（恒定开销已计入预算）
```

降级动作记录到 SSE `agent.status`（如 `context: summary_dropped`），前端可展示"上下文压缩"提示。

### 3.6 上下文生命周期与分支

- **作用域**：上下文按 `(chat_id, branch_root)` 计算——分支之间上下文互相隔离，
  切换分支即切换摘要与全文回溯起点
- **失效**：摘要随新消息滚动更新，`covered_message_ids` 外推后旧摘要自动覆盖；
  无失效删除（原文永存 DB）
- **跨 Agent 共享（现状校准）**：`MultiAgentState` 作为共享频道，子 Agent 之间只
  传递 `research_report → draft → final_output` 三条产物；各子 Agent 的
  `SubAgentState`（messages/tool_calls/result）相互隔离，单失败不阻断
  （`multi_agent.py`）。演进为子图后保持同约定：只共享最终产物，不共享中间 State。
- **记忆注入范围**：`memory_retriever` 对全部意图注入；采集/规划类任务是否注入
  记忆由意图类型决定（当前实现为全量注入，可优化为仅 chat/writing 类）

### 3.7 创作场景上下文（单次生成）

创作（生成/润色/重写）与 chat 是**两种不同的上下文形态**：

| 维度 | Chat 对话 | 内容创作 |
| :--- | :--- | :--- |
| 上下文形态 | 多轮历史 + 摘要 + 预算 | 单次 Prompt 组装 |
| 历史管理 | ContextComposer + 滚动摘要 | 无需（一次调用即完成） |
| 记忆注入 | MemoryRetriever top-K | **同一个 L2 记忆系统**检索注入 |
| 场景隔离 | `(chat_id, branch_root)` | 按 `source_item_id`（每文章独立 `AnswerDocument`） |

**上下文组装**（增强 `compose_writing_prompt`，composer.py:37）：

```text
点击文章 A 进入创作
    │
    ├─ ① 原文上下文：A 的 title / content / content_mode / 平台（已有）
    ├─ ② 平台与风格：compose_writing_prompt 分层装配（已有）
    ├─ ③ L2 记忆注入：user_memories 检索 top-K（新增，见 §4）
    ├─ ④ 对话背景摘要：chat 中与 A 相关的讨论（新增，见下）
    └─ ⑤ RAG 素材检索：source_type=material 命中（新增，见 §5）
    ▼
    单次 LLM 调用 → 写 AnswerVersion（多版本互不影响）
```

**chat → 创作衔接（对话背景摘要）**：

```text
点击文章 A 进入创作
    ▼
通过 chat_source_items 反向定位：A 出现在哪些 chat 中
    ▼
提取该 chat 中与 A 相关的消息段：
   ├ 采集 A 的时间点附近（采集请求 → 该文章出现）的对话
   └ 用户对 A 的澄清/补充要求（"这个问题的读者是大学生"）
    ▼
LLM 提炼为「文章背景摘要」（≤ 500 token，异步）
    ▼
注入创作 prompt 的可选 User 块（<对话背景>...），降低优先级
```

**隔离保证（对应 A/B/C 互不影响）**：
- 每个创作任务只组装该 `source_item_id` 的上下文，对话背景摘要只取
  与该文章相关的消息段，**不跨文章串扰**
- 背景摘要独立缓存（按 `source_item_id` 缓存，失效条件 = 对话新增了该文章
  相关消息段、最新 `covered_message_id` 前进时增量更新，避免全量重新提炼）

**创作上下文优先级**：
当前指令 > 原文 > 平台风格 > L2 记忆 > 对话背景摘要 > RAG 素材。

**可控性**：
- 设置页开关「创作时参考对话背景」，默认开启，可全局关闭
- 对话背景摘要只读消息，不写入任何记忆表，无副作用

---

## 4. L2 长期记忆系统

### 4.1 记忆类型 ✅

| memory_type | 含义 | 示例 | 来源 | 需确认 |
| :--- | :--- | :--- | :--- | :--- |
| `explicit` | 用户显式告知 | "我的读者是大学生" | 对话提取 | 否 |
| `implicit` | 行为中隐含的偏好 | "删除列表式结尾" | 版本 diff 分析 | **是** |
| `work_pattern` | 工作习惯 | "固定搜索知乎+Reddit" | 对话提取 | 否 |

三类类型已实现（`user_memories.py`），但 `implicit` 无写入路径。

### 4.2 数据模型 ✅（已实现）

表 `user_memories` 已存在（`app/persistence/models/user_memories.py` + 迁移
`20260804_user_memories.py`）：

```python
class UserMemoryModel(Base):
    __tablename__ = "user_memories"
    id: uuid.UUID                     # PK
    workspace_id: str                 # 隔离
    memory_type: str                  # explicit / implicit / work_pattern
    content: Text
    embedding: Vector(1536) | null    # pgvector 可选
    confidence: float                 # 0.0~1.0
    source: str | null                # session_id / 行为事件
    created_at / last_activated_at / activation_count
    Index("ix_user_memories_workspace_type", "workspace_id", "memory_type")
```

**演进缺口（◻️）**：实际模型**无 `status` 字段**（无法承载
`pending_confirmation / active / rejected` 生命周期，隐式记忆确认流程需加列）；
**无向量检索**（`retrieve_memories` 用 content LIKE + activation_count 排序，
embedding 列已存未用于 cosine）。

**向量检索前提（2.1 评审补录）**：改 cosine 前需在迁移中为 `user_memories.embedding`
建立 **HNSW 索引**（`vector_cosine_ops`）；否则语义检索与去重（相似度 > 0.9 的
近似近邻查询）全表扫描，随记忆量增长不可用。现有数据无 embedding 的条目在切换后
自动退化为 LIKE 兜底（与现状一致）。

### 4.3 记忆提取管线（写入）✅ 提取 / ◻️ 接入主图

**现状**：`memory_service.extract_memories(messages, session_id)` 已实现
（LLM 抽取 → `_parse_extraction_json` → 批量向量化 → 落库），Prompt 在
`prompts/memory/extract.yml`。**当前只被 `multi_agent.py` 的 MemoryAgent 调用**，
主对话图运行结束后未提取。

**缺口：**
- 对话图结束后追加异步 `MemoryExtractorNode`（BackgroundTasks，不阻塞 SSE 流）
- **去重缺失**：与已有记忆向量相似度 > 0.9 视为重复（现状每次提取都新增）。
  去重依赖 pgvector cosine 相似度查询（依赖 §4.2 HNSW 索引），阈值与检索共用；
  无 embedding 的旧条目以 content 精确匹配兜底

### 4.4 记忆检索注入（读取）✅ 已实现

**现状**：`memory_retriever.py` 节点已挂载于 `conversation.py` 的
`preprocess → memory_retriever → route_intent`，`retrieve_memories`
（≤200ms `asyncio.wait_for` 超时，失败静默降级）注入 top-K 到
`state.applied_memories`，`chat_node` 拼入 System Prompt。

**注入规则：**
- 记忆命中时在 System Prompt 附加记忆块，明确"用户偏好如下，请优先遵循"
- 冲突时（记忆 vs 当前显式指令）：**当前指令优先**，写入 prompt 规则即可，无需代码特判
- 检索失败静默降级，不阻断对话
- **优化点（◻️）**：检索改为 pgvector cosine（现状 LIKE 退化，需 §4.2 HNSW 索引）；
  命中详情写入 `retrieval_traces`（`trace_type=memory`），对话 Badge 可展开命中详情（见 §9）

### 4.5 隐式记忆：版本 diff 风格学习 ◻️

**现状**：未实现。`AnswerVersion` diff 数据已积累但未利用；
`user_memories` 无 `status` 字段，需先加列才能承载确认流程。

**数据源**：`AnswerVersion` 相邻版本 diff（AI 生成版 vs 用户手动编辑版）。

```
用户保存/打卡后触发（异步）
    │
    ▼
StyleLearnerService
    ├── 取相邻版本对（如 initial_generation → manual_checkpoint）
    ├── 计算 diff（difflib，已有依赖）
    ├── LLM 分析 diff → 提炼风格规则增量 [{rule, evidence, confidence}]
    └── 写入 user_memories（memory_type=implicit, status=pending_confirmation）
    ▼
用户确认 → status=active → 生效
用户拒绝 → status=rejected → 不生效
```

**关键约束**（对齐 `content-creation-pipeline.md` §4.5）：
- 隐式记忆**必须经用户确认**才激活，绝不静默改写风格
- 确认后合并进 `prompts/shared/style_rules` 或用户级 style_rules
- 每篇文档最多分析一次，避免重复提取
- **只学"AI 生成 → 手动编辑"的 diff**：质检一键采纳生成的版本
  （`AIOperation.operation_type=quality_adopt`）归为 AI 生成版，与手动编辑版
  相邻配对时跳过，避免把"AI 改 AI"误判为用户偏好（对齐
  agent-platform spec §4.6）

---

## 5. L3 知识记忆增强 ◻️

**现状**：`SourceType` 目前仅知识文档/URL 等值，无 `material`；素材库未实现。

- 复用现有 `KnowledgeRetrievalService`（BM25 + pgvector + RRF + 重排），不新建
- 扩展 `SourceType`：新增 `material`（用户素材库），写作时按素材检索注入
  （对齐 `content-creation-pipeline.md` §4.2，这是 RAG 正式接入创作主流程的时机）
- 素材写入入口：编辑器内"收藏为素材"按钮 → `knowledge_documents(source_type=material)` + 自动索引
- 检索过滤：写作场景带 `source_type=material` scope，与知识文档区分

---

## 6. 数据模型变更汇总

| 变更 | 表 | 说明 | 状态 |
| :--- | :--- | :--- | :--- |
| 新增 | `user_memories` | L2 长期记忆（§4.2） | ✅ 已建（迁移 `20260804_user_memories.py`） |
| 修改 | `user_memories` | 加 `status` 列（pending/active/rejected，隐式记忆确认流程）；**加 HNSW 向量索引**（`vector_cosine_ops`，§4.2） | ◻️ 需迁移 |
| 新增 | `conversation_summaries` | L1 滚动摘要（§3.3） | ◻️ 未建 |
| 修改 | `messages` | 无需改表；摘要独立存储 | — |
| 修改 | `knowledge_documents` | `source_type` 增加 `material` 枚举值 | ◻️ 需迁移 |
| 修改 | `answer_versions` | 无需改表；diff 分析直接读取 | — |

新增 Alembic 迁移：`migrations/versions/xxxx_context_memory_evolve.py`
（`user_memories` 加 `status` 列 + HNSW 索引、`conversation_summaries` 新表，
无破坏性 DDL）。

---

## 7. Agent 集成方案

**现状（已实现）**：`memory_retriever` 已挂载于 `conversation.py`
（`preprocess → memory_retriever → route_intent`）。

**增量（◻️）：**

```text
START → preprocess
    → memory_retriever（已实现，L2 检索注入）
    → route_intent
    ├── parse_url → normalize → build_response
    ├── task_plan（已实现）
    ├── multi_agent（已实现）
    └── knowledge_decision
        → retrieve_knowledge（L3）
        → chat（合并记忆块 + RAG 证据块 + 上下文预算）
    → END
    ↘ memory_extract（新增，L2 写入，BackgroundTasks）   ← 新
```

- `MemoryRetrieverNode`：✅ 已实现，无检索结果则跳过
- `MemoryExtractorNode`：◻️ 新增，异步任务，挂 BackgroundTasks，不进 SSE 主流程
  （现状仅 multi_agent 的 MemoryAgent 调用 `extract_memories`）
- 上下文组装：◻️ 移到 `ContextComposer`，`chats.py` 不再手拼历史

---

## 8. API 设计

**已实现**（`app/api/routes/memories.py`）：

| 方法 | 路径 | 说明 | 状态 |
| :--- | :--- | :--- | :--- |
| GET | `/api/memories` | 记忆列表 | ✅ |
| PUT | `/api/memories/{id}` | 编辑记忆内容 | ✅ |
| DELETE | `/api/memories/{id}` | 删除单条 | ✅ |
| DELETE | `/api/memories` | 一键清空 | ✅ |

**缺口（◻️）：**

| 方法 | 路径 | 说明 |
| :--- | :--- | :--- |
| POST | `/api/memories` | 手动新增记忆 |
| POST | `/api/memories/{id}/confirm` | 确认隐式记忆（pending → active，合并风格规则） |
| POST | `/api/memories/{id}/reject` | 拒绝隐式记忆（→ rejected） |
| GET | `/api/memories/pending` | 待确认的隐式记忆（前端红点提示） |

---

## 9. 前端 UI 需求

**已实现**：设置页 `memory-panel.tsx`（记忆列表 + 删除/清空）、对话 `memory-applied-badge.tsx`（已应用 N 条）。

**增量（◻️）：**
- 设置页记忆管理补齐：手动新增、**隐式记忆待确认队列**（内容 + 证据 diff + 采纳/拒绝按钮）
- **对话 Badge 扩展**：可展开命中详情（记忆条目 + 相似度 + 来源，数据来自
  `retrieval_traces` 的 memory 类型）
- **编辑器**：新增「收藏为素材」按钮，跳转知识库素材分类
- **长对话提示**：上下文预算接近上限时展示压缩提示

---

## 10. 实现优先级与路线图

| Phase | 内容 | 验收标准 |
| :--- | :--- | :--- |
| **已实现** | `user_memories` 表 + 提取/检索/管理 + 对话 Badge + MemoryAgent | `full-agent-upgrade` 功能二 |
| **P0** | ContextComposer + checkpoint thread_id 修复 + 滚动摘要 | 40 轮长对话 token 不超预算；同会话中断后状态可续 |
| **P1** | 记忆提取接入主对话图 + 向量检索 + 手动新增 + **创作上下文衔接** | 普通对话结束自动沉淀记忆；创作时模型能感知用户偏好与对话背景 |
| **P2** | 隐式记忆：`status` 列 + 版本 diff 风格学习 + 确认流程 | 用户改稿后出现待确认记忆；确认后新生成体现偏好 |
| **P3** | L3 素材库 + 写作时素材检索注入 | 编辑器收藏素材，写作可引用 [S1] 素材 |

### P0 验收细节

- [ ] 40 轮对话的历史注入 token 恒 ≤ `CONTEXT_TOKEN_BUDGET`（按 model profile）
- [ ] 最近 1 轮用户消息完整保留
- [ ] 摘要覆盖 ≥ 全部早期历史（covered_message_ids 完整）；增量合并不重复计算已覆盖段
- [ ] 同一 chat 的连续两次请求共享 checkpoint thread（状态可续）；**并发两条消息不产生状态错乱**（§3.4 串行锁）
- [ ] 现有 SSE 流式链路回归通过

---

## 11. 依赖与风险

| 风险 | 影响 | 应对 |
| :--- | :--- | :--- |
| checkpoint 与 DB 双写不一致 | 分支/恢复时状态错乱 | 以 DB messages 为权威，checkpoint 仅作运行态缓存；恢复时从 DB 重建 |
| 摘要压缩丢失关键信息 | 早期上下文失真 | 只压缩寒暄/重复内容；覆盖消息 ID 可回溯原文 |
| 记忆检索噪声 | 注入无关记忆干扰回答 | top-K 限制 + access_count 权重 + 相似度阈值 |
| 隐式记忆误判 | 风格被错误改变 | 一律 pending_confirmation，人工确认兜底 |
| 记忆隐私 | 用户敏感信息持久化 | 全本地存储；设置页一键清空；确认时才激活隐式记忆 |
| 提取 LLM 开销 | 每轮额外调用 | 提取走异步后台 + 批量轮次触发，不阻塞主流程 |

---

## 12. 技术架构影响评估

| 组件 | 当前状态 | 变化后 |
| :--- | :--- | :--- |
| `chats.py` 历史拼接 | 全量注入（`chats.py:262` thread 每次新建） | 改用 `ContextComposer.assemble()`；thread_id 改为 chat_id + 每 chat 串行锁（§3.4） |
| `conversation.py` | 已含 memory_retriever | + memory_extract（BackgroundTasks） |
| `state.py` | ChatAgentState 含 `applied_memories` | + 上下文组装结果字段 |
| `persistence/models/` | `user_memories` 已建（9+ 张表） | + `conversation_summaries`；`user_memories` 加 `status` 列 + **HNSW 索引** |
| `application/` | `memory_service.py`、`memory_retriever.py` 已有 | + `context/composer.py`、`summary_updater.py`、`style_learner_service.py`、创作背景摘要 |
| `prompts/` | `memory/extract.yml`、`memory/retrieve.yml` 已有 | + `chat/summary.yml`、写作背景摘要片段 |
| `infrastructure/knowledge/` | embedding/retrieval | 复用 embedding 通道；记忆检索改 pgvector cosine（HNSW 索引）+ 相似度去重；命中写入 `retrieval_traces`（memory 类型） |
| `api/routes/` | `memories.py` 已挂载 | + confirm/reject/pending 端点 |
| 前端 | `memory-panel.tsx`、`memory-applied-badge.tsx` 已有 | + 待确认队列、Badge 命中详情、素材收藏、创作背景开关 |
