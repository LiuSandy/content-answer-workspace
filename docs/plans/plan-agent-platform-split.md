# [实现计划] 专业 Agent 平台拆分

> **文档状态**：已确认 (Approved)
> **关联 Spec**：[docs/specs/feature-agent-platform-split.md](../specs/feature-agent-platform-split.md)
> **跨 Spec 依赖**：结构化输出（`generate_structured`）供 reviewer/analyst 使用；
> 本计划重构后的 `conversation_graph` 是记忆系统节点的挂载点。
>
> **2026-08-05 同步**：`feature/private-knowledge-rag` 已落地五大能力（5 子 Agent
> 顺序协作、TaskPlan DAG、长期记忆、反思循环、机会感知、三层意图、HITL）。
> 以下列表保留全部计划项，已落地的标 ✅，剩余工作为 ◻️（详见 §0）。
>
> **2026-08-05 评审补充（spec 2.1）**：P0 额外包含 HITL 提交入口、SSE 子图事件
> 回归、安全边界、立即删除全部死代码（含 `ChatConversationRunService`）；P3 前置
> 发布状态管理 + `PublishMetrics`；Topic Analyst 采用 Top-N LLM 评估。

---

## 0. 已实现基线（feature/private-knowledge-rag，权威 spec：feature-full-agent-upgrade.md）

| 能力 | 已落地 | 剩余工作 |
| :--- | :--- | :--- |
| 5 子 Agent 协作 | ✅ `nodes/multi_agent.py`（orchestrator/research/writing/review/memory 顺序调用） | 演进为 LangGraph 子图 + 子 Agent 运行级超时（§11） |
| 自主规划 | ✅ `task_planner_service.py`（TaskPlan DAG） | — |
| 长期记忆 | ✅ `user_memories` 表 + `memory_service.py` + `memory_retriever.py` | 向量检索、提取接入主对话图 |
| 反思循环 | ✅ `workflows/reflection.py` + `reflect_refine.py` | QualityReport schema + 一键采纳 |
| 主动感知 | ✅ `opportunity_service.py` + `scheduler/` | LLM 评估 + 热榜入口 |
| 三层意图 | ✅ `route_intent.py` + `intent_rules.py` | LLM 分支改 `generate_structured`（outline plan） |
| HITL | ✅ `hitl_decision.py`（节点产生 choice_request） | ◻️ **提交入口 API + 续跑**（spec §4.1/§11.7，P0） |
| 前端面板 | ✅ 7 个组件（agent-workspace-panel 等） | 质检采纳 / 评分徽章等 |
| API | ✅ `/api/opportunities` `/api/task-plans` `/api/memories` `/api/multi-agent` | — |
| 死代码 | — | ❌ `analysis.py` / `refinement.py` / `chat_conversation_run_service.py` / `workflow_service.py` / `app/workflow.py` / `generation_job_service.py` 待删（当前即死代码，P0 删） |

---

## 1. 拟修改与新增的文件列表

### 1.1 子图新建 (Sub-graphs) — ◻️ 尚未子图化（当前 multi_agent 为顺序调用）
* **[NEW] `app/application/agent/graphs/collector.py`**
  * `CollectorState` + `build_collector_graph()`：`parse_url` / `normalize_and_persist` 移入，输出 `ToolResult`
* **[NEW] `app/application/agent/graphs/knowledge.py`**
  * `RetrievalState` + `build_knowledge_graph()`：`knowledge_decision` + `retrieve_knowledge` 移入，输出 `RetrievalResult`
* **[NEW] `app/application/agent/graphs/reviewer.py`**
  * `ReviewerState` + `build_reviewer_graph()`：质检报告节点（调用 `generate_structured`）
* **[NEW] `app/application/agent/graphs/analyst.py`**
  * `AnalystState` + `build_analyst_graph()`：`evaluate_topic` 选题评估节点
* **[NEW] `app/application/agent/graphs/writer.py`**
  * `WriterState` + `build_writer_graph()`：观点采集 → 大纲 → 分段生成（依赖 outline spec）
  * **统一三类生成**：`generate_first` / `refine_selection` / `rewrite_full`
    （承接现有 answer_generation / inline_refinement / full_rewrite，保留流式事件契约）
  * 可选配图步骤（复用 `image_service`）

### 1.2 Orchestrator 改造
* **[MODIFY] `app/application/agent/graphs/conversation.py`**
  * ✅ 已含 `multi_agent` / `task_plan` 分支与递归上限 20
  * ◻️ 新增 `assign_agent` 条件路由 → 调用 collector / reviewer / analyst / writer 子图
