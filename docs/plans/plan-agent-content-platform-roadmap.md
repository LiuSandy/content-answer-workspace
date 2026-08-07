# Agent 内容创作平台统一实施路线

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`
> or `superpowers:executing-plans` to execute one stage at a time. Do not start a later
> stage until the preceding stage gate is satisfied.
>
> **文档状态：** 已确认 (Approved)
>
> **关联 Specs：**
> - `docs/specs/feature-outlines-structured-generation.md`
> - `docs/specs/feature-agent-platform-split.md`
> - `docs/specs/feature-context-memory-system.md`
> - `docs/specs/content-creation-pipeline.md`
>
> **关联领域计划：**
> - `docs/plans/plan-structured-output-and-outline.md`
> - `docs/plans/plan-agent-platform-split.md`
> - `docs/plans/plan-context-memory-system.md`

## 功能概述（Overview）

本文件是上述三份领域计划之上的**唯一主实施入口**。三份领域计划不并行从头执行；
实现者必须按本文的依赖顺序选择其中的任务，并以本文定义的阶段门禁决定何时进入下一阶段。

本文解决四类跨计划问题：

1. 明确结构化输出、Agent 运行底座、上下文记忆、质检、大纲、Writer、选题、风格学习和
   发布回流之间的前后依赖。
2. 为跨计划重复修改的文件指定唯一阶段，避免 `chats.py`、`conversation.py`、
   `answer_generation.py`、`dto.py` 被多条计划反复改写。
3. 修正当前代码基线中会阻断后续实施的数据模型、消息上下文和兼容入口问题。
4. 将业务交付与可选架构重构分开；先完成可验证业务闭环，再评估全面子图化。

## 目标（Goal）

按依赖顺序交付一条可持续演进的内容创作闭环：结构化决策 → 稳定 Agent 运行 → 质检 →
上下文与长期记忆 → 观点和大纲 → 统一写作 → 选题评估 → 风格学习 → 发布与数据回流。

每个阶段必须形成独立可用、可回归、可停止的产品增量；任何阶段失败都不得迫使系统同时保留
两套长期业务实现。

## 范围（Scope）

### 包含

- 三份 Spec 中尚未完成的能力，以及实施前必须修复的直接阻断项。
- 后端服务、LangGraph 运行层、数据库迁移、API、SSE、前端交互和自动化测试。
- 三份现有领域计划的依赖排序、任务归属和验收门禁。
- 当前单用户、单服务进程部署形态下的正确性和恢复能力。

### 不包含

- 自动向知乎、小红书等平台发布内容。
- 多账号矩阵、实时协同编辑和多租户权限系统。
- 为了形式统一而强制把所有 service/workflow 改成 LangGraph 子图。
- 在 Writer 稳定前删除仍被 CLI、路由或测试使用的兼容入口。
- 使用隐式风格学习结果直接修改仓库共享的 Prompt YAML。

## 技术栈（Tech Stack）

- Python 3.11+、FastAPI、Pydantic v2、SQLAlchemy 2、Alembic、PostgreSQL、pgvector
- LangGraph、LangChain OpenAI、OpenAI-compatible DeepSeek API
- React 19、TypeScript、Vite、TanStack Query、Zustand、Tailwind CSS v4、bun
- pytest、pytest-asyncio

## 全局约束（Global Constraints）

- 路由保持轻薄；编排进入 application service 或 Agent 节点。
- API 响应保持 `{"ok": true, "data": ...}`；错误由统一异常机制包装。
- Pydantic 对外字段使用 camelCase alias，持久化前明确 `by_alias=True` 边界。
- DB messages 是对话历史权威源；LangGraph checkpoint 只保存运行态和恢复所需增量。
- 当前用户指令永不因上下文压缩被裁剪。
- 隐式记忆必须由用户确认后才进入生成上下文。
- 自由文本正文继续流式生成；结构化输出只用于决策、报告、摘要和大纲。
- 编辑器生成、润色、重写最终只能保留一个业务入口；迁移期间用薄适配层兼容旧端点。
- 前端不直接散落业务 `fetch`；新增调用进入 feature API 层。
- 修改 `.ts`/`.tsx` 后至少运行 `bun run typecheck`；修改后端业务逻辑运行相关 pytest。
- 不删除 CLI 或兼容入口，除非引用扫描、替代入口、测试迁移和用户可见行为验证均已完成。

## 依赖图与阶段门禁

```text
R0 基线与契约修正
 └─ R1 结构化输出底座
     └─ R2 Agent 运行底座 / HITL / 安全
         ├─ R3 Quality Reviewer
         └─ R4 ContextComposer / checkpoint
             └─ R5 长期记忆完善
                 ├─ R6 观点采集与大纲生命周期
                 │   └─ R7 Content Writer / 素材库 / 创作衔接
                 └─ R8 Topic Analyst
                     
R3 + R5 + R7 ── R9 风格学习
R7 ── R10 发布状态与指标 ── R11 Data Analyst

