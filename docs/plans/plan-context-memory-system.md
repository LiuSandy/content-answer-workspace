# [实现计划] 上下文管理与记忆系统

> **文档状态**：已制定 (Drafting) - 等待用户评审确认
> **关联 Spec**：[docs/specs/feature-context-memory-system.md](../specs/feature-context-memory-system.md)
> **跨 Spec 依赖**：`StructuredOutputClient`（outline spec）供记忆提取/摘要使用；
> 记忆节点挂载在 agent-platform spec 重构后的 `conversation_graph` 上。

---

## 1. 拟修改与新增的文件列表

### 1.1 上下文管理（L1）
* **[NEW] `app/application/context/composer.py`**：`ContextComposer.assemble()` 四层预算组装（摘要/全文/记忆/系统）
* **[NEW] `app/application/context/summary_updater.py`**：`SummaryUpdater` 滚动摘要（LLM 压缩，`prompts/chat/summary.yml`）
* **[MODIFY] `app/api/routes/chats.py`**
  * `thread_id` 改为 `chat_id`（分支用 `chat_id__{branch_root}`）
  * 历史拼接改为 `ContextComposer.assemble()` 调用

### 1.2 长期记忆（L2）
* **[NEW] `app/persistence/models/memory.py`**：`UserMemory`（memory_type / content / embedding / status / access_count）
* **[NEW] `app/persistence/models/summaries.py`**：`ConversationSummary`（summary / covered_message_ids / token_count）
* **[MODIFY] `app/persistence/models/__init__.py`**：注册新模型
* **[NEW] `app/application/memory/memory_service.py`**：记忆 CRUD + 向量化 + 去重
* **[NEW] `app/application/memory/memory_extractor.py`**：`MemoryExtractorNode` 显式记忆提取（后台异步）
* **[NEW] `app/application/memory/memory_retriever.py`**：`MemoryRetrieverNode` top-K 检索注入
* **[NEW] `app/application/memory/style_learner_service.py`**：版本 diff → 隐式风格记忆（pending_confirmation）；**只取"AI 生成 → 手动编辑"相邻对，跳过质检采纳等 AI→AI 对**
* **[NEW] `prompts/chat/memory_extract.yml`**、**`prompts/chat/memory_inject.yml`**

### 1.3 Agent 图接入
* **[MODIFY] `app/application/agent/graphs/conversation.py`**：新增 `memory_retrieve`（读）与 `memory_extract`（写，BackgroundTasks）节点
* **[MODIFY] `app/application/agent/nodes/preprocess.py`**：记忆检索注入逻辑

### 1.4 创作衔接（chat → 创作）
* **[MODIFY] `app/prompts/composer.py`**：`compose_writing_prompt` 支持注入 L2 记忆块 + 对话背景摘要
* **[NEW] `app/application/context/writing_background.py`**：经 `chat_source_items` 反向定位 chat → 提炼「文章背景摘要」（≤500 token，按 source_item 缓存，最新 covered_message_id 前进时增量更新）
* **[MODIFY] `app/workflows/answer_generation.py`**：生成/润色/重写时接入记忆注入 + 背景摘要

### 1.5 素材库（L3）
* **[MODIFY] `app/domain/knowledge.py`**：`SourceType` 增加 `material`
* **[MODIFY] `app/api/routes/knowledge.py`**：素材收藏入口（`source_type=material` 自动索引）
* **[MODIFY] `frontend/src/features/chat/editor-panel.tsx`**：收藏为素材按钮

### 1.6 API 与前端
* **[NEW] `app/api/routes/memories.py`**：`/api/memories` CRUD + confirm/reject/pending
* **[MODIFY] `app/server.py`**：挂载 memories 路由
* **[NEW] `frontend/src/features/settings/memories-tab.tsx`**：记忆管理（显式列表 + 隐式待确认队列）
* **[MODIFY] `frontend/src/features/chat/chat-panel.tsx`**：记忆 Badge（已应用 N 条，可展开命中详情，读 `retrieval_traces` memory 类型）
* **[MODIFY] `frontend/src/features/settings/settings-page.tsx`**：创作背景开关

### 1.7 迁移与测试
* **[NEW] `migrations/versions/xxxx_memory_system.py`**：`user_memories` + `conversation_summaries`（仅新增表，无破坏性 DDL）
* **[NEW] `tests/test_context_composer.py`**：预算分层、最近 1 轮保留、40 轮不超预算
* **[NEW] `tests/test_memory_service.py`**：CRUD / 去重 / 向量化
* **[NEW] `tests/test_memory_pipeline.py`**：提取→检索→注入链路
* **[NEW] `tests/test_style_learner.py`**：diff → 隐式记忆 → 确认生效
* **[NEW] `tests/test_writing_background.py`**：chat 背景摘要隔离（A/B/C 互不串扰）

---

## 2. 详细执行步骤（TDD 流程）

### Phase 0：上下文窗口管理 + checkpoint 修复
1. **Step 1 (TDD)**：写 `tests/test_context_composer.py`——40 轮长对话 token 恒 ≤ 预算、最近 1 轮完整、摘要覆盖全量早期历史。
2. **Step 2**：实现 `context/composer.py`（复用 `context_builder.estimate_tokens`）。
3. **Step 3**：实现 `context/summary_updater.py` + `conversation_summaries` 表 + `prompts/chat/summary.yml`。
4. **Step 4**：`chats.py` 接入 Composer；`thread_id` 修复为 `chat_id`（分支隔离规则）。
5. **Step 5**：现有 4 条 SSE 链路回归（`tests/test_chat_branching.py` 等）。

### Phase 1：显式记忆 + 记忆管理
6. **Step 6 (TDD)**：写 `tests/test_memory_service.py` + `tests/test_memory_pipeline.py`。
7. **Step 7**：`UserMemory` 模型 + Alembic 迁移 + `memory_service.py`（CRUD/向量化/去重）。
8. **Step 8**：`MemoryExtractorNode`（后台异步，依赖 StructuredOutputClient）+ `MemoryRetrieverNode` + 图接入。
9. **Step 9**：`/api/memories` 路由 + 前端设置页记忆管理 + 对话 Badge。

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
1. 40 轮长对话：SSE 正常，`agent.status` 上报压缩提示，token 不超预算
2. 对话中告知"读者是大学生" → 新会话触发时 `agent.status` 显示"已应用 N 条记忆"
3. 用户改稿保存 → 设置页出现待确认隐式记忆 → 确认后新生成体现偏好
4. 点击文章 A 创作 → 背景摘要只含 A 相关对话，B/C 不受影响
5. 编辑器收藏素材 → 写作时生成回答可引用 `[S1]` 素材

### 里程碑验收（对应 spec §10）
- [ ] P0：40 轮不超预算；同会话中断后状态可续；4 条 SSE 链路回归
- [ ] P1：记忆提取/检索/管理全通；新会话可复用偏好
- [ ] P2：diff 风格学习 + 确认流程生效
- [ ] P3：素材库 + 写作时素材检索注入
