# [实现计划] 上下文管理与记忆系统

> **文档状态**：已制定 (Drafting) - 等待用户评审确认
> **关联 Spec**：[docs/specs/feature-context-memory-system.md](../specs/feature-context-memory-system.md)
> **跨 Spec 依赖**：`generate_structured`（outline plan）供记忆提取/摘要使用；
> 记忆节点挂载在 agent-platform plan 重构后的 `conversation_graph` 上。
>
> **2026-08-05 同步**：`feature/private-knowledge-rag` 已落地 L2 长期记忆主体
> （`user_memories` 表 + 提取/检索/管理 + 对话 Badge + MemoryAgent），见 §0。
> 以下列表保留全部计划项，已落地的标 ✅，剩余工作为 ◻️。
>
> **2026-08-05 评审补充（spec 2.1）**：Phase 0 增加每 chat 串行锁（并发写冲突）、
> 上下文预算按 model profile 配置、滚动摘要增量合并；Phase 1 增加 HNSW 向量索引迁移。

---

## 0. 已实现基线（feature/private-knowledge-rag）

| 能力 | 已落地 | 剩余工作 |
| :--- | :--- | :--- |
| L2 数据表 | ✅ `persistence/models/user_memories.py`（workspace_id/memory_type/content/embedding Vector(1536)/confidence/source/activation_count） | ◻️ 加 `status` 列（隐式记忆确认） |
| 提取 | ✅ `memory_service.extract_memories`（仅 multi_agent MemoryAgent 调用） | ◻️ 接入主对话图（BackgroundTasks）+ 去重 |
| 检索 | ✅ `memory_retriever.py`（conversation.py preprocess 后，200ms 超时静默，topK=5） | ◻️ pgvector cosine（当前 LIKE + activation_count） |
| 管理 | ✅ `/api/memories` GET/DELETE/PUT + `memory-panel.tsx` + `memory-applied-badge.tsx` | ◻️ 手动新增 + confirm/reject/pending |
| L1 上下文窗口 | — | ◻️ `ContextComposer` + 滚动摘要 + thread_id 复用 |
| 隐式记忆 / 素材库 / 创作衔接 | — | ◻️ 全部未实现 |

---

## 1. 拟修改与新增的文件列表

### 1.1 上下文管理（L1）— ◻️ 未实现
* **[NEW] `app/application/context/composer.py`**：`ContextComposer.assemble()` 四层预算组装（摘要/全文/记忆/系统）；**预算按 model profile 配置**（`prompts/model_profiles.yml`），默认 8000，CJK token 估算复用 `context_builder.estimate_tokens`
* **[NEW] `app/application/context/summary_updater.py`**：`SummaryUpdater` 滚动摘要（LLM 压缩，`prompts/chat/summary.yml`）；**增量合并**（旧摘要 + 上次 `covered_message_ids` 之后的新增长段）+ 失败指数退避重试 1 次
* **[MODIFY] `app/api/routes/chats.py`**
  * `thread_id` 改为 `chat_id`（分支用 `chat_id__{branch_root}`，当前 `chats.py:262` 仍每次新建）
  * **每 chat 串行锁（评审补充，spec §3.4）**：维护 `asyncio.Lock`（按 chat_id）串行化同一会话图运行，避免并发写同一 checkpoint thread
  * 历史拼接改为 `ContextComposer.assemble()` 调用