R0-R11 完成后 ── R12 可选子图化与遗留清理
```

规则：

- `R0 → R1 → R2` 严格串行。
- R3 完成后即可向用户交付质检，不等待记忆或 Writer。
- R6 只负责观点/大纲状态；R7 才迁移生成、润色、重写，避免两次重写 workflow。
- R8 依赖 R5 的用户兴趣记忆检索，但不依赖 R7。
- R9 必须能识别 R3/R7 产生的所有 AI 版本，不能只识别 `quality_adopt`。
- R11 只在 R10 已积累可用发布数据后启动。
- R12 不是业务能力的前置条件。

## 唯一任务归属

| 能力 | 唯一实施阶段 | 领域计划来源 | 禁止重复实施的位置 |
| :--- | :--- | :--- | :--- |
| `generate_structured` 与公共 schemas | R1 | structured plan P0/P2 | reviewer、memory、analyst 内不得自建 JSON 解析 |
| HITL 提交、SSE 稳定事件、运行级超时 | R2 | agent plan P0 | memory/outline 路由不得另建运行器 |
| QualityReport 与建议采纳 | R3 | agent plan P1 | outline plan 只定义 schema，不实现 reviewer |
| ContextComposer、摘要、checkpoint | R4 | memory plan P0 | agent plan 不再次改写历史组装 |
| 记忆向量检索、确认 API | R5 | memory plan P1 | analyst/writer 只消费检索接口 |
| 观点采访与大纲状态 | R6 | structured plan P1 | Writer 不自行定义第二套 Outline schema |
| 生成/润色/重写统一、素材检索 | R7 | agent plan P3 + memory plan P3 | outline/memory plan 不直接重写三个 workflow |
| 选题评估 | R8 | agent plan P2 | Data Analyst 使用独立服务和命名 |
| diff 风格学习 | R9 | memory plan P2 | Data Analyst 不重复提炼版本 diff |
| 发布状态、手动指标 | R10 | agent plan P3 前置 | 不 Agent 化 |
| 发布表现分析 | R11 | agent plan P4 | 不与 Topic Analyst 共用 `graphs/analyst.py` |
| Collector/Knowledge 全面子图化、死代码清理 | R12 | agent plan 可选重构 | 不阻塞 R3-R11 业务交付 |

## 涉及文件（Files）

本节列出主路线中的所有关键文件。各阶段开始前应以当时仓库状态重新确认行号，但不得改变职责归属。

### 公共基础设施与领域契约

- Modify: `app/domain/ports.py` — provider-neutral 结构化生成能力或对应服务端口
- Modify: `app/domain/dto.py` — 全部公共 Pydantic schemas 的唯一来源
- Modify: `app/infrastructure/llm/registry.py` — model profile 与 provider capability 路由
- Create: `app/infrastructure/llm/structured.py` — 结构化调用和降级实现
- Modify: `app/prompts/schemas.py` — context window、输出预留等 profile 字段
- Modify: `prompts/model_profiles.yml` — 每个模型的上下文规格和结构化能力

### Agent 运行与上下文

- Modify: `app/api/routes/chats.py` — HITL、SSE、上下文接入和运行串行化
- Modify: `app/application/agent/graphs/conversation.py` — 稳定编排边界
- Modify: `app/application/agent/state.py` — 明确增量输入和恢复字段
- Modify: `app/application/agent/nodes/preprocess.py` — 不覆盖合法续跑输入
- Create: `app/application/agent/scheduling.py` — 运行级 timeout/cancel/fallback
- Create: `app/application/context/composer.py` — 对话上下文预算组装
- Create: `app/application/context/summary_updater.py` — 分支级滚动摘要
- Create: `app/persistence/models/summaries.py` — 分支摘要持久化

### 记忆与创作

- Modify: `app/persistence/models/user_memories.py` — status、evidence、向量索引模型
- Modify: `app/application/memory_service.py` — 写入、去重、检索、确认语义
- Create: `app/application/memory_extractor.py` — 普通对话结束后的提取任务
- Create: `app/application/memory/style_learner_service.py` — 版本 diff 风格学习
- Create: `app/application/context/writing_background.py` — source item 级创作背景摘要
- Create: `app/application/outline_service.py` — 采访与大纲生命周期
- Create: `app/application/quality_service.py` — 质检报告与采纳
- Create: `app/application/writer_service.py` — 三类写作操作的唯一业务入口

### 持久化与 API

- Modify: `app/persistence/models/documents.py` — AI 输出元数据、发布状态
- Create: `app/persistence/models/publish_metrics.py` — 发布表现时间序列
- Modify: `app/domain/knowledge.py` — `SourceType.material`
- Modify: `app/api/routes/documents.py` — outline/review/writer/publish 端点
- Modify: `app/api/routes/memories.py` — create/pending/confirm/reject
- Modify: `app/api/routes/knowledge.py` — 素材收藏与 scope
- Modify: `app/api/routes/opportunities.py` — 评估与重评入口
- Create: `app/api/routes/publishing.py` — 发布状态与指标 CRUD
- Create: `migrations/versions/20260805_agent_content_foundation.py` — 基线和公共字段迁移
- Create: `migrations/versions/20260805_context_memory_evolve.py` — summary/status/vector/HNSW
- Create: `migrations/versions/20260805_publish_metrics.py` — 发布状态和指标

### 前端

- Modify: `frontend/src/features/chat/chat-panel.tsx` — HITL 与运行错误展示
- Modify: `frontend/src/features/chat/editor-panel.tsx` — 质检、大纲、素材和发布操作入口
- Create: `frontend/src/features/chat/quality-review-dialog.tsx` — 质检报告与采纳
- Create: `frontend/src/features/chat/outline-dialog.tsx` — 采访、大纲编辑和确认
- Modify: `frontend/src/features/settings/memory-panel.tsx` — 隐式记忆确认和证据
- Modify: `frontend/src/features/hotlist/hotlist-page.tsx` — 选题评估
- Create: `frontend/src/features/publishing/publishing-page.tsx` — 发布工作台
- Modify: `frontend/src/features/chat/prompt-templates-dialog.tsx` — 在保留变量和 user message 的前提下扩展分组

## 任务拆分（Tasks）与 TDD 执行步骤（TDD Steps）

### Task R0：修正代码基线与跨计划契约

**目标：**
消除会让后续迁移、上下文和业务测试建立在错误基础上的已知问题，并冻结跨计划公共契约。

**涉及文件：**
- Modify: `app/api/routes/chats.py`
- Modify: `app/application/opportunity_service.py`
- Modify: `app/api/routes/prompts.py`
- Modify: `app/persistence/models/documents.py`
- Create: `migrations/versions/20260805_agent_content_foundation.py`
- Test: `tests/test_chat_branching.py`
- Test: `tests/test_opportunity_scanner.py`
- Test: `tests/test_prompts_route.py`
- Test: `tests/test_document_models.py`

**接口决定：**

- `SourceItem` 继续作为跨 Chat 全局去重内容，不新增 `workspace_id`；“已创作 URL”通过
  `AnswerDocument → SourceItem` join 判断。当前单用户部署不做多租户过滤。
- `AIOperation` 新增 `output_metadata: JSONB`，结构化报告写输出字段，不占用输入字段。
- Prompt YAML 是共享模板，不承载用户隐式风格；用户确认后的隐式记忆作为用户级风格层注入。
- 当前用户消息在每次图运行中只出现一次。

**步骤：**

- [x] Step 1: 写失败测试，覆盖当前用户消息不重复、机会扫描能查询已创作文档、Prompt 更新保留
  user message/variables、`AIOperation.output_metadata` 可 round-trip。
- [x] Step 2: 分别运行上述四个测试文件，确认失败原因对应现有缺口。
- [x] Step 3: 编写最小修复和 Alembic 迁移；迁移只增加兼容字段，不删除旧字段或入口。
- [x] Step 4: 运行四个测试文件，预期全部通过。
- [x] Step 5: 运行 `uv run pytest tests/test_zhihu_import.py tests/test_prompt_composer.py -v`，确认 CLI
  关联能力与 Prompt 装配无回归。
- [x] Step 6: 提交，建议信息：`fix: stabilize agent content foundations`。

**阶段门禁：** 迁移 upgrade/downgrade 测试通过；不存在重复当前消息；机会扫描不再访问不存在字段；
Prompt 更新不破坏模板结构。

### Task R1：建立结构化输出公共底座

**目标：**
让路由、质检、选题、记忆、摘要和大纲共享同一结构化输出能力与 schema，停止新增手写 JSON 解析。

**涉及文件：**
- Create: `app/infrastructure/llm/structured.py`
- Modify: `app/domain/ports.py`
- Modify: `app/domain/dto.py`
- Modify: `app/infrastructure/llm/registry.py`
- Modify: `app/application/agent/adapters.py`
- Modify: `app/application/agent/nodes/route_intent.py`
- Modify: `app/prompts/schemas.py`
- Modify: `prompts/model_profiles.yml`
- Test: `tests/test_structured_output.py`
- Test: `tests/test_route_intent_modes.py`

**接口决定：**

- `StructuredResult[T]` 包含 `value`、`method_used`、`attempts`、`degradation_reason`；底层不直接写 DB。
- 调用方把降级元数据写入自己的 `AIOperation.model_parameters`。
- provider profile 明确声明 `structured_methods`；不支持 `json_schema` 的兼容端点直接从
  `json_mode` 开始，不用异常探测能力。
- `QualityReport` 分数统一为 `0..100` 整数。
- `TopicEvaluation` 固定包含 `worth_score/reason/competition_level/user_match/suggestion`。

**步骤：**

- [x] Step 1: 写 `tests/test_structured_output.py`，覆盖 profile 能力选择、Pydantic 校验、一次重试、
  JSON mode 降级、通用解析降级和 `StructuredResult` 元数据。
- [x] Step 2: 运行测试，确认因公共类型和实现不存在而失败。
- [x] Step 3: 实现公共 schemas、provider capability 和结构化生成服务。
- [x] Step 4: 将 `route_intent` 的 LLM 分支切换到公共接口，保留规则优先、显式 strict/off 和
  低置信度降级。
- [x] Step 5: 运行 `uv run pytest tests/test_structured_output.py tests/test_route_intent_modes.py tests/test_intent_rules.py tests/test_chat_branching.py -v`。
- [x] Step 6: 提交，建议信息：`feat: add shared structured generation`。

**阶段门禁：** 路由无手写 JSON；五类公共 schema 可导入；DeepSeek profile 不错误假定原生
`json_schema`；降级结果可由业务调用方审计。

### Task R2：稳定 Agent 运行、HITL、SSE 与工具安全

**目标：**
建立后续业务节点共用的运行语义，不在这一阶段全面迁移 Writer、Reviewer 或 Knowledge 子图。

**涉及文件：**
- Create: `app/application/agent/scheduling.py`
- Modify: `app/api/routes/chats.py`
- Modify: `app/application/agent/nodes/preprocess.py`
- Modify: `app/application/agent/graphs/conversation.py`
- Modify: `frontend/src/features/chat/chat-panel.tsx`
- Modify: `app/application/agent/tools/web_fetch.py`
- Modify: `app/application/agent/tools/crawl4ai_tool.py`
- Modify: `app/application/agent/tools/firecrawl_tool.py`
- Modify: `app/application/agent/tools/code_interpreter.py`
- Test: `tests/test_hitl_choice_api.py`
- Test: `tests/test_agent_timeout.py`
- Test: `tests/test_chat_sse_events.py`
- Test: `tests/test_agent_tool_security.py`

**步骤：**

- [x] Step 1: 写失败测试，覆盖 choice 消息校验、选择 ID 白名单、重复提交幂等、原 context 快照恢复、
  `preprocess` 不清空续跑选择。
- [x] Step 2: 实现 `POST /api/chats/{chat_id}/choices`，以 choice request 为 parent 保存选择消息，
  并用原分支 checkpoint 续跑。
- [x] Step 3: 写运行级 timeout/cancel/fallback 测试，确认生成不可自动重试、幂等检索最多重试一次、
  已持久化部分结果不丢失。
- [x] Step 4: 实现调度包装和稳定 SSE 事件封装；事件不依赖单一 `langgraph_node` 字符串。
- [x] Step 5: 写安全测试，覆盖初始 URL、重定向 URL、环回/私网/云元数据地址、响应大小上限，
  并断言代码解释器默认不注册。
- [x] Step 6: 实现安全策略与前端 HITL/`agent.error` 状态。
- [x] Step 7: 运行 `uv run pytest tests/test_hitl_choice_api.py tests/test_agent_timeout.py tests/test_chat_sse_events.py tests/test_agent_tool_security.py tests/test_chat_branching.py -v`，再运行前端 typecheck。
- [x] Step 8: 提交，建议信息：`feat: harden agent runtime and hitl`。

**阶段门禁：** 用户选择能够真实续跑；断线和超时有稳定终态；RAG/task plan/multi-agent 事件回归通过；
默认工具集合不包含任意代码执行。

### Task R3：交付 Quality Reviewer

**目标：**
以最小业务闭环交付“生成后质检 → 查看报告 → 逐条采纳 → 新版本”的用户价值。

**涉及文件：**
- Create: `app/application/quality_service.py`
- Create: `prompts/review/quality_review.yml`
- Modify: `app/api/routes/documents.py`
- Modify: `frontend/src/features/chat/editor-panel.tsx`
- Create: `frontend/src/features/chat/quality-review-dialog.tsx`
- Test: `tests/test_quality_review.py`

**步骤：**

- [x] Step 1: 写失败测试，覆盖合法报告、结构化失败、报告写入 `output_metadata`、来源版本锁定、
  单条采纳、重复采纳幂等和乐观锁冲突。
- [x] Step 2: 实现 `QualityService.review()` 和 `QualityService.adopt_suggestion()`；采纳版本使用
  `version_type=inline_refinement`，操作类型使用 `quality_adopt` 并回填 `result_version_id`。
- [x] Step 3: 增加 review/adopt API 和 Prompt。
- [x] Step 4: 实现前端 loading、empty、error、报告列表、已采纳状态和冲突刷新。
- [x] Step 5: 运行 `uv run pytest tests/test_quality_review.py tests/test_reflection_loop.py tests/test_refinement_loop_integration.py -v` 和 `bun run typecheck && bun run build`。
- [x] Step 6: 提交，建议信息：`feat: add quality review and adoption`。

**阶段门禁：** 报告可恢复查询；采纳生成新版本且不覆盖并发编辑；StyleLearner 能通过 operation
关联识别该版本为 AI 版本。

### Task R4：实现分支级 ContextComposer 与 checkpoint

**目标：**
让长对话在模型输入预算内运行，并使同一分支可恢复而不重复注入 DB 历史和 checkpoint 消息。

**涉及文件：**
- Create: `app/application/context/composer.py`
- Create: `app/application/context/summary_updater.py`
- Create: `app/persistence/models/summaries.py`
- Create: `migrations/versions/20260805_context_memory_evolve.py`
- Modify: `app/api/routes/chats.py`
- Modify: `app/application/agent/state.py`
- Test: `tests/test_context_composer.py`
- Test: `tests/test_chat_checkpoint_resume.py`

**接口决定：**

- 摘要唯一键为 `(chat_id, branch_root_message_id)`。
- 摘要保存 `covered_message_ids`、`last_covered_message_id` 和乐观版本号，旧异步任务不得覆盖新摘要。
- 已存在 checkpoint 的分支只向图传入本轮增量；缺失 checkpoint 时才从 DB 分支路径重建。
- 当前支持单服务进程；按 checkpoint key 的 `asyncio.Lock` 是当前部署约束，多 worker 不在本路线范围。

**步骤：**

- [x] Step 1: 写预算测试，覆盖 40 轮、CJK、超长 RAG、超长当前指令、最近两轮保留和输出 token 预留。
- [x] Step 2: 实现 profile 字段和 `ContextComposer.assemble()`。
- [x] Step 3: 写摘要分支隔离、增量覆盖、旧任务晚完成不覆盖新版本的失败测试。
- [x] Step 4: 实现摘要模型、迁移和 compare-and-swap 更新。
- [x] Step 5: 写 checkpoint 首次重建、连续请求只传增量、分支隔离和同分支串行测试。
- [x] Step 6: 接入 chats 路由与图输入。
- [x] Step 7: 运行 `uv run pytest tests/test_context_composer.py tests/test_chat_checkpoint_resume.py tests/test_chat_branching.py tests/test_chat_rag_sources.py -v`。
- [x] Step 8: 提交，建议信息：`feat: add bounded conversational context`。

**阶段门禁：** 40 轮输入不超 profile 预算；分支摘要不串扰；连续请求无消息重复；SSE 回归通过。

### Task R5：完善长期记忆与确认流程

**目标：**
让普通对话能沉淀、语义检索和管理记忆，并为 Writer、Topic Analyst 和 StyleLearner 提供稳定接口。

**涉及文件：**
- Modify: `app/persistence/models/user_memories.py`
- Modify: `migrations/versions/20260805_context_memory_evolve.py`
- Modify: `app/application/memory_service.py`
- Create: `app/application/memory_extractor.py`
- Modify: `app/api/routes/memories.py`
- Modify: `frontend/src/features/settings/memory-panel.tsx`
- Modify: `frontend/src/features/chat/memory-applied-badge.tsx`
- Test: `tests/test_memory_pipeline.py`
- Test: `tests/test_memory_api.py`

**接口决定：**

- 迁移先校验既有 ARRAY embedding 维度，再转换为 `vector(1536)`，然后创建 cosine HNSW 索引。
- 旧显式记忆回填 `status=active`；隐式记忆初始为 `pending_confirmation`。
- 检索只返回 active；编辑内容后重新 embedding；无 embedding 旧数据使用精确文本兜底。
- 提取任务在 assistant 消息成功持久化后提交，不作为 LangGraph preprocess 节点执行。

**步骤：**

- [x] Step 1: 写迁移测试，覆盖有效数组转换、错误维度拒绝、旧状态回填和 HNSW 索引存在。
- [x] Step 2: 写提取/去重/active-only 检索/编辑重嵌入/超时静默降级测试。
- [x] Step 3: 实现模型、迁移和 MemoryService 接口。
- [x] Step 4: 接入普通对话完成后的后台提取；同一 run 使用幂等键避免重复提取。
- [x] Step 5: 实现 create/pending/confirm/reject API、证据展示和 Badge trace 详情。
- [x] Step 6: 运行 `uv run pytest tests/test_memory_service.py tests/test_memory_pipeline.py tests/test_memory_api.py -v` 和前端 typecheck/build。
- [x] Step 7: 提交，建议信息：`feat: complete long term memory lifecycle`。

**阶段门禁：** 数据库真实使用 vector/HNSW；pending/rejected 不注入；普通聊天可沉淀且重复运行不重复写入。

### Task R6：建立观点采访与大纲生命周期

**目标：**
完成“采访问题 → 用户回答或跳过 → 大纲生成/编辑 → 确认”的独立业务增量，不在本阶段迁移正文生成。

**涉及文件：**
- Create: `app/application/outline_service.py`
- Create: `prompts/outline/answer_outline.yml`
- Modify: `app/api/routes/documents.py`
- Create: `frontend/src/features/chat/outline-dialog.tsx`
- Modify: `frontend/src/features/chat/editor-panel.tsx`
- Test: `tests/test_outline_service.py`
- Test: `tests/test_outline_api.py`

**接口决定：**

- Outline 与 viewpoint 快照存入 `AIOperation.input_metadata`，operation type 为 `outline`。
- input metadata 固定包含 `outlineStatus`、`viewpointQuestions`、`viewpointAnswers`、`outline`、
  `sourceItemId`、`documentLockVersion`。
- 每个 section 具有稳定 `id`、`order`、`heading`、`keyPoints`、`wordCountEstimate`。
- API 覆盖 generate、update、regenerate、confirm、get-current；所有修改携带 expected lock version。

**步骤：**

- [x] Step 1: 写 schema 与服务失败测试，覆盖跳过采访、编辑大纲、重生成、确认后禁止直接修改和并发冲突。
- [x] Step 2: 实现 Prompt、OutlineService 和 AIOperation 状态读取。
- [x] Step 3: 写 API 测试并实现五个生命周期端点。
- [x] Step 4: 实现前端采访、预览、编辑、确认、恢复和错误状态。
- [x] Step 5: 运行 `uv run pytest tests/test_outline_service.py tests/test_outline_api.py tests/test_prompt_composer.py -v` 和前端 typecheck/build。
- [x] Step 6: 提交，建议信息：`feat: add viewpoint and outline workflow`。

**阶段门禁：** 关闭页面后可恢复大纲；确认快照不可被旧请求覆盖；未确认大纲不能进入按段生成。

### Task R7：统一 Content Writer、创作背景与素材库

**目标：**
建立唯一 Writer 业务入口，并让确认后的观点、大纲、L2 记忆、对话背景和素材检索共同参与生成。

**涉及文件：**
- Create: `app/application/writer_service.py`
- Create: `app/application/context/writing_background.py`
- Modify: `app/domain/knowledge.py`
- Modify: `app/api/routes/knowledge.py`
- Modify: `app/api/routes/documents.py`
- Modify: `app/workflows/answer_generation.py`
- Modify: `app/workflows/inline_refinement.py`
- Modify: `app/workflows/full_rewrite.py`
- Modify: `frontend/src/features/chat/editor-panel.tsx`
- Test: `tests/test_writer_service.py`
- Test: `tests/test_writing_background.py`
- Test: `tests/test_material_knowledge.py`

**接口决定：**

- `WriterService.run(operation, document_id, expected_lock_version, ...)` 是 generate/refine/rewrite 的唯一入口。
- 旧 workflow 暂时保留为薄适配器，内部调用 WriterService；路由和前端 SSE 契约保持不变。
- 创作上下文优先级为当前指令 > 原文 > 确认观点/大纲 > 平台风格 > active L2 记忆 >
  对话背景 > material RAG。
- 素材检索必须使用 `source_type=material` scope，不与普通知识文档混用。

**步骤：**

- [x] Step 1: 写 Writer 三 operation、锁冲突、流式事件和版本类型测试。
- [x] Step 2: 写 A/B/C source item 背景隔离、缓存推进和设置关闭测试。
- [x] Step 3: 写素材收藏、自动索引、scope 检索和 `[S1]` 引用测试。
- [x] Step 4: 实现 WriterService、创作 Context、material 类型和 API。
- [x] Step 5: 把三个旧 workflow 改为薄适配层，并让 documents 路由只依赖 WriterService。
- [x] Step 6: 接入前端大纲确认生成、素材收藏和现有生成/润色/重写按钮。
- [x] Step 7: 运行 Writer、背景、素材、现有生成/精修/重写测试以及前端 typecheck/build。
- [x] Step 8: 提交，建议信息：`feat: unify contextual content writing`。

**阶段门禁：** 三类写作操作只有一个实现；旧 API 行为兼容；文章之间上下文不串扰；素材引用可追溯。

### Task R8：交付 Topic Analyst

**目标：**
用规则分筛选候选，再对 Top-N 进行带用户匹配度的结构化 LLM 评估。

**涉及文件：**
- Modify: `app/application/opportunity_service.py`
- Create: `app/application/topic_analyst_service.py`
- Create: `prompts/analysis/topic_evaluation.yml`
- Modify: `app/persistence/models/opportunity_feeds.py`
- Modify: `app/api/routes/opportunities.py`
- Modify: `frontend/src/features/hotlist/hotlist-page.tsx`
- Modify: `frontend/src/features/chat/today-opportunities-banner.tsx`
- Test: `tests/test_topic_analyst.py`

**步骤：**

- [x] Step 1: 写规则 Top-N、active 兴趣记忆注入、结构化结果、失败保留规则分、重评幂等和配额限制测试。
- [x] Step 2: 实现评估字段迁移、TopicAnalystService 和 Prompt。
- [x] Step 3: 接入 APScheduler 扫描后的评估任务和手动重评 API；不使用无持久语义的"队列"表述。
- [x] Step 4: 实现热榜和机会列表的徽章、理由、仅规则分状态和失败重试入口。
- [x] Step 5: 运行 `uv run pytest tests/test_opportunity_scanner.py tests/test_topic_analyst.py -v` 和前端 typecheck/build。
- [x] Step 6: 提交，建议信息：`feat: add memory aware topic evaluation`。

**阶段门禁：** 未进 Top-N 的候选不调用 LLM；失败不影响机会展示；评分 schema 与前端单位一致。

### Task R9：实现可确认的风格学习

**目标：**
只从 AI 版本到用户手动版本的真实编辑中提炼规则，经确认后作为用户级隐式记忆生效。

**涉及文件：**
- Create: `app/application/memory/style_learner_service.py`
- Modify: `app/application/version_service.py`
- Modify: `app/api/routes/memories.py`
- Modify: `frontend/src/features/settings/memory-panel.tsx`
- Test: `tests/test_style_learner.py`

**步骤：**

- [ ] Step 1: 写版本分类测试，覆盖 initial/refine/rewrite/quality_adopt/outline-generated 与 manual checkpoint，
  并确认所有 AI→AI 对被跳过。
- [ ] Step 2: 写每文档每来源版本对只分析一次、证据 diff 持久化、pending 不生效、confirm 生效、reject 不生效测试。
- [ ] Step 3: 实现 StyleLearnerService 和版本保存后的幂等任务触发。
- [ ] Step 4: 复用 memory confirm/reject API；active implicit memory 进入 Writer 的用户级风格层，不修改共享 YAML。
- [ ] Step 5: 实现前端证据 diff、确认、拒绝和撤销反馈。
- [ ] Step 6: 运行 `uv run pytest tests/test_style_learner.py tests/test_memory_pipeline.py tests/test_quality_review.py tests/test_writer_service.py -v` 和前端 typecheck/build。
- [ ] Step 7: 提交，建议信息：`feat: learn confirmed user style preferences`。

**阶段门禁：** AI→AI 不产出风格记忆；未确认规则不改变生成；同一版本对不会重复分析。

### Task R10：增加发布状态与手动指标

**目标：**
为内容创作链路提供明确出口，并为 Data Analyst 建立可信数据源。

**涉及文件：**
- Modify: `app/persistence/models/documents.py`
- Create: `app/persistence/models/publish_metrics.py`
- Create: `migrations/versions/20260805_publish_metrics.py`
- Create: `app/api/routes/publishing.py`
- Create: `frontend/src/features/publishing/publishing-page.tsx`
- Modify: `frontend/src/app/App.tsx`
- Test: `tests/test_publishing.py`

**步骤：**

- [ ] Step 1: 写 draft→ready→published 状态转换、published 字段约束、URL 校验、重复指标时间点和删除策略测试。
- [ ] Step 2: 实现迁移、模型、状态服务和手动指标 CRUD。
- [ ] Step 3: 实现发布工作台的 draft/ready/published 分组、平台格式复制、URL 回填、指标录入和错误状态。
- [ ] Step 4: 运行 `uv run pytest tests/test_publishing.py tests/test_answer_service.py -v` 和前端 typecheck/build。
- [ ] Step 5: 提交，建议信息：`feat: add publishing workflow and metrics`。

**阶段门禁：** 不执行自动发布；每条指标保留抓取/录入时间；published 文档拥有 URL 和发布时间。

### Task R11：增加发布表现 Data Analyst

**目标：**
基于已积累的发布指标生成可追溯分析，反哺选题建议但不自动改写用户风格。

**涉及文件：**
- Create: `app/application/publish_analyst_service.py`
- Create: `prompts/analysis/publish_performance.yml`
- Modify: `app/api/routes/publishing.py`
- Modify: `frontend/src/features/publishing/publishing-page.tsx`
- Test: `tests/test_publish_analyst.py`

**步骤：**

- [ ] Step 1: 写数据不足拒绝、时间窗口聚合、指标缺失、异常值和结构化分析结果测试。
- [ ] Step 2: 实现独立 PublishAnalystService；不复用 TopicAnalyst 的文件或 state。
- [ ] Step 3: 实现手动触发分析和报告查询 API，报告记录输入指标快照和生成时间。
- [ ] Step 4: 实现前端数据不足、运行中、失败、报告和引用内容入口。
- [ ] Step 5: 运行 `uv run pytest tests/test_publish_analyst.py tests/test_publishing.py tests/test_topic_analyst.py -v` 和前端 typecheck/build。
- [ ] Step 6: 提交，建议信息：`feat: analyze published content performance`。

**阶段门禁：** 没有足够指标时不生成伪结论；报告可追溯到输入快照；分析不自动修改 style rules。

### Task R12：评估子图化并清理遗留实现

**目标：**
在业务边界稳定后，根据可观测性、恢复和取消的真实收益决定子图化范围，并删除已完成替代的旧入口。

**涉及文件：**
- Potential Create: `app/application/agent/graphs/collector.py`
- Potential Create: `app/application/agent/graphs/writer.py`
- Potential Create: `app/application/agent/graphs/reviewer.py`
- Modify: `app/application/agent/graphs/conversation.py`
- Review/Delete only after proof: `app/application/agent/graphs/analysis.py`
- Review/Delete only after proof: `app/application/agent/graphs/refinement.py`
- Review/Delete only after proof: `app/application/chat_conversation_run_service.py`
- Review/Delete only after CLI migration: `app/application/workflow_service.py`
- Review/Delete only after CLI migration: `app/workflow.py`
- Review/Delete only after reference migration: `app/application/generation_job_service.py`
- Test: `tests/test_agent_graphs.py`
- Test: `tests/test_cli.py`

**步骤：**

- [ ] Step 1: 用调用图和测试清单证明每个候选文件是否仍有路由、CLI、测试或导入引用。
- [ ] Step 2: 为能带来独立 checkpoint、取消或事件可观测收益的领域写子图回归测试；纯 CRUD/service 不子图化。
- [ ] Step 3: 逐个迁移并运行对话、URL、RAG、Writer、Reviewer、CLI 回归；禁止一次删除整个列表。
- [ ] Step 4: 每删除一个兼容入口后运行 `rg` 引用扫描和对应测试，确认无活跃调用。
- [ ] Step 5: 运行全量后端测试、前端 typecheck/build 和 `git diff --check`。
- [ ] Step 6: 提交，建议拆分为 `refactor: extract stable agent subgraphs` 与
  `chore: remove replaced legacy workflows` 两个提交。

**阶段门禁：** 每个删除项均有替代入口和回归证据；子图化不改变 SSE/API 契约；CLI 要么迁移后可用，
要么经过单独产品决策明确移除。

## 验证命令（Verification Commands）

每阶段运行任务中列出的定向测试。每个里程碑结束额外运行：

```bash
uv run pytest tests/ -v
```

预期：全部测试通过；真实网络、Cookie、LLM 路径使用 mock，不依赖外部服务。

```bash
cd frontend && bun run typecheck && bun run build
```

预期：TypeScript 无错误，Vite production build 成功。

```bash
git diff --check
```

预期：无空白错误。

涉及迁移的阶段还必须在临时测试数据库验证：

```bash
uv run alembic upgrade head
uv run alembic downgrade -1
uv run alembic upgrade head
```

预期：升级、单步回滚、再次升级均成功；业务数据保留策略符合对应阶段说明。

## 提交计划（Commit Plan）

- 每个 Task 至少一个独立提交，Task 内迁移与依赖它的模型代码不得拆成不可运行的两个提交。
- 前后端可在同一业务 Task 中提交，确保该提交代表一个完整可验证增量。
- 推荐提交顺序与本文 R0-R12 一致。
- 不在路线文档阶段创建或提交任何实现代码。
- 进入下一阶段前，由评审者确认前一阶段门禁和验证输出。

## 风险与回滚（Risks and Rollback）

| 风险 | 控制与回滚 |
| :--- | :--- |
| ARRAY → vector 数据转换失败 | 迁移前校验维度并保留原列备份；转换与索引分步执行，失败时回滚新列 |
| checkpoint 与 DB 双重消息累积 | DB 为权威；切换采用分支级 feature flag，失败时恢复 per-run thread 和 DB 重建 |
| HITL 重复提交产生重复副作用 | choice request + selection 建唯一幂等键；只允许 pending 请求消费一次 |
| Writer 迁移破坏编辑器 SSE | 旧 workflow 先变薄适配器；前端契约测试通过后再删除旧实现 |
| Prompt 编辑损坏模板 | 更新时保留完整 messages/variables；写盘前 schema 校验，失败不替换原文件 |
| 后台任务在进程重启时丢失 | 可见任务保留持久状态与手动重试；摘要/记忆以下次幂等触发补偿 |
| 隐式学习污染风格 | pending 默认不检索；仅用户 confirm 后 active；拒绝和删除立即停止注入 |
| LLM 评估成本不可控 | Topic Analyst 先规则 Top-N；每轮上限、手动重评和失败状态显式化 |
| 大规模子图化造成回归 | 延迟到 R12；只对子图收益可证明的领域迁移，逐个回归 |

## 完成标准（Definition of Done）

- R0-R11 的所有阶段门禁均满足；R12 按评估结果完成必要部分或明确保持 service 形态。
- 三份领域计划的每项未完成功能都有且只有一个主路线 Task 负责。
- 公共 schemas、评分单位、版本分类和错误语义在前后端一致。
- 所有迁移经过 upgrade/downgrade/upgrade 验证。
- 后端全量测试、前端 typecheck/build、`git diff --check` 全部通过。
- 无新增手写 LLM JSON 解析；自由文本流式生成不被结构化输出约束。
- 同一业务能力没有长期双轨实现。
- 用户确认隐式记忆前，生成结果不受其影响。
- 发布分析不会在缺少真实指标时生成误导性结论。
- 原三份 Spec/Plan 在实施过程中若发生契约变化，必须先同步文档并重新评审，再继续对应阶段。

