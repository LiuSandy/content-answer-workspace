# 升级为完整 Agent 项目 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans` 按任务顺序实施；每完成一个任务，先验证再提交。Phase 之间必须按序推进，前置条件未达成不启动下一 Phase。

**Goal:** 将项目从「LLM 应用内嵌 Agent 子系统」升级为「以 Agent 为核心驱动力的内容创作平台」，按 Phase 1.5 → 2 → 3 → 4 顺序依次交付 RAG 主链路打通、反思循环与主动感知、自主规划引擎、长期记忆与多 Agent 协作。

**Architecture:** 在现有单编排 Chat Agent 基础上分层扩展：新增结构化评分工作流（ReflectionNode）、向 APScheduler 注入定时任务基础设施、新建 PlannerNode + TaskExecutorGraph 的 DAG 调度、引入 pgvector 长期记忆管道、最终用 LangGraph 子图嵌套实现多 Agent 协作。所有新能力通过 Application Service + 域模型 + 迁移落地，不改写现有 Chat Agent 已稳定的主链路。

**Tech Stack:** Python 3.11、FastAPI、Pydantic v2、SQLAlchemy 2 Async、Alembic、PostgreSQL、pgvector、LangGraph Graph API + Multi-Agent 子图、APScheduler、DeepSeek LLM、React 19、TypeScript、Vite、Tailwind CSS v4、TanStack Query、Zustand、Bun。

## Global Constraints

- 本计划对应已确认规格：[feature-full-agent-upgrade.md](../specs/feature-full-agent-upgrade.md)，不得把规格外的能力（如自动发布、多用户审核、版本 Diff/Patch、微服务化）加入任何 Phase。
- Phase 之间强依赖：Phase 2 隐含「RAG 已在主链路可信使用」假设，必须在 Phase 1.5 完成后启动；Phase 3 的 PlannerNode 生成的写作子任务依赖 Phase 2 的反思循环；Phase 4 的 MemoryAgent 依赖 Phase 2 已沉淀的行为信号、Phase 3 已存在的 TaskPlan。
- 反思循环硬性上限 3 轮，超过强制输出 + 用户告警；定时任务在非活跃时段（凌晨 1-7 点）跳过扫描。
- 多 Agent 协作状态隔离：单个子 Agent 失败不得影响其他子 Agent；ResearchAgent 并发 > 3。
- 所有新表预留 `workspace_id`，但第一版单用户不实现注册、RBAC 或复杂租户逻辑。
- 长期记忆全本地存储，不上传任何记忆数据；前端提供一键清空。
- 修改 `.py` 后运行相关 pytest；修改 `.ts/.tsx` 后至少运行 `bun run typecheck` 和 `bun run build`。
- 本计划不包含 specs 外的新功能。如发现 specs 有歧义，回到 specs 阶段修订，不在 plan 中自行补设定。

## 功能概述

实现五个能力维度，按 Phase 分批交付：

| Phase | 功能 | 复用度 | 预计周期 |
| :--- | :--- | :--- | :--- |
| 1.5 前置 | RAG 检索接入对话主链路 + 真实 PDF 端到端验证 | 改造现有节点 | 1-2 周 |
| 2 | 功能三 反思与自我修正循环 + 功能四 主动感知 | 复用 refinement 节点 + 热榜工具 | 4-6 周 |
| 3 | 功能一 自主规划引擎 | 全新 | 6-10 周 |
| 4 | 功能二 长期记忆系统 + 功能五 多 Agent 协作 | pgvector + 子图嵌套 | 10-16 周 |

## 目标

- **Phase 1.5：** RAG 检索在真实 Chat 流中影响 chat 节点输出、落库 Trace，真实 PDF 验证 conversion_confidence 非 NULL 且低于阈值时前端能看到警告。
- **Phase 2：** 生成后自动 LLM 自评 5 维，<0.75 自动定向修正（最多 3 轮）；每小时定时扫热榜，结合用户领域匹配度算机会得分，工作台顶部 SSE 推送「今日机会」卡片。
- **Phase 3：** 用户输入复合目标，Agent 自动生成 5 步以上 TaskPlan DAG 并并行执行，前端实时进度树，单任务失败可重试，5 步计划总耗时 ≤ 120s。
- **Phase 4：** 跨会话保存显式/隐式/工作习惯三类记忆，对话中检索注入 system prompt；Orchestrator/Research/Writing/Review/Memory 5 子 Agent 协作，ResearchAgent 并发 > 3，整体执行比串行缩短 ≥ 40%。

## 范围

**包含：**
- Phase 1.5：`retrieve_knowledge` 节点端到端验证、Trace 落库确认、chat 节点消费证据、真实 PDF 验证警告。
- 功能三：ReflectionNode 自评、定向修正循环、5 维评分协议、前端质量评分与修正历程。
- 功能四：APScheduler 定时任务、OpportunityScanTool、机会评分模型、今日机会 SSE 推送、设置页领域 Tag 配置。
- 功能一：PlannerNode、TaskExecutorGraph、DAG 依赖调度、5 种 SubTask 类型、TaskPlan 进度树。
- 功能二：pgvector user_memories 表、MemoryExtractor/Retriever 节点、显式/隐式/工作习惯三类记忆、「我的记忆」管理页。
- 功能五：planner_graph + multi_agent_graph、5 专职子 Agent、interrupt/resume、协作树状态面板。

**不包含：**
- 自动发布到平台、多用户审核、版本 Diff/Patch/分支/合并、Kafka 或微服务、向量化生产级部署、Multi-Agent 自主辩论。

## 技术栈

- 后端：Python 3.11、FastAPI、Pydantic v2、SQLAlchemy 2 Async、Alembic、LangGraph Graph API + Multi-Agent 子图、APScheduler。
- 数据：PostgreSQL、pgvector（长期记忆向量）、现有 ParadeDB `pg_search` BM25（RAG 已有）。
- 模型：DeepSeek LLM via OpenAI-compatible ChatOpenAI 客户端、Embedding 复用现有配置。
- 前端：React 19、TypeScript、Vite、Tailwind CSS v4、TanStack Query、Zustand、React Router、Bun。

## 涉及文件