### 1.2 长期记忆（L2）— ✅ 表/服务/检索节点已建，◻️ 向量检索与主图接入
* ✅ **[已存在] `app/persistence/models/user_memories.py`**：`UserMemoryModel`（真实字段见 §0）
* **[NEW] `app/persistence/models/summaries.py`**：`ConversationSummary`（summary / covered_message_ids / token_count）
* **[MODIFY] `app/persistence/models/user_memories.py`**：加 `status` 列（pending/active/rejected）+ **HNSW 向量索引**（`vector_cosine_ops`，评审补充，spec §4.2）
* ✅ **[已存在] `app/application/memory_service.py`**：CRUD + 向量化（提取/检索）
* **[NEW] `app/application/memory_extractor.py`**：`MemoryExtractorNode` 显式记忆提取（后台异步，接入主对话图）；**去重**依赖 pgvector cosine 相似度（阈值 > 0.9，需 HNSW 索引），无 embedding 旧条目以 content 精确匹配兜底
* ✅ **[已存在] `app/application/agent/nodes/memory_retriever.py`**：`MemoryRetrieverNode` top-K 检索注入（改 pgvector cosine）
* **[NEW] `app/application/memory/style_learner_service.py`**：版本 diff → 隐式风格记忆（pending_confirmation）；**只取"AI 生成 → 手动编辑"相邻对，跳过质检采纳等 AI→AI 对**（经 `ai_operations.result_version_id` join 识别，spec §4.6/agent-platform §4.6）
* ✅ **[已存在] `prompts/memory/extract.yml`、`prompts/memory/retrieve.yml`**

### 1.3 Agent 图接入
* ✅ **[已存在] `app/application/agent/graphs/conversation.py`**：`memory_retriever` 已挂载（preprocess 后）
* ◻️ **[MODIFY] `app/application/agent/nodes/preprocess.py`（或对话结束节点）**：`memory_extract`（BackgroundTasks）
* **[MODIFY] `app/application/agent/nodes/multi_agent.py`**：MemoryAgent 已调用 `extract_memories`（保留）

### 1.4 创作衔接（chat → 创作）
* **[MODIFY] `app/prompts/composer.py`**：`compose_writing_prompt` 支持注入 L2 记忆块 + 对话背景摘要
* **[NEW] `app/application/context/writing_background.py`**：经 `chat_source_items` 反向定位 chat → 提炼「文章背景摘要」（≤500 token，按 source_item 缓存，最新 covered_message_id 前进时增量更新）
* **[MODIFY] `app/workflows/answer_generation.py`**：生成/润色/重写时接入记忆注入 + 背景摘要

### 1.5 素材库（L3）
* **[MODIFY] `app/domain/knowledge.py`**：`SourceType` 增加 `material`
* **[MODIFY] `app/api/routes/knowledge.py`**：素材收藏入口（`source_type=material` 自动索引）
* **[MODIFY] `frontend/src/features/chat/editor-panel.tsx`**：收藏为素材按钮

### 1.6 API 与前端
* ✅ **[已存在] `app/api/routes/memories.py`**：`/api/memories` GET/DELETE/PUT（已挂载 server.py）
* ◻️ 补充 POST（手动新增）/confirm/reject/pending
* ✅ **[已存在] `frontend/src/features/settings/memory-panel.tsx`**：记忆管理列表
* ✅ **[已存在] `frontend/src/features/chat/memory-applied-badge.tsx`**：对话记忆 Badge
* ◻️ **[MODIFY]** Badge 可展开命中详情（读 `retrieval_traces` memory 类型）+ 隐式待确认队列
* **[MODIFY] `frontend/src/features/settings/settings-page.tsx`**：创作背景开关

### 1.7 迁移与测试
* ✅ **[已存在] `migrations/versions/20260804_user_memories.py`**：`user_memories` 表
* ◻️ **[NEW] `migrations/versions/xxxx_context_memory_evolve.py`**：`user_memories` 加 `status` 列 + **HNSW 索引** + `conversation_summaries` 表（无破坏性 DDL）
* **[NEW] `tests/test_context_composer.py`**：预算分层（按 model profile）、最近 1 轮保留、40 轮不超预算、**增量摘要不重复计算已覆盖段**
* ✅ **[已存在] `tests/test_memory_service.py`**：CRUD / 向量化（可扩展去重断言）
* **[NEW] `tests/test_memory_pipeline.py`**：提取→检索→注入链路（扩展主对话图接入断言）
* **[NEW] `tests/test_style_learner.py`**：diff → 隐式记忆 → 确认生效；**跳过 quality_adopt 的 AI→AI 对**
* **[NEW] `tests/test_writing_background.py`**：chat 背景摘要隔离（A/B/C 互不串扰）

---

## 2. 详细执行步骤（TDD 流程）

> 已落地部分不再列为步骤：`user_memories` 表、提取/检索/管理、对话 Badge、
> MemoryAgent。以下步骤仅覆盖 ◻️ 剩余工作。

