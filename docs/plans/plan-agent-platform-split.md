# [实现计划] 专业 Agent 平台拆分

> **文档状态**：已制定 (Drafting) - 等待用户评审确认
> **关联 Spec**：[docs/specs/feature-agent-platform-split.md](../specs/feature-agent-platform-split.md)
> **跨 Spec 依赖**：结构化输出（`StructuredOutputClient`）供 reviewer/analyst 使用；
> 本计划重构后的 `conversation_graph` 是记忆系统节点的挂载点。

---

## 1. 拟修改与新增的文件列表

### 1.1 子图新建 (Sub-graphs)
* **[NEW] `app/application/agent/graphs/collector.py`**
  * `CollectorState` + `build_collector_graph()`：`parse_url` / `normalize_and_persist` 移入，输出 `ToolResult`
* **[NEW] `app/application/agent/graphs/knowledge.py`**
  * `RetrievalState` + `build_knowledge_graph()`：`knowledge_decision` + `retrieve_knowledge` 移入，输出 `RetrievalResult`
* **[NEW] `app/application/agent/graphs/reviewer.py`**
  * `ReviewerState` + `build_reviewer_graph()`：质检报告节点（调用 `StructuredOutputClient`）
* **[NEW] `app/application/agent/graphs/analyst.py`**
  * `AnalystState` + `build_analyst_graph()`：`evaluate_topic` 选题评估节点
* **[NEW] `app/application/agent/graphs/writer.py`**
  * `WriterState` + `build_writer_graph()`：观点采集 → 大纲 → 分段生成（依赖 outline spec）
  * **统一三类生成**：`generate_first` / `refine_selection` / `rewrite_full`
    （承接现有 answer_generation / inline_refinement / full_rewrite，保留流式事件契约）
  * 可选配图步骤（复用 `image_service`）

### 1.2 Orchestrator 改造
* **[MODIFY] `app/application/agent/graphs/conversation.py`**
  * 瘦身为 Orchestrator：保留 preprocess / route_intent / knowledge_decision / chat
  * 新增 `assign_agent` 条件路由 → 调用 collector / knowledge / reviewer / analyst / writer 子图
* **[MODIFY] `app/application/agent/state.py`**
  * `ChatAgentState` 收敛为输入 + 消息 + 调度结果
  * 各子图新增独立 State（`CollectorState` / `RetrievalState` / `ReviewerState` 等）
* **[MODIFY] `app/application/agent/nodes/route_intent.py`**
  * 意图集合扩展：`chat` / `parse_url` / `create_answer` / `analyze` / `review`（保留规则优先）
* **[NEW] `app/application/agent/scheduling.py`**：`invoke_subgraph()`——`asyncio.wait_for` 子图运行级超时 + 按任务分类降级（spec §11.2/11.3）；降级写入 `AIOperation.model_parameters`（`reason=subagent_timeout`）
* **[MODIFY] `app/config/`**：子图超时预算（collector 60s / knowledge 15s / writer 90s / reviewer 30s / analyst 30s）
* **[MODIFY] `app/application/agent/nodes/chat_node.py`（或 SSE 封装）**：新增 `agent.error` 事件（spec §11.6）

### 1.3 领域服务与提示词
* **[NEW] `app/application/quality_service.py`**：质检报告组装、`AIOperation` 存档、建议一键采纳（走 Writer `refine_selection`，版本标记 `operation_type=quality_adopt`）
* **[NEW] `prompts/analysis/topic_evaluation.yml`**：选题评分 Few-shot 模板
* **[NEW] `prompts/review/quality_review.yml`**：质检 LLM-as-judge 模板

### 1.4 死代码清理
* **[DELETE] `app/application/agent/graphs/analysis.py`**（旧热榜分析单例）
* **[DELETE] `app/application/agent/graphs/refinement.py`**（旧精修图）
* **[DELETE] `app/application/agent/adapters.py`** 中无引用的 `HotlistServiceAdapter` / `LLMClientPort` 相关残留
* **[DELETE]** 被 Source Collector 取代的旧批量采集编排（`workflow_service` / `generation_job_service` 的采集路径，P0 后收敛）

### 1.5 前端
* **[MODIFY] `frontend/src/features/chat/chat-panel.tsx`**：Agent 执行链展示（复用 `agent.status` / `tool.started` 事件）
* **[MODIFY] `frontend/src/features/chat/editor-panel.tsx`**：质检按钮 + 报告面板
* **[NEW] `frontend/src/features/chat/quality-review-dialog.tsx`**：质检报告对话框（逐条建议采纳）
* **[MODIFY] `frontend/src/features/chat/prompt-templates-dialog.tsx`**：升级为通用提示词管理（+outline/review/analysis/memory/summary 分组）
* **[MODIFY] `frontend/src/features/hotlist/hotlist-page.tsx`**：选题评分徽章 + 理由 tooltip

### 1.6 测试
* **[NEW] `tests/test_agent_graphs.py`**：collector/knowledge 子图与 Orchestrator 编排
* **[NEW] `tests/test_agent_timeout.py`**：子图超时 → 降级路径（可重试重试 1 次 / 部分结果保留 / 不可重试直接降级）、`agent.error` 事件、取消传播（spec §11）
* **[NEW] `tests/test_quality_review.py`**：质检报告生成与采纳链路
* **[MODIFY] `tests/test_chat_branching.py`**：子图调用后对话/URL 导入/RAG 三条链路回归