```text
# Phase 1.5
app/application/agent/nodes/{retrieve_knowledge,chat_node,knowledge_decision}.py
app/application/agent/graphs/conversation.py
tests/test_conversation_graph_rag_e2e.py
tests/test_pdf_confidence_live.py
docs/specs/private-knowledge-rag-known-gaps.md

# Phase 2 - 功能三 反思循环
app/models.py
app/persistence/models/quality_scores.py
app/persistence/models/__init__.py
migrations/versions/YYYYMMDD_quality_scores.py
app/application/workflows/reflection.py
app/application/agent/nodes/reflection.py
app/application/agent/nodes/apply_refinement.py
app/application/agent/graphs/{conversation,refinement}.py
app/api/routes/documents.py
prompts/writing/reflection.yml
frontend/src/types/workflow.ts
frontend/src/features/chat/editor-panel.tsx
frontend/src/features/chat/quality-score-panel.tsx
frontend/src/features/chat/reflection-history-dialog.tsx
tests/test_reflection_loop.py
tests/knowledge/test_grounded_answer.py

# Phase 2 - 功能四 主动感知
app/core/config.py
app/persistence/models/{opportunity_feeds,agent_settings}.py
app/persistence/models/__init__.py
migrations/versions/YYYYMMDD_opportunity_feeds.py
app/application/opportunity_service.py
app/infrastructure/scheduler/__init__.py
app/infrastructure/scheduler/opportunity_scanner.py
app/application/agent/tools/opportunity_scan_tool.py
app/api/routes/opportunities.py
app/server.py
prompts/hotlist/opportunity_score.yml
frontend/src/features/chat/today-opportunities-banner.tsx
frontend/src/features/settings/agent-settings-panel.tsx
frontend/src/features/knowledge/opportunity-api.ts
tests/test_opportunity_scanner.py
tests/test_scheduler.py

# Phase 3 - 自主规划引擎
app/models.py
app/persistence/models/{task_plans,sub_tasks}.py
app/persistence/models/__init__.py
app/persistence/repositories/task_plan_repository.py
migrations/versions/YYYYMMDD_task_plans.py
app/application/task_planner_service.py
app/application/agent/nodes/planner.py
app/application/agent/nodes/task_executor.py
app/application/agent/graphs/planner_graph.py
app/application/agent/state.py
app/api/routes/task_plans.py
app/server.py
prompts/planning/planner.yml
prompts/planning/{search_subtask,outline_subtask,write_subtask,review_subtask}.yml
frontend/src/types/task-plan.ts
frontend/src/features/chat/task-plan-card.tsx
frontend/src/features/chat/task-mode-toggle.tsx
frontend/src/features/chat/task-plan-api.ts
frontend/src/store/chat-store.ts
frontend/src/features/chat/chat-panel.tsx
tests/test_planner_node.py
tests/test_task_executor_graph.py
tests/test_task_planner_service.py

# Phase 4 - 长期记忆
app/persistence/models/user_memories.py
app/persistence/models/__init__.py
app/persistence/repositories/memory_repository.py
migrations/versions/YYYYMMDD_user_memories.py
app/application/memory_service.py
app/application/agent/nodes/{memory_extractor,memory_retriever}.py
app/application/agent/graphs/conversation.py
app/application/agent/state.py
app/application/agent/tools/memory_search_tool.py
app/api/routes/memories.py
app/server.py
prompts/memory/{extract,retrieve}.yml
frontend/src/features/settings/memory-panel.tsx
frontend/src/features/chat/memory-applied-badge.tsx
frontend/src/features/settings/memory-api.ts
tests/test_memory_extractor.py
tests/test_memory_retriever.py
tests/test_memory_service.py

# Phase 4 - 多 Agent 协作
app/application/agent/graphs/multi_agent_graph.py
app/application/agent/nodes/{orchestrator,research_agent,writing_agent,review_agent,memory_agent}.py
app/application/agent/state.py
app/api/routes/task_plans.py
prompts/multi_agent/{orchestrator,research,writing,review,memory_agent}.yml
frontend/src/features/chat/agent-workspace-panel.tsx
frontend/src/features/chat/agent-status-tree.tsx
frontend/src/types/multi-agent.ts
tests/test_multi_agent_graph.py
tests/test_research_agent_concurrency.py
```

## 任务拆分

```text
Phase 1.5（Phase 2 启动前置）
  Task 1：RAG 检索接入对话主链路端到端验证
  Task 2：真实 PDF conversion_confidence 端到端验证

Phase 2 - 功能三：反思与自我修正循环
  Task 3：质量评分数据模型与迁移
  Task 4：ReflectionNode 自评与评分协议
  Task 5：定向修正循环与 3 轮上限
  Task 6：前端质量评分面板与修正历程

Phase 2 - 功能四：主动感知与推送
  Task 7：定时任务基建与 OpportunityFeed 数据模型
  Task 8：机会扫描器与评分模型
  Task 9：今日机会 SSE 推送与设置页配置
  Task 10：一键拉起 TaskPlan 集成

Phase 3 - 自主规划引擎
  Task 11：TaskPlan 数据模型与迁移
  Task 12：PlannerNode 目标分解与 DAG 生成
  Task 13：TaskExecutorGraph 依赖调度与并行执行
  Task 14：TaskPlan REST API 与前端进度树
  Task 15：动态调整与失败重试

Phase 4 - 长期记忆系统
  Task 16：pgvector user_memories 表与迁移
  Task 17：MemoryExtractor 记忆提取节点
  Task 18：MemoryRetriever 检索注入节点
  Task 19：「我的记忆」管理 UI

Phase 4 - 多 Agent 协作框架
  Task 20：Multi-Agent 状态与 Orchestrator 子图
  Task 21：ResearchAgent 并行研究子 Agent
  Task 22：WritingAgent + ReviewAgent 协作
  Task 23：MemoryAgent 集成与 interrupt/resume
  Task 24：前端 Agent 协作树面板与端到端验收
```

## TDD 执行步骤

### Task 1：RAG 检索接入对话主链路端到端验证

**目标：** 证明 `conversation.py` 中 `retrieve_knowledge` 节点在真实 Chat 流中执行检索、落库 Trace，且 `chat_node` 消费证据形成 grounded 回答；普通模式降级、严格模式拒答两条路径都被覆盖。这是 Phase 1.5 的核心，Phase 2 启动强制前置条件。

**涉及文件：**
- Modify: `app/application/agent/nodes/retrieve_knowledge.py`
- Modify: `app/application/agent/nodes/chat_node.py`
- Test: `tests/test_conversation_graph_rag_e2e.py`
- Modify: `tests/test_conversation_graph.py`

**步骤：**

