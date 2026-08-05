# 功能规范：上下文管理与记忆系统（Context & Memory System）

**版本：** 1.0
**日期：** 2026-08-05
**状态：** 待评审
**作者：** 架构设计
**关联：** `docs/specs/feature-agent-platform-split.md`、`docs/specs/content-creation-pipeline.md`

---

## 1. 背景与目标

### 1.1 现状盘点

| 层 | 现有实现 | 问题 |
| :--- | :--- | :--- |
| 对话历史持久化 | `messages` 表 + `parent_message_id` 分支树（`chat_service.py:114` 回溯） | ✅ 正确，但**全量注入**无预算 |
| LangGraph checkpoint | `AsyncSqliteSaver` → `agent_checkpoints.sqlite`（`server.py:75`） | ⚠️ `thread_id = chat_id_user_msg_id` 每次新建，**checkpoint 未跨请求复用** |
| RAG 知识上下文 | `ContextBuilder` token 预算 + `[S1]` 标签注入（`context_builder.py:30`） | ✅ 正确，仅聊天链路在用 |
| 长期记忆 | 无 `user_memories` 表 | ❌ 完全缺失 |
| 风格学习 | `AnswerVersion` 存 AI 版 vs 手动编辑版 | ❌ 数据已积累但未利用 |
| 运行缓存 | `ChatConversationRunService`（30min/200 run） | ❌ 死代码，无调用 |

### 1.2 问题定义

1. **上下文窗口无管理**：历史全量进 prompt，长对话必爆窗口，且旧消息稀释注意力
2. **checkpoint 名存实亡**：thread 每次新建，LangGraph 状态延续能力被浪费
3. **跨会话无记忆**：用户明确告知的偏好、习惯、素材都无法在下次对话复用
4. **风格不学习**：用户每次手动修改都在表达偏好，但系统毫不知情

### 1.3 目标

建立**分层记忆模型**，实现：

- **L1 工作记忆**：上下文窗口管理（全文 + 摘要 + 预算），支撑长对话
- **L2 长期记忆**：跨会话用户记忆（显式 / 隐式 / 工作习惯），自动提取与检索注入
- **L3 知识记忆**：知识库 + 素材库（增强现有 RAG）
- **风格记忆**：从版本 diff 学习用户写作偏好，经确认后生效

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

| 记忆 | 触发 | 写入方 |
| :--- | :--- | :--- |
| L0 运行时 | 每次图运行 | LangGraph checkpointer 自动 |
| L1 全文 | 每轮对话 | ChatService 落库（已有） |
| L1 摘要 | 每 M 轮 或 token 超阈值 | `SummaryUpdater` 异步 |
| L2 显式 | 对话结束提取 | `MemoryExtractorNode` |
| L2 隐式 | 文档版本 diff 落库后 | `StyleLearnerService` |
| L3 | 文档上传/确认 | IndexingService（已有） |

---

## 3. L1 工作记忆：上下文窗口管理

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
- 总预算 `CONTEXT_TOKEN_BUDGET`（默认 8000），超出按层裁剪，层内从旧到新截断
- token 估算复用 `context_builder.py:19` 的 `estimate_tokens`（CJK ≈ 1 token，其余 4 字符 1 token）
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
- 执行：异步 `BackgroundTasks`，不阻塞对话流

### 3.4 checkpoint 修复（L0）

- `thread_id` 改为 `chat_id`（`chats.py:216`），同一会话共享 thread，LangGraph 状态跨请求延续
- 分支隔离：新分支用 `chat_id__{branch_root_message_id}`，通过 `parent_message_id` 判断是否进入既有 thread
- 收益：中断恢复、工具状态延续、消息序列由 checkpoint 维护（DB 仍为权威存储，双写一致性见风险）

### 3.5 预算降级策略

总预算 `CONTEXT_TOKEN_BUDGET`（默认 8000）不足时，按以下顺序逐层降级，
**永不触碰优先级 1（当前指令）**：

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
- **跨 Agent 共享**：Orchestrator 组装一次上下文后透传给子 Agent；
  子 Agent 之间只共享最终上下文快照，不共享各自中间 State（中间结果经工具返回
  写回 DB，避免上下文互相污染）
- **记忆注入范围**：L2 记忆检索只作用于 chat 类意图；parse_url / collect 类
  任务不注入记忆，避免无关上下文干扰采集

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