* **[MODIFY] `app/application/agent/state.py`**
  * ✅ `MultiAgentState` / `SubAgentState` 已实现（子 Agent 状态隔离）
  * ◻️ 子图独立 State（`CollectorState` / `RetrievalState` / `ReviewerState` 等）
* **[MODIFY] `app/application/agent/nodes/route_intent.py`**
  * ✅ 三层意图已实现，意图集 `chat` / `parse_url` / `task_plan` / `multi_agent`（规则层另有 `collect`）
  * ◻️ 扩展 `create_answer` / `analyze` / `review`（保留规则优先）
* **[NEW] `app/application/agent/scheduling.py`**：`invoke_subgraph()`——`asyncio.wait_for` 子图运行级超时 + 按任务分类降级（spec §11.2/11.3）；降级写入 `AIOperation.model_parameters`（`reason=subagent_timeout`）
* **[MODIFY] `app/config/`**：子图超时预算（collector 60s / knowledge 15s / writer 90s / reviewer 30s / analyst 30s）
* **[MODIFY] `app/application/agent/nodes/chat_node.py`（或 SSE 封装）**：新增 `agent.error` 事件（spec §11.6）
* **[NEW] `app/api/routes/chats.py` HITL 端点（评审补充，spec §11.7）**：
  `POST /api/chats/{chat_id}/choices`（body `{messageId, selection}`）→ 校验
  `choice_request` 消息 → 保存选择消息 → 带 `hitl_selection` + `hitl_choice.context`
  续跑；`preprocess.py` 已有 `hitl_selection` 初始化，透传即可
* **[MODIFY] `app/api/routes/chats.py` SSE 事件匹配（评审补充，spec §11.8）**：
  子图化后 `metadata.langgraph_node` 匹配失效 → 改为子图感知匹配 / 关键节点
  显式事件名，保证 `rag.sources` / `task_plan.created` / `multi_agent.status` 仍透传

### 1.3 领域服务与提示词
* **[NEW] `app/application/quality_service.py`**：质检报告组装、`AIOperation` 存档、建议一键采纳（走 Writer `refine_selection`，版本标记 `operation_type=quality_adopt`，`AIOperation.result_version_id` 回填；采纳版本 `version_type=inline_refinement`，见 spec §4.6 版本溯源方案 A）
* **[NEW] `prompts/analysis/topic_evaluation.yml`**：选题评分 Few-shot 模板（Top-N 后置 LLM，见 Phase 2）
* **[NEW] `prompts/review/quality_review.yml`**：质检 LLM-as-judge 模板
* 现状备注：✅ `workflows/reflection.py` + `reflect_refine.py` 已承担评分与迭代修正；✅ `agents/adapters.py` 已有 `DeepSeekLLMAdapter`；◻️ `scheduling.py` 未实现，`run_multi_agent_plan` 无运行级超时

### 1.4 死代码清理（评审补充：当前即死代码，P0 一并删除）
* **[DELETE] `app/application/agent/graphs/analysis.py`**（旧热榜分析单例）
* **[DELETE] `app/application/agent/graphs/refinement.py`**（旧精修图）
* **[DELETE]** `app/application/agent/adapters.py` 中无引用的 `HotlistServiceAdapter` / `LLMClientPort` 相关残留
* **[DELETE]** 旧批量采集编排 `app/application/workflow_service.py`、`app/workflow.py`、`app/application/generation_job_service.py`
* **[DELETE]** `app/application/chat_conversation_run_service.py`（运行缓存，前端无调用、未挂载路由）

### 1.5 前端
* ✅ 已实现：`agent-workspace-panel.tsx`（子 Agent 状态树）、`task-plan-card.tsx`、`quality-score-panel.tsx`、`today-opportunities-banner.tsx`
* **[MODIFY] `frontend/src/features/chat/chat-panel.tsx`**：Agent 执行链展示（复用 `agent.status` / `tool.started` 事件）+ **HITL 选择卡片**（`choice.requested` → 选项 → 提交 `POST /api/chats/{id}/choices` → 流式等待）
* **[MODIFY] `frontend/src/features/chat/editor-panel.tsx`**：质检按钮 + 报告面板
* **[NEW] `frontend/src/features/chat/quality-review-dialog.tsx`**：质检报告对话框（逐条建议采纳）
* **[MODIFY] `frontend/src/features/chat/prompt-templates-dialog.tsx`**：升级为通用提示词管理（+outline/review/analysis/memory/summary 分组）
* **[MODIFY] `frontend/src/features/hotlist/hotlist-page.tsx`**：选题评分徽章 + 理由 tooltip