- [ ] **Step 1：写失败测试**

  在 `tests/test_conversation_graph_rag_e2e.py` 用 fake `KnowledgeRetrievalService`（返回 `has_evidence=True` + `context_text` + `trace_hits`）+ fake `TraceService` 构造四条路径：
  1. `knowledge_mode=normal` + 证据充分 → `chat_node` 收到 `retrieval_result.has_evidence=True`，system_content 含「【私有资料上下文】」与 `[Sx]` 引用指令，Trace 被调用 `create_trace` + `record_hits` + `finalize_trace`，返回 `trace_id` 非 None。
  2. `knowledge_mode=normal` + 证据不足 → system_content 含「【提示】私有资料库中没有找到足够的相关证据」，`fallback_reason` 非 None，Trace 落库 fallback 原因。
  3. `knowledge_mode=strict` + 证据不足 → 图路由到 `strict_refusal_node`，返回固定拒答文本，`chat_node` 不被调用。
  4. `knowledge_mode=off` → `knowledge_decision` 返回 `rag_decision=False`，直接进 `chat_node`，`retrieve_knowledge` 节点不执行。

  断言 `trace_id` 写入 state 返回值、`chat_node` 的 system_content 包含检索上下文。Mock 在 fixture 中注入到 `retrieve_knowledge.py` 的 `get_session_factory` 与 `KnowledgeRetrievalService`。

- [ ] **Step 2：运行测试确认失败**

  ```bash
  uv run pytest tests/test_conversation_graph_rag_e2e.py -v
  ```

  Expected: FAIL，端到端测试文件不存在，或四条路径中至少一条断言不通过（当前主链路未端到端覆盖）。

- [ ] **Step 3：最小实现**

  检查现有 `retrieve_knowledge.py`、`chat_node.py`、`conversation.py` 是否已实现四条路径。当前代码已挂载节点，本任务主要补端到端测试覆盖与可达性验证，不引入新功能。若发现路径 #3 strict 拒答未真正跳过 chat_node（当前 `_route_after_retrieval` 在 `mode=="strict"` 且无证据时返回 `"strict_refusal"`），确认 `strict_refusal_node` 已存在且未误入 chat 节点；若发现 `trace_id` 未写入最终 response payload（`build_response` 节点未读 `trace_id`），在 `build_response_node` 中透传 `trace_id` 与 `sources` 到 `ChatResponsePayload`。

- [ ] **Step 4：运行测试确认通过**

  ```bash
  uv run pytest tests/test_conversation_graph_rag_e2e.py tests/test_conversation_graph.py -v
  ```

  Expected: PASS，四条路径全通过。

- [ ] **Step 5：重构与验证**

  确认 Trace 落库失败不阻断主链路（`retrieve_knowledge.py:69-71` 已有 try/except warning，保持不变）。确认 SQLite Checkpointer 只保存图运行 state，知识正文/Chunk/Trace 仍在 PostgreSQL。

- [ ] **Step 6：提交**

  ```bash
  git add tests/test_conversation_graph_rag_e2e.py app/application/agent/nodes tests/test_conversation_graph.py
  git commit -m "test: verify rag retrieval integrated into chat main flow"
  ```

### Task 2：真实 PDF conversion_confidence 端到端验证

**目标：** 证明置信度链路真实数据流通——上传含扫描页/复杂排版 PDF 后 `conversionConfidence < 0.7` 且候选稿页出现红色警告；纯文字 PDF 接近 1.0 无警告。这是 Phase 1.5 第二项前置条件。

**涉及文件：**
- Modify: `tests/test_pdf_confidence_live.py`
- Modify: `tests/test_knowledge_api.py`
- Modify: `docs/specs/private-knowledge-rag-known-gaps.md`

**步骤：**

- [ ] **Step 1：写失败测试**

  在 `tests/test_pdf_confidence_live.py` 准备两份 fixture PDF（或用 PyMuPDF 程序生成）：
  1. 富文本 PDF：10 页每页 500 字符纯文本 → `_estimate_pdf_confidence` 返回 ≥ 0.9。
  2. 扫描页模拟 PDF：10 页只识别出 50 字符 + 含 U+FFFD 替换字符 → 置信度 < 0.7。
  
  API 集成测试（`test_knowledge_api.py` 扩展）：mock MinerU 返回对应 md_text，调用 `POST /api/knowledge/documents` 上传扫描页 PDF，断言响应 `data.conversionConfidence < 0.7`。再调用 `GET /api/knowledge/documents/{id}` 确认 DB 持久化字段同样 < 0.7（非 null）。

- [ ] **Step 2：运行测试确认失败**

  ```bash
  uv run pytest tests/test_pdf_confidence_live.py tests/test_knowledge_api.py -v
  ```

  Expected: 富文本测试 PASS（链路已修复），扫描页 PDF 端到端断言可能 FAIL（若无 MinerU mock 框架）。

- [ ] **Step 3：最小实现**

  在 `tests/test_pdf_confidence_live.py` 增加 MinerU mock helper（monkeypatch `MinerUCloudParser._parse_single_chunk` 返回固定 md_text），让扫描页 PDF 走完整 `_parse_pdf_to_markdown` 路径并产出低置信度。在 `private-knowledge-rag-known-gaps.md` 第 3 节「路线图裁定」追加："Phase 1.5 第 2 项已于本次完成，真实 PDF 链路打通。"

- [ ] **Step 4：运行测试确认通过**

  ```bash
  uv run pytest tests/test_pdf_confidence_live.py tests/test_knowledge_api.py tests/test_pdf_confidence.py -v
  ```

  Expected: PASS。

- [ ] **Step 5：重构与验证**

  把 MinerU mock 抽到 `tests/conftest.py` fixture，后续 Agent 测试复用。

- [ ] **Step 6：提交**

  ```bash
  git add tests/test_pdf_confidence_live.py tests/test_knowledge_api.py tests/conftest.py docs/specs/private-knowledge-rag-known-gaps.md
  git commit -m "test: verify pdf conversion confidence end to end"
  ```

### Task 3：质量评分数据模型与迁移

**目标：** 为反思循环建立持久化模型，保存每次自评的 5 维分数、weakness_summary、refinement_instruction 与迭代轮次。复用现有 `ai_operations` 表关联。

**涉及文件：**
- Create: `app/persistence/models/quality_scores.py`
- Modify: `app/persistence/models/__init__.py`
- Create: `migrations/versions/YYYYMMDD_quality_scores.py`
- Create: `tests/test_quality_score_model.py`

**Interfaces：**
- `QualityScore`：`id`、`ai_operation_id`（FK）、`document_id`（FK）、`version_id`（FK，nullable）、`iteration`（1-3）、`overall_score`（0-1）、`dimensions`（JSONB: relevance/information_density/readability/logic_coherence/word_count_compliance）、`weakness_summary`、`refinement_instruction`、`created_at`。