### 4.1 记忆类型

| memory_type | 含义 | 示例 | 来源 | 需确认 |
| :--- | :--- | :--- | :--- | :--- |
| `explicit` | 用户显式告知 | "我的读者是大学生" | 对话提取 | 否 |
| `implicit` | 行为中隐含的偏好 | "删除列表式结尾" | 版本 diff 分析 | **是** |
| `work_pattern` | 工作习惯 | "固定搜索知乎+Reddit" | 对话提取 | 否 |

### 4.2 数据模型

新建表 `user_memories`（SQLAlchemy 模型 `app/persistence/models/memory.py`）：

```python
class UserMemory(Base):
    __tablename__ = "user_memories"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    owner_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    memory_type: Mapped[str] = mapped_column(String(20), nullable=False)  # explicit/implicit/work_pattern
    content: Mapped[str] = mapped_column(Text, nullable=False)            # 记忆内容
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1536), nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)  # 0.0~1.0
    # 来源溯源
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)  # chat / document_edit / manual
    source_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # 生命周期：active / pending_confirmation / rejected
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    access_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_accessed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
```

### 4.3 记忆提取管线（写入）

**入口**：对话图结束后追加异步 `MemoryExtractorNode`（不阻塞 SSE 流）。

```
对话结束（run.completed 前）
    │
    ▼
MemoryExtractorNode（异步）
    ├── LLM 抽取：从本轮 user/assistant 消息提取显式事实与工作习惯
    │    → 输出 JSON [{memory_type, content, confidence}]
    ├── 过滤：与已有记忆去重（向量相似度 > 0.9 视为重复，仅更新 access_count）
    └── 写入 user_memories（status=active）
```

**Prompt**：`prompts/chat/memory_extract.yml`（Few-shot + JSON Schema 约束）。

### 4.4 记忆检索注入（读取）

**入口**：图运行开始时新增 `MemoryRetrieverNode`（在 preprocess 后）。

```
用户消息
    │
    ▼
MemoryRetrieverNode
    ├── 向量检索 top-K（默认 5，复用 KnowledgeRetrievalService 的 embedding 通道）
    ├── 过滤：access_count 高 + 与当前主题相关 优先
    └── 注入 System Prompt：<记忆>...</记忆> 块，标记来源
    ▼
chat_node（Orchestrator）合并记忆块 + RAG 证据块
```

**注入规则：**
- 记忆命中时在 System Prompt 附加记忆块，明确"用户偏好如下，请优先遵循"
- 冲突时（记忆 vs 当前显式指令）：**当前指令优先**，写入 prompt 规则即可，无需代码特判
- 检索失败静默降级，不阻断对话
- **命中可观测**：命中的 top-K 条目写入 `retrieval_traces`（`trace_type=memory`，
  记录记忆 ID / 内容片段 / 相似度），复用现有 Trace 面板机制；对话顶部 Badge
  可展开查看命中详情（见 §9）

### 4.5 隐式记忆：版本 diff 风格学习

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

## 5. L3 知识记忆增强

- 复用现有 `KnowledgeRetrievalService`（BM25 + pgvector + RRF + 重排），不新建
- 扩展 `SourceType`：新增 `material`（用户素材库），写作时按素材检索注入
  （对齐 `content-creation-pipeline.md` §4.2，这是 RAG 正式接入创作主流程的时机）
- 素材写入入口：编辑器内"收藏为素材"按钮 → `knowledge_documents(source_type=material)` + 自动索引

---

## 6. 数据模型变更汇总

| 变更 | 表 | 说明 |
| :--- | :--- | :--- |
| 新增 | `user_memories` | L2 长期记忆（§4.2） |
| 新增 | `conversation_summaries` | L1 滚动摘要（§3.2） |
| 修改 | `messages` | 无需改表；摘要独立存储 |
| 修改 | `knowledge_documents` | `source_type` 增加 `material` 枚举值（需迁移） |
| 修改 | `answer_versions` | 无需改表；diff 分析直接读取 |

新增 Alembic 迁移：`migrations/versions/xxxx_memory_system.py`。

---

## 7. Agent 集成方案

**改造 `graphs/conversation.py`：**