---

## 2. 详细执行步骤（TDD 流程）

### Phase 0：子图抽取 + Orchestrator 瘦身（架构重构，不改用户行为）
1. **Step 1 (TDD)**：写 `tests/test_agent_graphs.py`——collector / knowledge 子图作为独立图可编译、可被 Orchestrator 调用；对话、URL 导入、RAG 检索三条链路行为与重构前一致（失败测试先行）。
2. **Step 2**：新建 `graphs/collector.py`、`graphs/knowledge.py`，把 `parse_url_node` / `normalize_and_persist_node` / `knowledge_decision_node` / `retrieve_knowledge_node` 移入对应子图。
3. **Step 3**：改造 `conversation.py` 为 Orchestrator，通过子图节点接入；`ChatAgentState` 字段收敛到核心集合。
4. **Step 4 (TDD)**：写 `tests/test_agent_timeout.py`——mock 子图运行 sleep 超预算，断言降级路径（重试 1 次 / 部分结果保留 / 直接降级）、`agent.error` 事件、`AIOperation` 记录（失败测试先行）。
5. **Step 5**：实现 `scheduling.py` 的 `invoke_subgraph()` + 超时预算配置 + `agent.error` 事件，接入 `assign_agent`。
6. **Step 6**：删除死代码 `analysis.py` / `refinement.py` / 无用 adapters。
7. **Step 7**：`uv run pytest tests/test_agent_graphs.py tests/test_agent_timeout.py tests/test_chat_branching.py -v` + 前端 `bun run typecheck`。

### Phase 1：Quality Reviewer（质检审稿，最高性价比）
8. **Step 8 (TDD)**：写 `tests/test_quality_review.py`——质检报告输出合法结构、建议采纳后调用 inline_refinement、报告写入 `AIOperation`。
9. **Step 9**：实现 `quality_service.py` + `graphs/reviewer.py`（依赖 StructuredOutputClient，见 outline spec Phase 0）。
10. **Step 10**：`prompts/review/quality_review.yml` 模板 + 前端质检面板。
11. **Step 11**：全链路验证（生成 → 质检 → 采纳润色）。

### Phase 2：Topic Analyst（选题评估）
12. **Step 12 (TDD)**：写 `tests/test_topic_analyst.py`——`evaluate_topic` 输出 `worth_score` + `user_match` 结构化结果（含 L2 记忆兴趣领域注入，依赖记忆 spec P1 的检索通道）。
13. **Step 13**：实现 `graphs/analyst.py` + `prompts/analysis/topic_evaluation.yml`。
14. **Step 14**：`SourceItem` 增加评估字段（迁移）→ 前端热榜/采集列表按 worth_score 排序 + 评分徽章；热榜页加「评估」入口（保留一键建对话）。

### Phase 3：Content Writer（观点采集 → 大纲 → 分段生成，依赖 outline spec）
15. **Step 15**：实现 `graphs/writer.py`，统一承载 `generate_first` / `refine_selection` / `rewrite_full`（迁移现有三个 workflow），接入大纲生成（outline spec Phase 1）。
16. **Step 16**：Writer 支持可选调用 RAG Knowledge 素材库检索（记忆 spec Phase 3）+ 观点采集前置（viewpoint_notes）+ 可选配图（复用 `image_service`）。

### Phase 4：Data Analyst（远期，依赖发布数据）
17. **Step 17**：实现 `graphs/analyst.py` 数据回流分析 + 版本 diff 风格学习输出（记忆 spec Phase 2 的 StyleLearner）。

---

## 3. 验证计划

### 自动化测试命令
```bash
uv run pytest tests/test_agent_graphs.py tests/test_agent_timeout.py tests/test_chat_branching.py tests/test_quality_review.py tests/test_topic_analyst.py -v
cd frontend && bun run typecheck && bun run build
```

### 实际链路校验
1. 对话 → 输入 URL → 走 collector 子图 → SSE 返回结构化卡片（与重构前一致）
2. 对话 → 触发 RAG → 走 knowledge 子图 → `retrieval_traces` 落库正常
3. 编辑器 → 生成回答 → 质检 → 报告面板展示 → 采纳建议后内容被润色
4. 热榜页 → 选题评估徽章与排序生效
5. mock 子图挂死 → 超时后 SSE 收到 `agent.error`、前端展示"已降级"、`AIOperation` 有记录
6. 全量回归：`uv run pytest tests/` 无失败

### 里程碑验收（对应 spec §7 / §11）
- [ ] P0：子图被 Orchestrator 调用；对话/URL 导入/RAG 回归一致；死图已删；`ChatAgentState` 收敛
- [ ] P0：子图运行级超时生效（`invoke_subgraph`）——mock 挂死降级不抛异常，`agent.error` 事件 + `AIOperation` 记录
- [ ] P1：质检报告可用（合法结构 + 采纳润色 + `AIOperation` 存档）
- [ ] P2：选题评估可用（worth_score + 排序 + 徽章）
- [ ] P3：大纲 → 分段生成打通；Writer 可检索素材
- [ ] P4：数据回流分析 + 风格学习（经确认生效）