- [ ] **Step 1：写失败测试**

  `tests/test_quality_score_model.py`：验证 SQLAlchemy model 字段、JSONB dimensions 序列化、`ai_operation_id` 外键关系、`(document_id, iteration)` 联合查询。

- [ ] **Step 2：运行测试确认失败**

  ```bash
  uv run pytest tests/test_quality_score_model.py -v
  ```

  Expected: FAIL，模型不存在。

- [ ] **Step 3：最小实现**

  以 `20260726_bm25_chinese_tokenizer` 为 `down_revision`，创建 `quality_scores` 表。`dimensions` 用 PostgreSQL `JSONB`，Pydantic 用 `dict[str, float]`。

- [ ] **Step 4：运行测试确认通过**

  ```bash
  uv run alembic upgrade head
  uv run pytest tests/test_quality_score_model.py -v
  ```

  Expected: PASS。

- [ ] **Step 5：重构与验证**

  执行 `alembic downgrade` + `upgrade` 验证可逆。

- [ ] **Step 6：提交**

  ```bash
  git commit -m "feat: add quality score persistence schema"
  ```

### Task 4：ReflectionNode 自评与评分协议

**目标：** 建立 `application/workflows/reflection.py`，接收文档当前内容，LLM 按 spec 4.4 节协议输出结构化评分 JSON，落库 `QualityScore`。这是反思循环的「评」环节，独立于「修」环节以便复用。

**涉及文件：**
- Create: `app/application/workflows/reflection.py`
- Create: `app/application/agent/nodes/reflection.py`
- Create: `prompts/writing/reflection.yml`
- Create: `tests/test_reflection_loop.py`

**Interfaces：**
- `async def reflect(content: str, document_id: UUID, version_id: UUID | None, iteration: int) -> ReflectionResult`
- `ReflectionResult`：`overall_score: float`、`dimensions: dict`、`weakness_summary: str`、`refinement_instruction: str | None`
- 评分协议严格遵循 spec 4.4 节 JSON schema。

- [ ] **Step 1：写失败测试**

  `tests/test_reflection_loop.py`：mock ChatOpenAI 返回固定评分 JSON，验证 `reflect` 解析正确、`QualityScore` 落库 `iteration=1`、`overall_score=0.68`、dimensions 5 个键齐全；mock LLM 返回非法 JSON 时抛 `LLMOutputError`。

- [ ] **Step 2：运行测试确认失败**

  ```bash
  uv run pytest tests/test_reflection_loop.py -v
  ```

- [ ] **Step 3：最小实现**

  `prompts/writing/reflection.yml`：system 要求 LLM 只输出 JSON、包含 5 维分数 0-1、weakness_summary、refinement_instruction；temperature=0.2 保证稳定。`reflect` 用 Pydantic 模型校验 LLM 输出后落库。

- [ ] **Step 4：运行测试确认通过**

  ```bash
  uv run pytest tests/test_reflection_loop.py -v
  ```

- [ ] **Step 5：重构与验证**

  prompt 注册表加载校验必填变量 `content`、`iteration`，启动时 `prompts/writing/reflection.yml` 须通过 `PromptRegistry` schema 校验。

- [ ] **Step 6：提交**

  ```bash
  git commit -m "feat: add reflection self-evaluation workflow"
  ```

### Task 5：定向修正循环与 3 轮上限

**目标：** 在 `refinement.py` 工作流中接入反思循环：首次生成 → ReflectionNode 评分 → < 0.75 触发定向修正（复用 `apply_instruction_node`）→ 再评分 → 最多 3 轮强制输出。给现有 `refinement` Graph 加循环边。

**涉及文件：**
- Modify: `app/application/agent/graphs/refinement.py`
- Create: `app/application/agent/nodes/apply_refinement.py`
- Modify: `app/application/workflows/reflection.py`
- Modify: `app/api/routes/documents.py`
- Create: `tests/test_refinement_loop_integration.py`

**Interfaces：**
- 生成后自动触发反思：`POST /api/documents/{id}/generate` 完成后调 `reflect`，< 0.75 自动 chain refinement。
- 硬性上限 3 轮，超过强制输出当前内容并附「反思未收敛」提示。
- 每轮创建新 `AnswerVersion`，`version_type="inline_refinement"`，关联 `QualityScore` 记录。

- [ ] **Step 1：写失败测试**

  `tests/test_refinement_loop_integration.py`：
  1. mock 首次生成 + 第一轮评分 0.68 → 触发修正 → 第二轮评分 0.82 → 终止，共 2 个 AnswerVersion、2 条 QualityScore。
  2. mock 连续 3 轮评分 < 0.75 → 第 4 轮强制输出，附「已自评 3 轮未收敛」标记，共 3 个版本。
  3. mock 首次评分 0.85 → 不触发修正，1 个版本、1 条 QualityScore。

- [ ] **Step 2-6**：TDD 循环 + 提交 `feat: add reflection-driven refinement loop`

### Task 6：前端质量评分面板与修正历程

**目标：** spec 4.5 节 UI——工作台底部展示「质量评分」进度条与维度雷达图；生成完成后显示「已自评 N 轮，最终得分 X」；「查看修正历程」按钮展示每轮 Diff。

**涉及文件：**
- Create: `frontend/src/features/chat/quality-score-panel.tsx`
- Create: `frontend/src/features/chat/reflection-history-dialog.tsx`
- Modify: `frontend/src/features/chat/editor-panel.tsx`
- Modify: `frontend/src/types/workflow.ts`
- Modify: `frontend/src/features/knowledge/knowledge-api.ts`

**interfaces：**
- `GET /api/documents/{id}/quality-scores` 返回 `[{iteration, overallScore, dimensions, weaknessSummary, createdAt}]`。
- 前端雷达图用纯 SVG（不引入额外图表库）。

- [ ] **Step 1**：写 `quality-score-panel.test.tsx` 类型与渲染断言。
- [ ] **Step 2-6**：TDD + `bun run typecheck` + `bun run build` + 提交 `feat: add quality score panel and reflection history`

### Task 7：定时任务基建与 OpportunityFeed 数据模型

**目标：** 引入 APScheduler 进程内定时任务基建（spec 第 9 节）；创建 `opportunity_feeds` 表持久化扫描结果。第一版不引入 Celery，`InProcessTaskDispatcher` 思路。

**涉及文件：**
- Modify: `pyproject.toml`（加 `apscheduler>=3.10`）
- Create: `app/infrastructure/scheduler/__init__.py`
- Create: `app/infrastructure/scheduler/opportunity_scanner.py`
- Create: `app/persistence/models/opportunity_feeds.py`
- Create: `migrations/versions/YYYYMMDD_opportunity_feeds.py`
- Create: `app/persistence/models/agent_settings.py`
- Modify: `app/server.py`（启动时注册 scheduler）
- Create: `tests/test_scheduler.py`