```text
START → preprocess
    → memory_retrieve（新增节点，L2 检索注入）   ← 新
    → route_intent
    ├── parse_url → normalize → build_response
    └── knowledge_decision
        → retrieve_knowledge（L3）
        → chat（合并记忆块 + RAG 证据块 + 上下文预算）
    → END
    ↘ memory_extract（异步后台，L2 写入）        ← 新
```

- `MemoryRetrieverNode`：L2 注入，无检索结果则跳过
- `MemoryExtractorNode`：异步任务，挂 BackgroundTasks，不进 SSE 主流程
- 上下文组装移到 `ContextComposer`，`chats.py` 不再手拼历史

---

## 8. API 设计

| 方法 | 路径 | 说明 |
| :--- | :--- | :--- |
| GET | `/api/memories` | 记忆列表（type/status 筛选、分页） |
| POST | `/api/memories` | 手动新增记忆（source_type=manual） |
| PUT | `/api/memories/{id}` | 编辑记忆内容（重新向量化） |
| POST | `/api/memories/{id}/confirm` | 确认隐式记忆（pending → active，合并风格规则） |
| POST | `/api/memories/{id}/reject` | 拒绝隐式记忆（→ rejected） |
| DELETE | `/api/memories/{id}` | 删除记忆（软删） |
| GET | `/api/memories/pending` | 待确认的隐式记忆（前端红点提示） |

复用现有 `settings` 路由风格，新增 `app/api/routes/memories.py`。

---

## 9. 前端 UI 需求

- **设置页新增「记忆管理」标签页**：
  - 显式/工作习惯记忆：列表展示 + 编辑/删除
  - 隐式记忆：待确认队列（内容 + 证据 diff + 采纳/拒绝按钮）
- **对话界面**：顶部 Badge「已应用 N 条记忆」，可展开命中详情
  （记忆条目 + 相似度 + 来源，数据来自 `retrieval_traces` 的 memory 类型）
- **编辑器**：新增「收藏为素材」按钮，跳转知识库素材分类
- **长对话提示**：上下文预算接近上限时展示压缩提示

---

## 10. 实现优先级与路线图

| Phase | 内容 | 验收标准 |
| :--- | :--- | :--- |
| **P0** | ContextComposer + checkpoint thread_id 修复 + 滚动摘要 | 40 轮长对话 token 不超预算；同会话中断后状态可续 |
| **P1** | user_memories 表 + 显式记忆提取/检索注入 + 记忆管理 API/UI + **创作上下文衔接** | 对话中告知偏好，新会话可复用；创作时模型能感知用户偏好与对话背景 |
| **P2** | 隐式记忆：版本 diff 风格学习 + 确认流程 | 用户改稿后出现待确认记忆；确认后新生成体现偏好 |
| **P3** | L3 素材库 + 写作时素材检索注入 | 编辑器收藏素材，写作可引用 [S1] 素材 |

### P0 验收细节

- [ ] 40 轮对话的历史注入 token 恒 ≤ `CONTEXT_TOKEN_BUDGET`
- [ ] 最近 1 轮用户消息完整保留
- [ ] 摘要覆盖 ≥ 全部早期历史（covered_message_ids 完整）
- [ ] 同一 chat 的连续两次请求共享 checkpoint thread（状态可续）
- [ ] 现有 4 条 SSE 流式链路回归通过

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
| `chats.py` 历史拼接 | 全量注入 | 改用 `ContextComposer.assemble()` |
| `graphs/conversation.py` | 6 节点 | + memory_retrieve / memory_extract 节点 |
| `state.py` | ChatAgentState | + memory_hits 字段（只读注入，不落 checkpoint） |
| `persistence/models/` | 9 张表 | + `user_memories`、`conversation_summaries` |
| `application/` | chat/document/knowledge | + `context/composer.py`、`memory/` 服务、`StyleLearnerService`、创作背景摘要 |
| `prompts/` | chat/system 等 | + `chat/memory_extract.yml`、`chat/summary.yml`、`chat/memory_inject.yml`、写作背景摘要片段 |
| `infrastructure/knowledge/` | embedding/retrieval | 复用 embedding 通道，不新建；记忆检索命中写入 `retrieval_traces`（memory 类型） |
| `api/routes/` | 7 个路由 | + `memories.py` |
| 前端 | chat/knowledge/hotlist/settings | 设置页记忆管理、对话记忆 Badge、素材收藏、创作背景开关 |