### Phase 0：上下文窗口管理 + checkpoint 修复
1. **Step 1 (TDD)**：写 `tests/test_context_composer.py`——40 轮长对话 token 恒 ≤ 预算（按 model profile）、最近 1 轮完整、摘要覆盖全量早期历史、增量摘要不重复。
2. **Step 2**：实现 `context/composer.py`（复用 `context_builder.estimate_tokens`，预算读取自 model profile）。
3. **Step 3**：实现 `context/summary_updater.py` + `conversation_summaries` 表 + `prompts/chat/summary.yml`（增量合并 + 失败重试）。
4. **Step 4**：`chats.py` 接入 Composer；`thread_id` 修复为 `chat_id`（分支隔离规则，当前 `chats.py:262` 仍每次新建）；**每 chat 串行锁**，并写并发断言（同一 chat 两条消息不冲突）。
5. **Step 5**：现有 SSE 流式链路回归（`tests/test_chat_branching.py` 等）。

### Phase 1：显式记忆 + 记忆管理（主体已实现，◻️ 补齐主图接入）
6. **Step 6 (TDD)**：扩展 `tests/test_memory_service.py` + 新 `tests/test_memory_pipeline.py`——主对话图结束异步提取、去重（相似度 > 0.9）。
7. **Step 7**：◻️ `user_memories` 加 `status` 列 + **HNSW 向量索引**（Alembic 迁移，为 P2 铺路）。
8. **Step 8**：◻️ `MemoryExtractorNode`（后台异步，依赖 `generate_structured`）接入主对话图；检索改 pgvector cosine（HNSW 索引生效）。
9. **Step 9**：◻️ `/api/memories` 补 POST/confirm/reject/pending + 前端隐式待确认队列 + Badge 命中详情。

### Phase 2：隐式记忆风格学习
10. **Step 10 (TDD)**：写 `tests/test_style_learner.py`——AI 版 vs 手动版 diff 提炼、pending_confirmation、确认后合并 style_rules。
11. **Step 11**：实现 `style_learner_service.py` + 确认/拒绝 API + 前端待确认队列。

### Phase 3：创作衔接 + 素材库
12. **Step 12 (TDD)**：写 `tests/test_writing_background.py`——背景摘要按 source_item 隔离、A/B/C 互不串扰。
13. **Step 13**：`writing_background.py` + `composer.py` 注入记忆/背景摘要 + workflows 接入。
14. **Step 14**：`SourceType.material` + 素材收藏入口 + Writer 检索素材注入。

---

## 3. 验证计划

### 自动化测试命令
```bash
uv run pytest tests/test_context_composer.py tests/test_memory_service.py tests/test_memory_pipeline.py tests/test_style_learner.py tests/test_writing_background.py -v
cd frontend && bun run typecheck && bun run build
```

### 实际链路校验
1. 40 轮长对话：SSE 正常，`agent.status` 上报压缩提示，token 不超预算（按 model profile）
2. 同一 chat 快速连发两条消息：串行锁生效，无状态错乱
3. 对话中告知"读者是大学生" → 新会话触发时 `agent.status` 显示"已应用 N 条记忆"
4. 用户改稿保存 → 设置页出现待确认隐式记忆 → 确认后新生成体现偏好；质检采纳生成的版本不产生隐式记忆
5. 点击文章 A 创作 → 背景摘要只含 A 相关对话，B/C 不受影响
6. 编辑器收藏素材 → 写作时生成回答可引用 `[S1]` 素材

### 里程碑验收（对应 spec §10）

- [x] **已实现（feature/private-knowledge-rag）**：`user_memories` 表 + 提取/检索/管理 + 对话 Badge + MemoryAgent
- [ ] P0：40 轮不超预算；**并发两条消息不冲突**；同会话中断后状态可续；SSE 链路回归
- [ ] P1：记忆提取接入主对话图；向量检索（HNSW 索引）；手动新增/确认流程；新会话可复用偏好
- [ ] P2：diff 风格学习 + 确认流程生效（跳过 AI→AI 对）
- [ ] P3：素材库 + 写作时素材检索注入