**interfaces：**
- `OpportunityFeed`：`id`、`workspace_id`、`platform`、`question_title`、`question_url`、`hot_score`、`match_score`、`opportunity_score`、`existing_answer_count`、`scanned_at`、`pushed`（是否已推送）。
- `AgentSettings`：`workspace_id`、`proactive_sensing_enabled`、`interest_tags`（JSONB）、`push_time_window`、`scan_interval_hours`。

- [ ] **Step 1-6**：TDD + 迁移 + 提交 `feat: add scheduler infrastructure and opportunity feed schema`

### Task 8：机会扫描器与评分模型

**目标：** 实现 spec 5.4 节评分公式，每小时扫一次热榜（复用 `nodes/fetch_hotlist.py` + `analyze_hotlist.py`），结合 `AgentSettings.interest_tags` 算 `match_score`，排除已创作过的 `SourceItem`，结果落库 `opportunity_feeds`。

**涉及文件：**
- Create: `app/application/opportunity_service.py`
- Create: `app/application/agent/tools/opportunity_scan_tool.py`
- Create: `prompts/hotlist/opportunity_score.yml`
- Modify: `app/infrastructure/scheduler/opportunity_scanner.py`
- Create: `tests/test_opportunity_scanner.py`

**interfaces：**
- 机会得分 = `hot_score × 0.4 + match_score × 0.35 + competition_score × 0.15 + recency_score × 0.10`
- 凌晨 1-7 点跳过扫描（`AgentSettings.scan_interval_hours` 配置）。

- [ ] **Step 1-6**：TDD + `opportunity_score` prompt + 提交 `feat: add opportunity scanner with scoring model`

### Task 9：今日机会 SSE 推送与设置页配置

**目标：** 工作台顶部「今日机会」横幅（可折叠，最多 3 条），SSE 实时刷新；设置页新增「主动感知」配置（领域 Tag、推送时间窗口、关闭开关）。

**涉及文件：**
- Create: `app/api/routes/opportunities.py`
- Modify: `app/server.py`
- Create: `frontend/src/features/chat/today-opportunities-banner.tsx`
- Create: `frontend/src/features/settings/agent-settings-panel.tsx`
- Create: `frontend/src/features/knowledge/opportunity-api.ts`
- Modify: `frontend/src/features/settings/settings-page.tsx`

**interfaces：**
- `GET /api/opportunities?workspaceId=...&limit=3` 返回今日 top 卡片。
- `PUT /api/agent-settings` 保存领域 Tag 与开关。
- SSE 端点 `GET /api/opportunities/stream` 推送新机会事件。

- [ ] **Step 1-6**：TDD + typecheck + build + 提交 `feat: add today opportunities banner and agent settings`

### Task 10：一键拉起 TaskPlan 集成

**目标：** spec 5.5「点击『一键创作』直接拉起 TaskPlan」——卡片按钮调 Phase 3 的 TaskPlan API。本任务在 Phase 2 阶段先实现接口握手（调用方传入卡片数据 → 占位返回 "task_plan_pending"），Phase 3 实现后真正对接。

**涉及文件：**
- Modify: `frontend/src/features/chat/today-opportunities-banner.tsx`
- Modify: `app/api/routes/opportunities.py`

**interfaces：**
- `POST /api/opportunities/{id}/start-plan` → 接收 `{goal}` 返回 `{taskId, status: "pending"}`。

- [ ] **Step 1-6**：TDD + 提交 `feat: bridge opportunity card to task plan placeholder`

### Task 11：TaskPlan 数据模型与迁移

**目标：** spec 2.4 节 `TaskPlan` + `SubTask` 模型，含 DAG 依赖字段。

**涉及文件：**
- Create: `app/persistence/models/task_plans.py`
- Create: `app/persistence/repositories/task_plan_repository.py`
- Create: `migrations/versions/YYYYMMDD_task_plans.py`
- Create: `tests/test_task_plan_model.py`

**interfaces：**
- `TaskPlan`：`id`、`workspace_id`、`chat_id`（FK，nullable）、`goal`、`status`（pending/running/done/failed）、`created_at`、`updated_at`。
- `SubTask`：`id`、`plan_id`（FK）、`task_id`（plan 内编号）、`type`（search/analyze/outline/write/review）、`description`、`depends_on`（JSONB `list[str]`）、`status`、`result`（TEXT nullable）、`started_at`、`completed_at`。

- [ ] **Step 1-6**：TDD + 迁移可逆验证 + 提交 `feat: add task plan persistence schema`

### Task 12：PlannerNode 目标分解与 DAG 生成

**目标：** spec 2.3 节 `PlannerNode`，LLM 接收复合目标输出 5 步以上 `TaskPlan` JSON，Pydantic 校验 `SubTask.type` 与 `depends_on` 形成有效 DAG（无环、可达）。

**涉及文件：**
- Create: `app/application/agent/nodes/planner.py`
- Create: `app/application/agent/state.py`（新增 `TaskPlanState`）
- Create: `prompts/planning/planner.yml`
- Create: `tests/test_planner_node.py`

**interfaces：**
- Few-shot 示例约束 LLM 输出符合 spec 2.4 schema。
- DAG 校验：`depends_on` 引用的 `task_id` 必须存在于同 plan；拓扑排序无环。

- [ ] **Step 1-6**：TDD + 提交 `feat: add planner node with DAG validation`

### Task 13：TaskExecutorGraph 依赖调度与并行执行

**目标：** spec 2.3 节 `TaskExecutorGraph`，LangGraph 子图按 DAG 依赖调度 5 种 SubTask 类型，无依赖节点的并行执行。

**涉及文件：**
- Create: `app/application/agent/nodes/task_executor.py`
- Create: `app/application/agent/graphs/planner_graph.py`
- Create: `prompts/planning/{search_subtask,outline_subtask,write_subtask,review_subtask}.yml`
- Create: `tests/test_task_executor_graph.py`

**interfaces：**
- `SearchSubTask` 调用 `web_search`/`zhihu_tool`/`reddit_tool` 等（复用现有 18 工具）。
- `OutlineSubTask`、`WritingSubTask`、`ReviewSubTask` 各自调用对应 prompt + LLM。
- 并行执行：`asyncio.gather` 同一依赖层级无依赖子任务。
- 完成后写 `WorkSession` 与最终文章到 `AnswerDocument`。