### 1.6 测试
* **[NEW] `tests/test_agent_graphs.py`**：collector/knowledge 子图与 Orchestrator 编排；**子图内完成 RAG/task_plan 后 SSE 事件仍可透传**（spec §11.8 回归）
* **[NEW] `tests/test_agent_timeout.py`**：子图超时 → 降级路径（可重试重试 1 次 / 部分结果保留 / 不可重试直接降级）、`agent.error` 事件、取消传播（spec §11）
* **[NEW] `tests/test_quality_review.py`**：质检报告生成与采纳链路（含 `result_version_id` 溯源断言）
* **[NEW] `tests/test_hitl_choice_api.py`**（评审补充）：`choice.requested` → 提交 `POST /choices` → 续跑消费 `hitl_selection`
* **[MODIFY] `tests/test_chat_branching.py`**：子图调用后对话/URL 导入/RAG 三条链路回归

### 1.7 安全（评审补充，spec §12）
* **[MODIFY] `app/application/agent/tools/web_fetch.py` / `crawl4ai_tool.py` / `firecrawl_tool.py`**：统一走 SSRF 防护（复用/下沉 `infrastructure/knowledge/ssrf.py`，拒绝内网/环回/云元数据地址）
* **[MODIFY] `app/application/agent/tools/code_interpreter.py`**：默认关闭或白名单命令模式，需 `agent_reach_config.json` 显式开启
* **[NEW] 内容清洗**：RAG 素材 / 采集正文注入 prompt 前做分隔符包裹 + 长度截断（prompt injection 缓解）

---

## 2. 详细执行步骤（TDD 流程）

> 已落地部分不再列为步骤：5 子 Agent 协作、TaskPlan、记忆、反思、机会、三层意图、HITL。
> 以下步骤仅覆盖 ◻️ 剩余工作。

### Phase 0：子图抽取 + Orchestrator 瘦身（架构重构，不改用户行为）
1. **Step 1 (TDD)**：写 `tests/test_agent_graphs.py`——collector / knowledge 子图作为独立图可编译、可被 Orchestrator 调用；对话、URL 导入、RAG 检索三条链路行为与重构前一致；**子图内 RAG/task_plan 完成后 SSE 事件仍可透传**（失败测试先行）。
2. **Step 2**：新建 `graphs/collector.py`、`graphs/knowledge.py`，把 `parse_url_node` / `normalize_and_persist_node` / `knowledge_decision_node` / `retrieve_knowledge_node` 移入对应子图。
3. **Step 3**：改造 `conversation.py` 为 Orchestrator，通过子图节点接入；`ChatAgentState` 字段收敛到核心集合。
4. **Step 3.5 (TDD，评审补充)**：写 `tests/test_hitl_choice_api.py`——`choice.requested` → `POST /api/chats/{id}/choices` → 续跑消费 `hitl_selection`。
5. **Step 3.6**：实现 HITL 提交端点 + `preprocess` 透传 `hitl_selection` 续跑。
6. **Step 4 (TDD)**：写 `tests/test_agent_timeout.py`——mock 子图运行 sleep 超预算，断言降级路径（重试 1 次 / 部分结果保留 / 直接降级）、`agent.error` 事件、`AIOperation` 记录（失败测试先行）。
7. **Step 5**：实现 `scheduling.py` 的 `invoke_subgraph()` + 超时预算配置 + `agent.error` 事件，接入 `assign_agent`。
8. **Step 5.5（评审补充）**：SSE 事件匹配子图感知化（spec §11.8）+ 工具安全（spec §12：SSRF 防护、`code_interpreter` 默认关闭、内容清洗）。
9. **Step 6**：删除全部死代码 `analysis.py` / `refinement.py` / `chat_conversation_run_service.py` / `workflow_service.py` / `app/workflow.py` / `generation_job_service.py` / 无用 adapters。
10. **Step 7**：`uv run pytest tests/test_agent_graphs.py tests/test_agent_timeout.py tests/test_hitl_choice_api.py tests/test_chat_branching.py -v` + 前端 `bun run typecheck`。

### Phase 1：Quality Reviewer（质检审稿，最高性价比）
11. **Step 8 (TDD)**：写 `tests/test_quality_review.py`——质检报告输出合法结构、建议采纳后调用 inline_refinement、报告写入 `AIOperation`、`result_version_id` 溯源正确。
12. **Step 9**：实现 `quality_service.py` + `graphs/reviewer.py`（复用 `reflection.py` 5 维评分，补 `QualityReport` schema 与一键采纳，依赖 `generate_structured`，见 outline plan Phase 0）。
13. **Step 10**：`prompts/review/quality_review.yml` 模板 + 前端质检面板。
14. **Step 11**：全链路验证（生成 → 质检 → 采纳润色），采纳版本溯源 join 就绪（spec §4.6 方案 A，供 StyleLearner 使用）。