- [ ] **Step 1-6**：TDD + 提交 `feat: add task executor graph with DAG scheduling`

### Task 14：TaskPlan REST API 与前端进度树

**目标：** spec 2.5 节前端——对话框「任务模式」切换 + 实时流式 TaskPlan 进度树 + 完成后填入编辑器。

**涉及文件：**
- Create: `app/api/routes/task_plans.py`
- Modify: `app/server.py`
- Create: `frontend/src/types/task-plan.ts`
- Create: `frontend/src/features/chat/task-plan-card.tsx`
- Create: `frontend/src/features/chat/task-mode-toggle.tsx`
- Create: `frontend/src/features/chat/task-plan-api.ts`
- Modify: `frontend/src/store/chat-store.ts`
- Modify: `frontend/src/features/chat/chat-panel.tsx`

**interfaces：**
- `POST /api/task-plans` 接收 `{goal, chatId}` 触发 planner_graph，返回 SSE 流（`task.started`、`task.completed`、`task.failed`、`plan.completed` 事件）。
- 前端 `TaskPlanCard` 可折叠，每子任务节点显示状态指示灯 + 耗时。

- [ ] **Step 1-6**：TDD + 提交 `feat: add task plan API and progress tree UI`

### Task 15：动态调整与失败重试

**目标：** spec 2.6 验收——单子任务失败时其他已完成任务结果保留、失败任务可单独重试；执行中若中间结果质量不达标自动重新规划剩余步骤。

**涉及文件：**
- Modify: `app/application/agent/nodes/task_executor.py`
- Modify: `app/application/agent/graphs/planner_graph.py`
- Modify: `app/api/routes/task_plans.py`
- Modify: `frontend/src/features/chat/task-plan-card.tsx`
- Create: `tests/test_task_planner_service.py`

**interfaces：**
- `POST /api/task-plans/{plan_id}/tasks/{task_id}/retry` 单任务重试。
- 中间结果质量不达标 → PlannerNode 重新规划剩余 `pending` 任务，保留已完成。
- 验收：5 步计划总耗时 ≤ 120s。

- [ ] **Step 1-6**：TDD + 提交 `feat: add task plan dynamic replanning and retry`

### Task 16：pgvector user_memories 表与迁移

**目标：** spec 3.4 节 `UserMemory` 模型，含 `embedding vector(1536)`、`memory_type`（explicit/implicit/work_pattern）、`confidence`、`activation_count`、`last_activated_at`。

**涉及文件：**
- Create: `app/persistence/models/user_memories.py`
- Create: `app/persistence/repositories/memory_repository.py`
- Create: `migrations/versions/YYYYMMDD_user_memories.py`
- Create: `tests/test_user_memory_model.py`

**interfaces：**
- HNSW cosine 索引 on `embedding`。
- `(workspace_id, memory_type)` B-tree 索引。

- [ ] **Step 1-6**：TDD + 提交 `feat: add user memory persistence schema`

### Task 17：MemoryExtractor 记忆提取节点

**目标：** spec 3.3 节 Agent 运行结束后 `MemoryExtractorNode` 用 LLM 从本次对话抽取可记忆信息，向量化后写 `user_memories`。

**涉及文件：**
- Create: `app/application/memory_service.py`
- Create: `app/application/agent/nodes/memory_extractor.py`
- Create: `prompts/memory/extract.yml`
- Create: `tests/test_memory_extractor.py`

**interfaces：**
- `async def extract_memories(messages: list, session_id: str) -> list[UserMemoryDTO`
- 3.5 验收：第二次打开 Agent 后能体现上次用户告知的写作风格。

- [ ] **Step 1-6**：TDD + 提交 `feat: add memory extractor node`

### Task 18：MemoryRetriever 检索注入节点

**目标：** spec 3.3 节 Agent 运行开始时 `MemoryRetrieverNode` 从 `user_memories` 向量检索相关记忆片段，注入 system prompt。验收 3.6：单次检索 ≤ 200ms。

**涉及文件：**
- Create: `app/application/agent/nodes/memory_retriever.py`
- Create: `prompts/memory/retrieve.yml`
- Create: `app/application/agent/tools/memory_search_tool.py`
- Modify: `app/application/agent/graphs/conversation.py`
- Modify: `app/application/agent/state.py`
- Create: `tests/test_memory_retriever.py`

**interfaces：**
- 新增字段进 `ChatAgentState`：`applied_memories: list[MemorySnippet] | None`。
- 对话界面「已应用 N 条记忆」Badge。

- [ ] **Step 1-6**：TDD + 提交 `feat: add memory retriever injection to chat agent`

### Task 19：「我的记忆」管理 UI

**目标：** spec 3.5 节——设置页「我的记忆」标签页，展示/编辑/删除记忆条目；一键清空。

**涉及文件：**
- Create: `app/api/routes/memories.py`
- Modify: `app/server.py`
- Create: `frontend/src/features/settings/memory-panel.tsx`
- Create: `frontend/src/features/settings/memory-api.ts`
- Modify: `frontend/src/features/settings/settings-page.tsx`
- Create: `frontend/src/features/chat/memory-applied-badge.tsx`

**interfaces：**
- `GET /api/memories`、`PUT /api/memories/{id}`、`DELETE /api/memories/{id}`、`DELETE /api/memories?workspaceId=...`（一键清空）。

- [ ] **Step 1-6**：TDD + `bun run typecheck` + `bun run build` + 提交 `feat: add my memories management UI`

### Task 20：Multi-Agent 状态与 Orchestrator 子图

**目标：** spec 6.4 节 LangGraph Multi-Agent 子图嵌套；`OrchestratorAgent` 接收目标、生成 TaskPlan、分配给子 Agent。新建 `MultiAgentState` 与 `multi_agent_graph.py`。

**涉及文件：**
- Create: `app/application/agent/nodes/orchestrator.py`
- Create: `app/application/agent/graphs/multi_agent_graph.py`
- Modify: `app/application/agent/state.py`（新增 `MultiAgentState`）
- Create: `prompts/multi_agent/orchestrator.yml`
- Create: `tests/test_multi_agent_graph.py`

**interfaces：**
- `MultiAgentState`：`plan`、`sub_agent_states: dict[str, AgentState]`、`research_report`、`draft`、`final_output`。
- OrchestratorAgent 无工具，只调度。

- [ ] **Step 1-6**：TDD + 提交 `feat: add orchestrator multi-agent graph`

### Task 21：ResearchAgent 并行研究子 Agent

**目标：** spec 6.6 验收——ResearchAgent 真正并行调用多个平台工具（并发 > 3）、子 Agent 状态隔离、单失败不影响其他。

**涉及文件：**
- Create: `app/application/agent/nodes/research_agent.py`
- Create: `prompts/multi_agent/research.yml`
- Create: `tests/test_research_agent_concurrency.py`

**interfaces：**
- ResearchAgent 持有 `web_search`、`zhihu_tool`、`reddit_tool`、`github_tool` 等工具集。
- `asyncio.gather` 并发调用 ≥ 4 个工具，单工具 timeout 不阻断其他。

- [ ] **Step 1-6**：TDD + 提交 `feat: add parallel research subagent`

### Task 22：WritingAgent + ReviewAgent 协作

**目标：** spec 6.3 节协作流——WritingAgent 基于 Research 报告生成初稿，ReviewAgent 自评 + 修正（复用 Phase 2 反思循环）。

**涉及文件：**
- Create: `app/application/agent/nodes/writing_agent.py`
- Create: `app/application/agent/nodes/review_agent.py`
- Create: `prompts/multi_agent/{writing,review}.yml`
- Modify: `app/application/agent/graphs/multi_agent_graph.py`
- Create: `tests/test_writing_review_agent.py`

**interfaces：**
- WritingAgent 无外部工具，依赖 RAG + LLM。
- ReviewAgent 复用 `app/application/workflows/reflection.py`。

- [ ] **Step 1-6**：TDD + 提交 `feat: add writing and review subagents`

### Task 23：MemoryAgent 集成与 interrupt/resume

**目标：** spec 6.4 节 LangGraph `interrupt/resume` 机制——Orchestrator 分配完子任务后可暂停等待用户确认；MemoryAgent 沉淀本次创作记忆（依赖 Phase 4 Task 17）。

**涉及文件：**
- Create: `app/application/agent/nodes/memory_agent.py`
- Modify: `app/application/agent/graphs/multi_agent_graph.py`
- Create: `prompts/multi_agent/memory_agent.yml`
- Modify: `app/api/routes/task_plans.py`（interrupt/resume 端点）
- Create: `tests/test_memory_agent_and_interrupt.py`

**interfaces：**
- `POST /api/task-plans/{id}/interrupt`、`POST /api/task-plans/{id}/resume`。
- MemoryAgent 调用 `memory_service.extract_memories`。

- [ ] **Step 1-6**：TDD + 提交 `feat: add memory agent and interrupt resume mechanism`

### Task 24：前端 Agent 协作树面板与端到端验收

**目标：** spec 6.5 节前端「Agent 工作区」面板——实时展示各子 Agent 运行状态树、独立日志折叠区、手动调整分配策略。最终验收所有 spec AC。

**涉及文件：**
- Create: `frontend/src/features/chat/agent-workspace-panel.tsx`
- Create: `frontend/src/features/chat/agent-status-tree.tsx`
- Create: `frontend/src/types/multi-agent.ts`
- Modify: `frontend/src/features/chat/chat-panel.tsx`
- Create: `tests/test_full_agent_upgrade_e2e.py`

**interfaces：**
- SSE 端点推送 `sub_agent.started`、`sub_agent.completed`、`sub_agent.failed` 事件。
- 端到端验收：spec 6.6 全部 4 条 + 整体执行时间比串行缩短 ≥ 40%。

- [ ] **Step 1**：写失败端到端测试，映射所有 spec 验收标准。
- [ ] **Step 2-6**：TDD + `uv run pytest tests/ -v` + `bun run typecheck` + `bun run build` + 提交 `test: cover full agent upgrade acceptance criteria`

## 验证命令

```bash
# Phase 1.5
uv run pytest tests/test_conversation_graph_rag_e2e.py tests/test_pdf_confidence_live.py tests/test_pdf_confidence.py tests/test_knowledge_api.py -v

# Phase 2
uv run pytest tests/test_reflection_loop.py tests/test_refinement_loop_integration.py tests/test_opportunity_scanner.py tests/test_scheduler.py -v
cd frontend && bun run typecheck && bun run build

# Phase 3
uv run pytest tests/test_planner_node.py tests/test_task_executor_graph.py tests/test_task_planner_service.py tests/test_task_plan_model.py -v
cd frontend && bun run typecheck && bun run build

# Phase 4
uv run pytest tests/test_memory_extractor.py tests/test_memory_retriever.py tests/test_memory_service.py tests/test_multi_agent_graph.py tests/test_research_agent_concurrency.py tests/test_full_agent_upgrade_e2e.py -v
cd frontend && bun run typecheck && bun run build

# 全量回归（每个 Phase 完成后）
docker compose up -d postgres
uv run alembic upgrade head
uv run pytest tests/ -v
cd frontend && bun test && bun run typecheck && bun run build
uv run alembic current
git diff --check
```

需要真实 LLM/平台的测试单独标记，默认 mock：

```bash
RUN_LIVE_LLM=1 uv run pytest tests/test_reflection_loop.py -v
RUN_LIVE_HOTLIST=1 uv run pytest tests/test_opportunity_scanner.py -v
```

## 提交计划

按 Phase 分批提交，每个 Phase 完成后建议打一个 git tag：

```text
Phase 1.5
  test: verify rag retrieval integrated into chat main flow
  test: verify pdf conversion confidence end to end

Phase 2 - 反思循环
  feat: add quality score persistence schema
  feat: add reflection self-evaluation workflow
  feat: add reflection-driven refinement loop
  feat: add quality score panel and reflection history

Phase 2 - 主动感知
  feat: add scheduler infrastructure and opportunity feed schema
  feat: add opportunity scanner with scoring model
  feat: add today opportunities banner and agent settings
  feat: bridge opportunity card to task plan placeholder

Phase 3 - 自主规划
  feat: add task plan persistence schema
  feat: add planner node with DAG validation
  feat: add task executor graph with DAG scheduling
  feat: add task plan API and progress tree UI
  feat: add task plan dynamic replanning and retry

Phase 4 - 长期记忆
  feat: add user memory persistence schema
  feat: add memory extractor node
  feat: add memory retriever injection to chat agent
  feat: add my memories management UI

Phase 4 - 多 Agent
  feat: add orchestrator multi-agent graph
  feat: add parallel research subagent
  feat: add writing and review subagents
  feat: add memory agent and interrupt resume mechanism
  test: cover full agent upgrade acceptance criteria
```

建议 tag：`phase-1.5-done`、`phase-2-done`、`phase-3-done`、`phase-4-done`。

## 风险与回滚