### Phase 2：Topic Analyst（选题评估）
15. **Step 12 (TDD)**：写 `tests/test_topic_analyst.py`——`evaluate_topic` 输出 `worth_score` + `user_match` 结构化结果（含 L2 记忆兴趣领域注入，依赖记忆 plan P1 的检索通道）。
16. **Step 13**：实现 `graphs/analyst.py` + `prompts/analysis/topic_evaluation.yml`（复用 `opportunity_service` 规则打分，**Top-N 后置 LLM**：仅对规则分前 N 名做 LLM 评估，N 默认 10 可配）。
17. **Step 14**：`SourceItem` 增加评估字段（迁移）→ 前端热榜/采集列表按 worth_score 排序 + 评分徽章；热榜页加「评估」入口（保留一键建对话）。

### Phase 3：Content Writer（观点采集 → 大纲 → 分段生成，依赖 outline plan）
18. **Step 15**：实现 `graphs/writer.py`，统一承载 `generate_first` / `refine_selection` / `rewrite_full`（迁移现有三个 workflow），接入大纲生成（outline plan Phase 1）。
19. **Step 16**：Writer 支持可选调用 RAG Knowledge 素材库检索（记忆 plan Phase 3）+ 观点采集前置（viewpoint_notes）+ 可选配图（复用 `image_service`）。
20. **Step 16.5（评审补充）**：发布状态管理 + `PublishMetrics` 表迁移与 CRUD（Data Analyst 数据前置，spec §4.7）。

### Phase 4：Data Analyst（远期，依赖发布数据）
21. **Step 17**：实现 `graphs/analyst.py` 数据回流分析 + 版本 diff 风格学习输出（记忆 plan Phase 2 的 StyleLearner）。
22. **Step 18（评审补充）**：跨 spec 集成测试——大纲 → 写作 → 质检 → 采纳 → 风格学习 → 下一轮生成体现偏好的端到端用例。

---

## 3. 验证计划

### 自动化测试命令
```bash
uv run pytest tests/test_agent_graphs.py tests/test_agent_timeout.py tests/test_hitl_choice_api.py tests/test_quality_review.py tests/test_topic_analyst.py -v
cd frontend && bun run typecheck && bun run build
```

### 实际链路校验
1. 对话 → 输入 URL → 走 collector 子图 → SSE 返回结构化卡片（与重构前一致，**且子图内 RAG/task_plan 事件仍透传**）
2. 对话 → 触发 RAG → 走 knowledge 子图 → `retrieval_traces` 落库正常
3. 对话 → 采集约束冲突 → `choice.requested` → 提交选择 → 续跑完成
4. 编辑器 → 生成回答 → 质检 → 报告面板展示 → 采纳建议后内容被润色（`result_version_id` 溯源正确）
5. 热榜页 → 选题评估徽章与排序生效（仅 Top-N 有 LLM 理由）
6. mock 子图挂死 → 超时后 SSE 收到 `agent.error`、前端展示"已降级"、`AIOperation` 有记录
7. 全量回归：`uv run pytest tests/` 无失败

### 里程碑验收（对应 spec §7 / §11）

- [x] **已实现（feature/private-knowledge-rag）**：5 子 Agent 协作、TaskPlan、长期记忆、反思循环、机会感知、三层意图、HITL 节点、前端 7 面板
- [ ] P0：子图被 Orchestrator 调用；对话/URL 导入/RAG 回归一致；子图内 SSE 事件透传；`ChatAgentState` 收敛
- [ ] P0：子图运行级超时生效（`invoke_subgraph`）——mock 挂死降级不抛异常，`agent.error` 事件 + `AIOperation` 记录
- [ ] P0：HITL 提交入口——冲突后可提交选择续跑，历史消息链完整
- [ ] P0：全部死代码已删；工具 SSRF 防护 / `code_interpreter` 默认关闭生效
- [ ] P1：质检报告可用（合法结构 + 采纳润色 + `AIOperation` 存档 + 版本溯源）
- [ ] P2：选题评估可用（worth_score + Top-N LLM 理由 + 排序 + 徽章）
- [ ] P3：大纲 → 分段生成打通；Writer 可检索素材；发布状态 + `PublishMetrics` 就绪
- [ ] P4：数据回流分析 + 风格学习（经确认生效）