- **LLM 规划结果不稳定（Phase 3）：** PlannerNode 输出质量无法保证 → Few-shot 示例 + JSON Schema 约束 + Pydantic 严格校验 + DAG 环检测；输出非法时降级为「请补充更多上下文」而非执行错误计划。回滚：单 plan 失败标记 `failed`，不影响其他 plan。
- **长期记忆隐私合规（Phase 4）：** 敏感信息被持久化 → 全本地存储、不上传任何记忆数据、前端一键清空、`extract_memories` 调用前 LLM 提示词明确排除 PII（姓名/身份证/电话）。回滚：`DELETE FROM user_memories WHERE workspace_id=?` 一键清空。
- **多 Agent 调试困难（Phase 4）：** Bug 定位复杂 → LangGraph Studio 可视化 + 完整结构化日志 + 每个 sub_agent_state 独立 trace_id。回滚：`multi_agent_graph` 与现有 `conversation.py` 完全隔离，单 Agent 模式继续可用。
- **定时任务资源占用（Phase 2 主动感知）：** 每小时扫描消耗 API 配额 → 凌晨 1-7 点跳过、`scan_interval_hours` 可配、非活跃时段降频。回滚：`proactive_sensing_enabled=false` 关闭整个子系统。
- **反思循环死循环（Phase 2 反思）：** 迭代不收敛 → 硬性上限 3 轮、超过强制输出 + 用户告警 + QualityScore 记录「未收敛」状态。回滚：单文档反思失败不影响其他文档。
- **pgvector 维度变化（Phase 4）：** Embedding 模型升级需改维度 → 用新 `user_memories_v2` 表 + 双写过渡 + 切换后软删除旧表，不原地改维度。
- **Phase 强依赖破坏：** 若 Phase 2 启动前 Phase 1.5 未完成 → spec 7.1 节强制前置条件，CI 在 Phase 2 任务测试中加 `phase-1.5-complete` 检查标记。

## 完成标准

- **Phase 1.5（强制前置）：**
  - [ ] RAG 检索在真实 Chat 流中产出落地 Trace，4 条路径（normal+证据/normal+不足/strict 拒答/off）端到端测试通过。
  - [ ] 真实 PDF 验证：扫描页 `conversionConfidence < 0.7` 且候选稿页出现红色警告；富文本 PDF ≥ 0.9 无警告。
- **Phase 2：**
  - [ ] 首次生成评分 < 0.75 时自动触发修正（spec 4.6 #1）。
  - [ ] 每个评分维度有明确数值展示（spec 4.6 #2）。
  - [ ] 迭代修正后综合评分相比首次提升 ≥ 0.08（spec 4.6 #3）。
  - [ ] 反思循环最多 3 轮，超过强制输出并提示用户（spec 4.6 #4）。
  - [ ] 后端定时任务每小时执行一次热榜扫描，结果写入数据库（spec 5.6 #1）。
  - [ ] 推荐算法结合用户历史产出领域，排除已创作过的问题（spec 5.6 #2）。
  - [ ] 前端「今日机会」卡片实时刷新（SSE 推送）（spec 5.6 #3）。
  - [ ] 用户可在设置页关闭主动推送（spec 5.6 #4）。
- **Phase 3：**
  - [ ] 用户输入「帮我写一篇知乎回答：xxx」，Agent 自动生成并执行 5 步以上的 TaskPlan（spec 2.6 #1）。
  - [ ] 前端实时流式渲染 TaskPlan 进度（spec 2.6 #2）。
  - [ ] 单个子任务失败时其他已完成任务结果保留，失败任务可单独重试（spec 2.6 #3）。
  - [ ] TaskPlan 执行总耗时不超过 120 秒（5 步计划）（spec 2.6 #4）。
- **Phase 4 - 长期记忆：**
  - [ ] 第二次打开 Agent 后能在回答中体现上次用户明确告知的写作风格（spec 3.6 #1）。
  - [ ] 用户频繁删除「列表式结尾」后 Agent 后续生成减少该写法（spec 3.6 #2）。
  - [ ] 记忆条目在设置页可视化展示和管理（spec 3.6 #3）。
  - [ ] 单次记忆检索耗时不超过 200ms（spec 3.6 #4）。
- **Phase 4 - 多 Agent：**
  - [ ] ResearchAgent 能真正并行调用多个平台工具（并发 > 3）（spec 6.6 #1）。
  - [ ] 各子 Agent 之间状态隔离，单个失败不影响其他（spec 6.6 #2）。
  - [ ] 前端实时展示多 Agent 协作树状态图（spec 6.6 #3）。
  - [ ] 整体协作执行时间比串行方案缩短 ≥ 40%（spec 6.6 #4）。
- **全局：**
  - 后端完整 pytest 通过。
  - 前端 Bun tests/typecheck/build 全部通过。
  - Alembic migration head 与代码模型一致，升级/降级可逆。
  - 无新增 lint/type/build 错误。
  - `output/`、`generated-images/`、API 密钥、Cookie、SQLite checkpoint 未进入 Git。
  - 文档（`feature-full-agent-upgrade.md` 第 1.2 节 RAG 状态、`private-knowledge-rag-known-gaps.md` 第 3 节路线图）已按 Phase 完成度同步。

## 规格覆盖自检

- **Phase 1.5 前置：** Tasks 1、2 覆盖 spec 7.1 节三项前置条件（confidence 链路已在上一轮修复，本计划补 RAG 主链路验证 + 真实 PDF 验证）。
- **功能三 反思循环：** Tasks 3、4、5、6 覆盖 spec 第 4 节全部功能需求与 4 条验收标准。
- **功能四 主动感知：** Tasks 7、8、9、10 覆盖 spec 第 5 节功能描述与 4 条验收标准。
- **功能一 自主规划：** Tasks 11、12、13、14、15 覆盖 spec 第 2 节功能需求（目标分解、并行执行、动态调整、进度透明）与 4 条验收标准。
- **功能二 长期记忆：** Tasks 16、17、18、19 覆盖 spec 第 3 节三类记忆（显式/隐式/工作习惯）、技术方案（Extractor/Retriever）与 4 条验收标准。
- **功能五 多 Agent：** Tasks 20、21、22、23、24 覆盖 spec 第 6 节 5 专职子 Agent、协作流程、interrupt/resume 与 4 条验收标准。
- **无占位项：** spec Open Questions 未明确列出，本计划不存在 TODO/TBD；每个 Phase 的依赖、默认参数（阈值 0.75、最多 3 轮、机会得分权重 0.4/0.35/0.15/0.10、DAG 依赖 5 种 SubTask 类型）、失败策略（降级/强制输出/隔离）与验收命令均已明确。