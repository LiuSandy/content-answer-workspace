# 功能规范：专业 Agent 平台拆分

**版本：** 2.1
**日期：** 2026-08-05
**状态：** 待评审
**作者：** 架构设计
**关联：** `docs/specs/feature-full-agent-upgrade.md`（权威产品 spec，五大能力）、
`docs/specs/feature-context-memory-system.md`、`docs/specs/feature-outlines-structured-generation.md`

> **2.0 修订说明**：1.0 版基于本地旧代码撰写，远程 `feature/private-knowledge-rag`
> 分支已实现 `feature-full-agent-upgrade.md` 的五大能力（自主规划 / 长期记忆 /
> 反思循环 / 主动感知 / 多 Agent 协作）。2.0 版重新分析代码，
> 将"已实现"部分校准为现状（✅），聚焦剩余技术缺口（◻️），不再重复规划已落地功能。
>
> **2.1 修订说明**：评审补充遗漏边界与方案优化——
> ① HITL 人工选择提交入口（节点已实现，回传 API 缺失，见 §4.1/§11.7）；
> ② 发布状态管理 + `PublishMetrics`（Data Analyst 数据源，见 §4.7/§7）；
> ③ 子图化后的 SSE 事件透传回归（`metadata.langgraph_node` 匹配风险，见 §11.8）；
> ④ `quality_adopt` 的版本溯源 join（StyleLearner 跳过 AI→AI 对，见 §4.6）；
> ⑤ Topic Analyst LLM 评估成本控制（Top-N 策略，见 §4.4）；
> ⑥ multi_agent 子图化降级为可选（先做运行级超时，见 §11）；
> ⑦ 死代码清理清单补全与时机提前（§10/§12）；⑧ 安全边界（§12）。

---

## 1. 背景与目标

### 1.1 现状评估（2026-08-05 代码校准）

项目已从"单 Agent + 脚本工作流"演进为**多 Agent 协作形态**，远程分支落地了：

| 能力 | 实现位置 | 状态 |
| :--- | :--- | :--- |
| 5 子 Agent 协作（orchestrator/research/writing/review/memory） | `application/agent/nodes/multi_agent.py` + `multi_agent_exec.py` | ✅ 已实现（顺序函数调用，非 LangGraph 子图） |
| 自主规划（TaskPlan DAG + 并行执行） | `application/task_planner_service.py` + `task_plan.py` | ✅ 已实现 |
| 长期记忆（user_memories 提取/检索/管理） | `application/memory_service.py` + `memory_retriever.py` | ✅ 已实现（检索为 LIKE 退化版） |
| 反思循环（5 维评分 + 迭代修正） | `application/workflows/reflection.py` + `reflect_refine.py` | ✅ 已实现 |
| 主动感知（机会扫描 + 评分 + 定时任务） | `application/opportunity_service.py` + `infrastructure/scheduler/` | ✅ 已实现 |
| 三层意图识别（规则→LLM→校验） | `nodes/route_intent.py` + `intent_rules.py` | ✅ 已实现 |
| Human-in-the-loop（约束冲突选择） | `nodes/hitl_decision.py` | ✅ 已实现 |
| Agent 递归上限 20 | `conversation.py` 路由 | ✅ 已实现 |

**核心业务闭环仍缺的环节**（`content-creation-pipeline.md` 定义的
选题 → 观点 → 大纲 → 生成 → 质检 → 编辑 → 发布 → 回流）中：

- ✅ 已覆盖：多 Agent 协作生成、反思质检评分、主动感知选题
- ◻️ 仍缺失：**观点采集**（采访问题）、**内容大纲**（ArticleOutline）、
  **质检一键采纳**（报告 schema + 采纳链路）、**创作衔接**（chat→背景摘要）、
  **子 Agent 运行级超时策略**、**Data Analyst**（发布回流 + 风格学习）
- ◻️ 评审补录（2.1）：
  - **HITL 人工提交入口**——`hitl_decision.py` 已能产生 `choice_request`，
    但**没有接收用户选择的回传 API**（`hitl_selection` 无消费方，见 §4.1/§11.7）
  - **发布状态管理 + `PublishMetrics` 表**——`content-creation-pipeline §4.4` 的
    发布出口未纳入规划，Data Analyst 因此无数据源（见 §4.7/§7）
  - **SSE 子图事件透传**——`chats.py` 依赖 `metadata.langgraph_node` 匹配节点，
    子图化后该元数据语义变化，RAG/task_plan/multi_agent 事件可能静默失效（见 §11.8）
  - **工具安全边界**——`code_interpreter` / `web_fetch` / `crawl4ai` / `firecrawl`
    的沙箱与 SSRF 防护未规划（见 §12）

### 1.2 现有能力盘点

| 已有资产 | 实现位置 | 状态 |
| :--- | :--- | :--- |
| 对话 Agent（三层意图路由 + ReAct） | `agent/graphs/conversation.py` + `route_intent.py` | ✅ 活跃 |
| 18 个平台/通用工具 | `agent/tools/` | ✅ 活跃 |
| RAG 混合检索（BM25 + 向量 + 重排 + Trace） | `application/knowledge/` | ✅ 活跃（已接入对话主链路） |
| URL 解析 + 采集入库节点 | `agent/nodes/tool_nodes.py` + `infrastructure/sources/` | ✅ 活跃（嵌在对话图中） |
| 回答生成/润色/重写工作流 | `app/workflows/` | ✅ 活跃（脚本式） |
| 5 子 Agent 协作 + TaskPlan DAG | `multi_agent.py` + `task_planner_service.py` | ✅ 活跃（非子图，顺序调用） |
| 长期记忆（user_memories） | `memory_service.py` + `memory_retriever.py` + `api/routes/memories.py` | ✅ 活跃 |
| 反思循环（QualityScore） | `workflows/reflection.py` + `reflect_refine.py` | ✅ 活跃 |
| 机会感知（定时扫描 + 评分） | `opportunity_service.py` + `infrastructure/scheduler/` | ✅ 活跃 |
| HITL（约束冲突人工选择） | `agent/nodes/hitl_decision.py` | ✅ 活跃 |
| 热榜分析 Agent | `graphs/analysis.py` | ❌ 死代码（被机会扫描取代） |
| 回答精修 Agent | `graphs/refinement.py` | ❌ 死代码（被反思循环取代） |
| 运行缓存 `ChatConversationRunService` | `chat_conversation_run_service.py` | ❌ 死代码（未挂载路由、前端无调用） |
| 旧批量采集编排 | `application/workflow_service.py` + `app/workflow.py` + `generation_job_service.py` | ❌ 死代码（前端已无 `generation-jobs`/`/api/workflow` 等调用，`server.py` 未挂载，可立即删） |
| 版本系统（AI 版 vs 手动版 diff + 乐观锁） | `persistence/models/documents.py` | ✅ 活跃但数据未利用 |

### 1.3 目标

在已实现的多 Agent 协作（`full-agent-upgrade.md` 功能五）基础上，向
**专业内容创作平台**补齐缺口：

1. **校准对齐**：文档描述与代码现状一致（5 子 Agent / TaskPlan / QualityScore /
   OpportunityFeed 术语统一），不再重复规划已落地能力
2. **补缺闭环**：观点采集 → 大纲 → 生成 → 质检采纳 → 创作衔接
   （`content-creation-pipeline.md` 的缺失环节）
3. **子图化演进**：把"顺序函数调用"的多 Agent 协作升级为 LangGraph 子图 +
   运行级超时/降级策略，获得可观测、可取消、可恢复
4. **共享底座**：LLM / Prompt / RAG / Source 四类基础设施下沉为公共层
5. **Data Analyst（远期）**：发布回流 + 风格学习，闭环收口

---

## 2. 拆分原则

1. **按业务领域拆，不按工具数量拆**：工具只是 Agent 的手脚，领域才是边界。
2. **每个 Agent 有独立 State**：已实现的 `MultiAgentState`（dataclass）+ 每子
   Agent 独立 `SubAgentState`（状态隔离、单失败不阻断）为事实基础，演进时保持隔离性。
3. **不拆成 Agent 的**：纯 CRUD（发布管理、主题设置）保持普通 service，
   避免过度拆分。
4. **死代码按意图对齐现状**：`analysis_graph`（选题）意图已由机会扫描
   （`opportunity_service`）承接，`refinement_graph`（精修）已由反思循环
   （`reflect_refine`）承接——删除旧实现即可，不重复复活。

---

## 3. 目标架构

```text
用户输入（对话 / 热榜 / 编辑器操作）
        │
        ▼
conversation_graph（Orchestrator，三层意图路由）
        │  preprocess → memory_retriever → route_intent
        ├─→ parse_url / normalize / build_response      ✅ Collector 路径
        ├─→ knowledge_decision → retrieve_knowledge     ✅ RAG 路径
        ├─→ task_plan（TaskPlan DAG）                   ✅ 已实现
        ├─→ multi_agent（5 子 Agent 协作）               ✅ 已实现
        │     orchestrator → research → writing → review → memory
        └─→ chat（ReAct + tools → hitl_decision）       ✅ 已实现
                        │
        ── 以下为本文档规划的增量（◻️） ──
        ├─→ Source Collector 子图化         采集 / URL 解析 / 平台适配 / 去重入库
        ├─→ Topic Analyst 接机会评分        选题评估（OpportunityFeed + 记忆匹配）
        ├─→ Content Writer 补观点采集/大纲  大纲 → 观点 → 分段生成 → 配图
        ├─→ Quality Reviewer 采纳链路       质检报告 schema + 一键采纳
        └─→ Data Analyst（远期）            发布数据回流 / 风格学习
```

### 3.1 Agent 清单与代码映射

| # | Agent | 职责边界 | 现状 | 优先级 |
| :--- | :--- | :--- | :--- | :--- |
| 1 | **Orchestrator**（编排主管） | 三层意图路由、多轮对话、任务编排、**HITL 选择回传** | ✅ `conversation.py` + `route_intent.py`；◻️ HITL 回传 API（§4.1） | 已实现 + P0 |
| 2 | **Research / Writing / Review / Memory** | 协作生成初稿、自评修正、记忆沉淀 | ✅ `multi_agent.py` | 已实现 |
| 3 | **Source Collector** | URL 解析、关键词采集、去重入库 | ◻️ 从 `tool_nodes.py` 子图化（当前嵌在对话图） | P0 |
| 4 | **RAG Knowledge** | 混合检索、重排、Trace、证据注入 | ✅ `retrieve_knowledge` + `KnowledgeRetrievalService` | 已实现 |
| 5 | **Topic Analyst** | 选题评估（复用机会评分 + 记忆匹配） | ◻️ `opportunity_service` 已打分，缺用户记忆匹配与热榜入口集成 | P2 |
| 6 | **Content Writer** | 观点采集 → 大纲 → 分段生成（统一三类生成） | ◻️ 现有 `workflows/` 脚本式，未并入子图 | P1/P3 |
| 7 | **Quality Reviewer** | 质检报告 + 一键采纳（`QualityReport` schema） | ◻️ 反思评分已实现（`reflection.py`），缺采纳链路 | P1 |
| 8 | **Data Analyst** | 发布回流分析、版本 diff 风格学习 | ◻️ 依赖发布状态数据积累 | P3/P4 |

---

## 4. 各 Agent 详细设计

### 4.1 Orchestrator Agent（编排主管）✅

**职责：** 理解用户目标，决定直接对话还是分派子 Agent；执行通用工具。

**现状（已实现，`conversation.py`）：**
- 三层意图路由（`route_intent.py`：规则 → LLM → 校验 + 低置信度降级）
- 意图集：`chat` / `parse_url` / `task_plan` / `multi_agent`（+ 规则层 `collect`）
- `memory_retriever` 节点挂载于 preprocess 之后
- ReAct 环路 + `hitl_decision`（工具冲突人工选择）+ 递归上限 20

**增量（◻️）：**
- **HITL 人工提交入口（P0，评审补录）**：`hitl_decision.py` 已能产出
  `choice_request` 并置 `hitl_pending` 终态，但全仓库**没有接收用户选择的 API**。
  补 `POST /api/chats/{chat_id}/choices`（body：`{messageId, selection}`），
  落库 `hitl_selection` 并带 `hitl_choice.context` 快照发起续跑（新 thread_id
  进入既有 thread，见 memory spec §3.4 分支规则）；前端在 `choice.requested`
  事件后渲染选项，提交后 `agent.status` 显示"按选择继续执行"
- **创作类意图统一调度 Writer**：首次生成 / 选区润色 / 全文重写 / 大纲
  四类操作全部由 Content Writer Agent 承载（见 4.5），Orchestrator 不保留
  第二套生成实现
- **编辑器直连**：编辑器按钮触发的创作操作不经对话图，由前端直接调用
  Writer 暴露的端点（同一 Agent 能力、不同入口），避免"对话内生成"与
  "编辑器生成"两套实现

### 4.2 Source Collector Agent ◻️

**职责：** 多平台 URL 解析与关键词采集、去重入库、结构化输出。

**现状：** `parse_url` / `normalize_and_persist` / `build_response` 仍嵌在
`conversation.py` 中（已实现，但未子图化）。

**增量（P0）：**
- 新建 `graphs/collector.py`（`CollectorState`），将
  `parse_url_node` + `normalize_and_persist_node` 移入
- 复用 `infrastructure/sources/registry.py`（zhihu / xiaohongshu / universal 适配器）
- 输出契约：`ToolResult` / `SourceItemDTO`（已存在，`domain/dto.py`）
- **取代遗留批量采集**：`workflow_service` / `generation_job_service` 中的
  采集与生成编排由本子图承接（见 §10 衔接矩阵）。**注意（2.1 评审）**：这三处
  服务前端已无调用、`server.py` 未挂载，当前即死代码，随 P0 直接删除，
  无需等待"P0 后"再收敛

**State（`CollectorState`）：**
```python
class CollectorState(TypedDict):
    chat_id: str
    extracted_urls: list[str]
    request: CollectionRequest | None   # 关键词采集参数
    tool_result: ToolResult | None      # 输出
```

### 4.3 RAG Knowledge Agent ✅

**职责：** 判断是否检索、执行混合检索、证据注入、Trace 落库。

**现状（已实现）：** `knowledge_decision` + `retrieve_knowledge` 节点已接入
`conversation.py`，复用 `KnowledgeRetrievalService`（BM25 `|||` + pgvector + RRF + 重排），
strict 模式无证据时走 `strict_refusal`；RAG 已接入对话主链路（`full-agent-upgrade` Phase 1.5）。

**增量（◻️）：** 写作时的素材库检索（`source_type=material`）——见
context-memory spec §5，素材检索带 scope 过滤，复用同一服务。

### 4.4 Topic Analyst Agent ◻️

**职责：** 对热榜/采集结果批量评估，输出「值得答指数」+ 理由，按分值排序。

**现状（已实现）：** `opportunity_service` 已按
`hot×0.4 + match×0.35 + competition×0.15 + recency×0.10` 打分（规则式，
`OpportunityFeedModel` 落库），APScheduler 每小时扫描 + 前端「今日机会」横幅。

**增量（P2）：**
- **补 LLM 评估维度**：`evaluate_topic` 用 LLM 输出结构化 JSON（`TopicEvaluation`，
  见 outline spec 场景 3），在规则分基础上补一句理由与建议
- **成本控制（2.1 评审）**：每小时扫描 + 全量 LLM 评估会显著推高 API 配额。
  采用 **Top-N 后置 LLM**：先跑规则分排序，仅对前 N 名（默认 10，可配）
  做 LLM `evaluate_topic`，未进 Top-N 的候选只保留规则分、无 LLM 理由；
  批量触发走异步队列（§11.5），失败不阻断横幅展示
- **输入增加记忆匹配度**：并入 L2 记忆中的用户兴趣领域（`user_memories` 检索），
  输出 `user_match` 字段，衔接 context-memory spec（对齐
  `content-creation-pipeline` §2.1 的"匹配度"维度）
- 数据：`OpportunityFeed` 增加评估字段（或独立 `TopicEvaluation` 表）
- **入口覆盖热榜**：热榜页现有「一键建对话」保留，另加"评估"入口；
  热榜与机会列表均按 `worth_score` 排序展示徽章（见 §6）

**输出协议：**
```json
{
  "worth_score": 72,
  "reason": "高浏览低回答，蓝海选题",
  "competition_level": "low",
  "user_match": "high",
  "suggestion": "优先作答"
}
```

### 4.5 Content Writer Agent ◻️

**职责：** 创作全链路的生成方——观点采集（采访问题）→ 大纲 → 分段生成，
**统一承载三类生成操作**（首次生成 / 选区润色 / 全文重写），可选触发配图。

**现状：** `app/workflows/answer_generation.py` / `inline_refinement.py` /
`full_rewrite.py` 仍是脚本式 workflow，编辑器按钮直接调用，未并入 Agent 子图；
`multi_agent.py` 的 `writing_agent_node` 已有 WritingAgent 雏形（依赖研究报告生成初稿）。

**增量（P1/P3）：**
- 将 `app/workflows/answer_generation.py` 升级为 `graphs/writer.py`
  （`WriterState`），保留流式 `document.delta` 事件契约（前端无需改动）
- **统一三类生成**：`inline_refinement` / `full_rewrite` 迁移为 Writer 子图的
  不同 operation（`generate_first` / `refine_selection` / `rewrite_full`），
  三个入口共用 Writer 的提示词装配与记忆注入，消除"编辑器操作绕过 Agent"的二套实现
- **观点采集（前置步骤）**：创作前可选向用户提 2~3 个采访问题，回答沉淀为
  `viewpoint_notes`，作为大纲与分段生成的观点注入（衔接
  `content-creation-pipeline` §4.2，对齐 outline spec §4.2）
- 生成前可调用 RAG Knowledge 检索素材库（观点注入时机）
- **配图（可选步骤）**：大纲确认后可选生成配图，复用 `image_service`
  （从旧采集工作流迁入，见 §10），迁移时与大纲/分段生成的流式事件共存
- Prompt：复用 `prompts/writing/` + 结构化输出与大纲 spec 大纲模板

### 4.6 Quality Reviewer Agent ◻️

**职责：** 质检审稿：AI 味检测、平台合规、质量评分、修改建议。

**现状（已实现）：** 反思循环 `reflection.py` 已产出 5 维评分
（relevance / information_density / readability / logic_coherence /
word_count_compliance）+ `QualityScoreModel` 落库；`reflect_refine.py`
低于 0.75 迭代修正（最多 3 轮）。

**增量（P1）：**
- 新建 `QualityReport` schema（AI 味 / 合规 / 建议，见 outline spec 场景 4），
  质检报告作为 `AIOperation` 记录存档
- 建议一键采纳：复用 Writer 的 `refine_selection`（原
  `workflows/inline_refinement.py`），生成版本操作类型记为
  `operation_type=quality_adopt`，**归为 AI 生成版**——StyleLearner 只学习
  "AI 生成版 → 用户手动编辑版"的 diff，跳过 AI→AI 版本对（见
  context-memory spec §4.5），避免质检采纳污染风格学习数据
- **版本溯源（2.1 评审，P1 落地时即设计好）**：`AnswerVersion.version_type`
  是固定 Enum（`documents.py`：initial_generation / inline_refinement /
  full_rewrite / manual_checkpoint / restored），**没有 `quality_adopt` 值**，
  而 `AIOperation.operation_type` 是 String 且为另一张表。StyleLearner
  按 `AnswerVersion` 相邻 diff 配对，要"跳过 AI→AI 对"必须 join：
  `ai_operations(operation_type=quality_adopt, result_version_id)` →
  命中则该版本归为 AI 生成版。落地方式二选一（建议 A，避免改 Enum 迁移）：
  - **A（推荐）**：`quality_adopt` 采纳生成的版本 `version_type=inline_refinement`，
    仅在 `AIOperation.operation_type=quality_adopt` 标记；StyleLearner 配对时
    通过 `AIOperation.result_version_id` 排除"上一版是 AI 版"的相邻对
  - B：`AnswerVersion.version_type` 增加枚举值 + Alembic 迁移
- **采纳版本写入时机**：采纳后新写 `AnswerVersion`（version_type 见上）并
  `AIOperation.result_version_id` 回填，保证 diff 溯源完整

**输出协议：**
```json
{
  "ai_flavor_score": 0.65,
  "hook_score": 0.8,
  "compliance_issues": ["广告法禁用词：顶级"],
  "suggestions": ["开头第 2 句改为反问句式"]
}
```

### 4.7 Data Analyst Agent ◻️（远期）

**职责：** 发布数据回流分析、版本 diff 风格学习（spec 4.5 / 4.6）。

**现状：** 无实现；`AnswerVersion` 版本 diff 数据已积累但未利用。

**前置依赖（2.1 评审补录）**：Data Analyst 依赖 **发布状态管理与 `PublishMetrics`
数据源**，但 `content-creation-pipeline §4.4` 的发布出口未纳入本 spec。为使
闭环收口，P3 必须包含（作为 Data Analyst 的数据前置）：
- `AnswerDocument` 增加 `publish_status`（draft / ready / published）、
  `published_at`、`published_url`（迁移）
- 新建 `PublishMetrics` 表（answer_document_id、抓取时间、赞同/评论/收藏数），
  手动录入或复用现有采集器抓自己的回答页；发布工作台/一键复制为普通 CRUD
  （不 Agent 化）

**增量（P3/P4）：**
- 数据源：`AnswerVersion` 中 AI 生成版与手动编辑版的 diff、`PublishMetrics` 表
- 风格学习结果必须经用户确认后才合并进 `style_rules`，不静默改写
- 复用 `QualityScoreModel` / `user_memories` 的 `implicit` 类型承接学习结果

---

## 5. 共享基础设施下沉

| 公共层 | 现有实现 | 要求 |
| :--- | :--- | :--- |
| LLM Provider | `infrastructure/llm/registry.py` + `agent/adapters.py`（`DeepSeekLLMAdapter`） | 所有 Agent 统一走 Registry / Adapter，按 model profile 选择规格 |
| Prompt | `app/prompts/registry.py`（已新增 `planning/`、`memory/`、`writing.reflection` 等） | 每个 Agent 的提示词独立 YAML，平台分层复用；**前端模板编辑可覆盖新增提示词分组**（见 §6） |
| RAG 检索 | `application/knowledge/retrieval_service.py` | Orchestrator / Writer 均调用同一服务 |
| Source 采集 | `infrastructure/sources/registry.py` | Collector / 各平台工具复用同一适配器 |
| 消息持久化 | `ChatService` / `DocumentService` | Agent 输出统一经此落库，不直接碰 Session |

---

## 6. 前端 UI 需求

**已实现**（`full-agent-upgrade` 配套）：`agent-workspace-panel.tsx`（子 Agent 状态树）、
`task-plan-card.tsx`（规划进度树）、`quality-score-panel.tsx`（质量评分雷达）、
`today-opportunities-banner.tsx`（今日机会横幅）、`memory-applied-badge.tsx`、
`memory-panel.tsx`（设置页记忆管理）、`agent-settings-panel.tsx`（机会感知开关/领域 Tag）。

**增量（◻️）：**
- 编辑器侧边新增「质检」按钮 → 报告面板，逐条建议可一键采纳
- 热榜/机会列表按 `worth_score` 排序，展示评分徽章 + 理由 tooltip
- 设置页「风格学习」入口（Data Analyst 阶段）
- **提示词模板编辑扩展**：现有 `prompt-templates-dialog` 升级为通用提示词管理，
  在「通用原则 + 平台包」之外，新增可编辑分组：
  `outline`（大纲）、`review`（质检）、`analysis`（选题评估）、
  `memory`（记忆提取/注入）、`summary`（滚动摘要）——对齐 Prompt Registry
  分层（§5），新增场景提示词不必改代码即可调优

---

## 7. 实现优先级与路线图

| Phase | 内容 | 说明 |
| :--- | :--- | :--- |
| **已实现** | 5 子 Agent 协作、TaskPlan、记忆、反思、机会、HITL 节点、三层意图 | `full-agent-upgrade.md` 功能一~五 |
| **P0 重构** | Collector 子图化 + 子图运行级超时 + **HITL 提交入口 + SSE 子图事件回归**（§11.7/11.8） | 删除全部死代码（§10）；`invoke_subgraph` 兜底 |
| **P1** | Quality Reviewer（`QualityReport` + 一键采纳 + 版本溯源 §4.6） | 复用已实现反思评分，补 schema 与采纳链路 |
| **P2** | Topic Analyst 增量（Top-N LLM 评估 + 记忆匹配 + 热榜入口） | 复用 `opportunity_service` 规则分 |
| **P3** | Content Writer（观点采集 → 大纲 → 分段生成 + 配图 + 素材检索）+ **发布状态管理 / `PublishMetrics` 前置**（§4.7） | 依赖 outline spec + context-memory spec |
| **P4** | Data Analyst（发布回流 + 风格学习） | 依赖 P3 积累数据，闭环收口 |

### P0 验收标准

- [ ] `parse_url` 等作为 Collector 子图被 Orchestrator 调用
- [ ] 对话、URL 导入、RAG 三条路径行为与重构前一致（回归测试通过），**且子图内
      `rag.sources` / `task_plan.created` / `multi_agent.status` SSE 事件仍可透传**（§11.8）
- [ ] `invoke_subgraph` 超时/降级生效（§11），mock 挂死不阻塞 SSE
- [ ] HITL `choice.requested` 后，前端可提交选择并续跑（§11.7）
- [ ] 删除全部死代码：`analysis.py`、`refinement.py`、`chat_conversation_run_service.py`、
      `workflow_service.py`、`app/workflow.py`、`generation_job_service.py`

---

## 8. 依赖与风险

| 风险 | 影响 | 应对方案 |
| :--- | :--- | :--- |
| 重构引入回归 | 对话/采集/检索主链路断裂 | P0 前补齐相关回归测试，逐图灰度切换 |
| 子图编排调试困难 | Bug 定位复杂 | 复用 LangGraph checkpoint + SSE 事件埋点，子图独立可测 |
| 子 Agent 挂死/长时间无响应 | 对话/创作链路卡住，SSE 空等 | 子图运行级超时 + 分任务降级 + 可取消（§11） |
| **子图化后 SSE 事件静默失效** | RAG/task_plan/multi_agent 卡片不展示 | `chats.py` 的 `metadata.langgraph_node` 匹配改为子图感知（§11.8），P0 加回归断言 |
| **同一 chat 并发写同一 checkpoint thread** | 状态错乱/丢失 | 每 chat 串行锁 + run 级隔离（context-memory spec §3.4） |
| **工具执行任意代码 / SSRF / prompt 注入** | 数据泄露、被利用 | 工具沙箱 + URL 域名白名单 + 内容清洗（§12） |
| LLM 评估结果不稳定 | 选题/质检分数失真 | JSON Schema 约束 + Few-shot 示例 + 阈值提示重试 |
| **选题全量 LLM 评估成本** | API 配额上升 | Top-N 后置 LLM（§4.4）+ 异步队列 |
| RAG 接入主流程开销 | 每次生成多一次检索 | 只在 Writer 明确请求素材时触发，聊天链路保持现状 |
| 风格学习误改风格 | 用户风格被破坏 | 必须人工确认才合并，提供一键回滚 |

---

## 9. 技术架构影响评估

| 组件 | 当前状态 | 变化后 |
| :--- | :--- | :--- |
| `conversation.py` | 已含 5 子 Agent / task_plan / hitl 等节点 | 增量子图化（Collector）+ 超时兜底（`scheduling.py`）+ HITL 续跑入口 |
| `multi_agent.py` | 顺序函数调用（非子图） | **可选**演进为 LangGraph 子图（§11.2 先加超时包装，子图化不强制） |
| `nodes/` | 12+ 节点 | Collector 相关节点移入子图 |
| `state.py` | ChatAgentState 含 multi_agent/task_plan/hitl/memory 字段 | 子图业务载荷移入各自 State；`hitl_selection` 有消费方 |
| `chats.py` | 基于 `metadata.langgraph_node` 匹配节点事件 | 改为子图感知匹配（§11.8），避免 RAG/task_plan 事件断链 |
| `prompts/` | 已有 planning/memory/writing.reflection | 新增 `analysis/topic_evaluation.yml`、`review/quality_review.yml`、`outline/` |
| `application/` | multi_agent / memory / opportunity / reflection 服务 | 新增 `quality_service.py`、`scheduling.py` |
| 前端 | agent-workspace/task-plan/quality-score/opportunity/memory 面板 | 新增质检采纳面板、评分徽章、提示词分组编辑、HITL 选择卡片 |

---

## 10. 与现有功能的衔接矩阵

> 本节回答「已有业务功能在新架构下怎么处置」。标注 **保留** = 不动或仅加薄层；
> **迁移** = 逻辑移入对应 Agent/服务；**废弃** = 由新实现取代并删除。
> 时机列对齐 §7 优先级路线。

| 现有功能 | 新架构承接 | 动作 | 时机 |
| :--- | :--- | :--- | :--- |
| 对话 / 三层意图路由 / 通用工具 | Orchestrator（`conversation.py`） | ✅ 已实现 | — |
| 5 子 Agent 协作（research/writing/review/memory） | `multi_agent.py` | ✅ 已实现；演进为子图 | P0 后 |
| TaskPlan DAG / 并行执行 | `task_planner_service.py` | ✅ 已实现 | — |
| 长期记忆（提取/检索/管理） | `memory_service.py` + memories API | ✅ 已实现（LIKE 退化） | — |
| 反思循环 / QualityScore | `reflection.py` + `reflect_refine.py` | ✅ 已实现 | — |
| 机会扫描 / 评分 / 定时任务 | `opportunity_service.py` + `scheduler/` | ✅ 已实现 | — |
| HITL 约束冲突选择 | `hitl_decision.py` | ✅ 节点已实现；◻️ 补提交 API 与续跑（§4.1/§11.7） | P0 |
| URL 解析 / 采集入库节点 | Source Collector 子图（§4.2） | 迁移 | P0 |
| RAG 检索 / 证据注入 / Trace | `retrieve_knowledge` 节点 | ✅ 已实现 | — |
| 生成 / 润色 / 重写（编辑器触发） | Content Writer 三类 operation（§4.5） | 迁移 + 统一 | P1/P3 |
| 质检评分 | 反思循环已评分；补 `QualityReport` + 采纳（§4.6） | 保留 + 扩展 | P1 |
| 提示词模板编辑对话框 | 通用提示词管理（§6） | 扩展 | P1 |
| 版本系统 / 乐观锁 / `AIOperation` | 保留；新增 `outline`/`quality_adopt` 操作类型 + 版本溯源 join（§4.6） | 保留 + 扩展 | P1/P2 |
| 知识库管理 CRUD（上传/编辑/确认/重解析/删除） | 普通 service（不 Agent 化） | 保留 | 不变 |
| RAG 检索测试面板 / Trace 面板 | 保留；记忆检索命中详情复用 Trace 机制 | 保留 | 不变 |
| 热榜拉取 + 一键建对话 / 今日机会横幅 | 保留；Topic Analyst 接入机会评分（§4.4） | 保留 + 扩展 | P2 |
| 设置页 | 保留；已含记忆/机会感知面板，新增创作背景开关 | 保留 + 扩展 | 记忆 spec |
| 发布状态管理 / 发布工作台 / 一键复制 | 普通 CRUD（§4.7 前置） | **新增（2.1 补录）** | P3 |
| 旧批量采集工作流（`workflow_service` / `generation_job_service` / `app/workflow.py`） | 被 Source Collector 取代 | **废弃（当前即死代码，P0 直接删）** | P0 |
| `ChatConversationRunService` | 运行缓存，前端无调用 | **废弃（P0 删）** | P0 |
| 配图（`image_service`） | 迁入 Writer 可选步骤（§4.5） | 迁移 | P3 |
| 主题扩展（`topic_expansion_service`） | 纯 CRUD，保持 service | 保留 | 不变 |
| 死代码 `analysis_graph` / `refinement_graph` | 意图已由机会扫描 / 反思循环承接 | 删除旧实现 | P0 |

**收敛原则**：同一业务能力只有一条实现路径——编辑器按钮与对话意图均落到
Writer / Reviewer / Analyst 子图；CRUD 一律不 Agent 化。废弃动作统一在
P0 重构时删净，避免新旧双轨长期并存。

---

## 11. 子 Agent 调度：超时与降级策略

> 本节定义 Orchestrator 调用子 Agent 时的运行级超时、失败降级与取消恢复。
> 底层单次调用（HTTP / 子进程工具 / LLM / RAG 组件）的超时已存在，
> 本节解决的是「整个子 Agent / 子图运行挂死」这一层。
>
> **现状缺口**：`multi_agent.py` 当前为顺序函数调用（`run_multi_agent_plan`），
> 无运行级超时——任一子 Agent 挂死将整体卡住。本节即为此补齐。
>
> **2.1 评审**：运行级超时用 `asyncio.wait_for` 包裹协程即可获得，**不依赖子图化**。
> multi_agent 演进为 LangGraph 子图列为可选重构（§9），P0 只做超时包装，
> 子图化留到 collector 子图验证稳定后再评估——避免为低收益做高风险改动。

### 11.1 超时分级总览

| 层级 | 机制 | 现状 |
| :--- | :--- | :--- |
| 网络 / HTTP | httpx `timeout`（fetch 15s / client 30s） | ✅ 已有 |
| 子进程工具 | `subprocess.run(timeout=30~60)` | ✅ 已有 |
| 浏览器采集 | Playwright `goto` 30s | ✅ 已有 |
| RAG 组件 | reranker 8s / embedding 30s | ✅ 已有 |
| LLM 调用 | 各节点 `llm.analyze` 无统一超时/重试 | ◻️ 需 `generate_structured` 统一（outline spec） |
| **子 Agent 运行级** | `asyncio.wait_for` 包裹子 Agent 调用 | ❌ **本节新增** |

### 11.2 子 Agent 运行级超时

子 Agent 调用统一经 `invoke_subagent()` 包装（`run_multi_agent_plan` 各节点
与未来的子图调度共用）：

```python
async def invoke_subagent(name: str, run: Coroutine, budget: float) -> SubAgentResult:
    try:
        return await asyncio.wait_for(run, timeout=budget)
    except asyncio.TimeoutError:
        return SubAgentResult(status="timeout", agent=name)
```

按子 Agent 分级的默认预算（可配置，入 `app/config/`；对齐 `multi_agent.py`
现有的 orchestrator / research / writing / review / memory）：

| Agent | 默认预算 | 说明 |
| :--- | :--- | :--- |
| orchestrator | 10s | 只做计划校验，不调用工具 |
| research | 60s | 多平台并行采集，可部分返回 |
| writing | 90s | LLM 生成初稿最长 |
| review | 60s | 含迭代修正（最多 3 轮） |
| memory | 15s | 记忆沉淀，失败不影响主链路 |
| Source Collector（子图化后） | 60s | 含网络抓取/解析 |

### 11.3 超时/失败后的降级策略

按任务性质分三类，`invoke_subagent()` 内部选择：

1. **幂等可重试**（采集、检索）：重试 1 次；仍失败 → 降级到主对话
   （chat 节点），SSE 发 `agent.error` 说明。
2. **部分结果已落库**（采集入库）：保留已写 DB 的内容，返回部分成功；
   不重跑已入库的 source_item（按去重键跳过）。
3. **不可重试**（生成、质检、选题）：直接降级并返回可读原因，
   不阻断编辑流程；Writer/Reviewer 超时时保留已生成的大纲/分段内容
   （已落库部分不丢弃）。

降级动作统一记录到 `AIOperation.model_parameters`（`reason=subagent_timeout`），
可观测性复用现有 `ai_operations` 表。

### 11.4 取消与恢复

- **用户取消**：SSE 请求断开或收到取消 → 向子图运行注入
  `asyncio.CancelledError`，子图清理后退出，不残留半开任务。
- **中断可续**：checkpoint `thread_id=chat_id`（context-memory spec §3.4）
  保证取消/断线后同一会话可恢复，已生成内容经 DB 保留。
- **前端配合**：复用现有 `interrupted` 状态 + 重发/继续恢复入口
  （`feature-chat-collect-result-rendering.md:171`），收到 `agent.error`
  时在消息流展示"XX Agent 超时，已降级"。

### 11.5 异步批量任务的例外

选题评估 / 质检 / 记忆提取 / 滚动摘要走 `BackgroundTasks`，
**不使用同步超时**：

- 队列执行 + 失败重试（指数退避），失败原因写入 `AIOperation`
- 对用户可见的结果（评分徽章 / 质检报告面板）超时后 UI 显示失败态，
  提供手动重试按钮；不可见任务静默重试

### 11.6 SSE 事件契约（扩展）

新增 `agent.error` 事件（沿用 `agent.status` / `tool.started` 命名）：

```json
{
  "agent": "research",
  "reason": "timeout",
  "duration_ms": 60000,
  "fallback": "chat"
}
```

前端收到后按 §11.3 的分类展示对应提示；不影响对话与编辑流程。

### 11.7 HITL 人工选择提交（P0，2.1 补录）

> 现状缺口：`hitl_decision.py` 生成 `choice_request` 并置 `hitl_pending` 终态，
> `chats.py:366` 发出 `choice.requested` SSE；但**没有任何 API 接收用户选择**，
> `hitl_selection`（state 字段）无消费方——用户被卡死在这一轮。

**设计：**
- 新端点 `POST /api/chats/{chat_id}/choices`
  body：`{"messageId": "<choice_request 消息 id>", "selection": "use_found"}`
- 处理：校验该消息确为 `choice_request` → 保存用户选择消息（`parent_message_id`
  指向该 choice_request）→ 以新 user message 为根发起一次续跑，输入带上
  `hitl_selection` + `hitl_choice.context`（走既有 checkpoint thread，
  分支规则见 context-memory spec §3.4）
- `preprocess.py` 已有 `hitl_selection` 初始化；续跑时保留并透传给后续工具调用
- SSE：续跑正常走 `agent.status` / `tool.started` 事件，前端在选项卡片显示
  "已选择，正在继续"
- 前端：`choice.requested` 事件 → 渲染选项卡片（复用 `task-plan-card` 的卡片模式），
  提交后进入流式等待

**验收**：模拟采集约束冲突 → 收到 `choice.requested` → 提交 `use_found` →
续跑使用已采内容完成本轮，历史消息链完整。

### 11.8 子图化后的 SSE 事件透传（P0，2.1 补录）

> 现状：`chats.py` 通过 `kind == "on_chain_end"` 且
> `metadata.langgraph_node == "retrieve_knowledge"` / `"task_plan"` / `"multi_agent"`
> 匹配节点完成时的事件。节点移入子图后，子图内节点的 `langgraph_node` 元数据
> 属于子图执行帧（值为子图内部节点名），该匹配会**静默失效**——RAG 来源卡片、
> 任务规划卡、多 Agent 状态树不再展示。

**处理方案（P0 必须做）：**
- 事件匹配改为子图感知：优先用事件自带的子图/节点命名空间（`parent` 元数据链）
  或给关键子图节点增加稳定的事件名（`name="retrieve_knowledge"` 显式标注），
  不再依赖 `langgraph_node` 字符串
- 或更稳：在 `retrieve_knowledge_node` / `task_plan_node` / `multi_agent_node`
  内部产出结构化状态后，由 Orchestrator 层统一发事件（封装 `emit_node_done`），
  前端契约不变
- 回归：P0 验收必须包含"子图内完成 RAG/任务规划/多 Agent 后 SSE 事件仍可收到"

---

## 12. 安全边界（2.1 补录）

> 现状缺口：`ALL_TOOLS` 按 `.data/agent_reach_config.json` 动态加载，含
> `code_interpreter`（`PythonREPLTool` 任意代码执行）、`web_fetch` /
> `crawl4ai_fetch` / `firecrawl_scrape`（任意 URL 抓取）、平台搜索工具；
> SSRF 防护仅存在于 `infrastructure/knowledge/ssrf.py`（只覆盖知识库上传），
> 未覆盖 Agent 工具。子图化后工具入口增多，攻击面同步扩大。

**P0 加入：**
- **URL 域名白名单**：`web_fetch` / `crawl4ai` / `firecrawl` 统一走 SSRF 防护
  （禁止内网/环回/云元数据地址，复用 `ssrf.py` 或下沉为公共模块）
- **代码执行沙箱**：`code_interpreter` 默认关闭或降级为"仅白名单命令"模式，
  需在 `agent_reach_config.json` 显式开启；开启时以受限用户/超时运行
- **内容清洗**：RAG 素材与采集正文在注入 prompt 前剥离嵌入指令
  （prompt injection 缓解，最小实现：长度截断 + 分隔符包裹 + 可选标记）
- **平台工具鉴权**：各平台工具保持配置开关（已具备），未启用平台不注册
- 验收：mock 内网地址抓取被拒、PythonREPL 默认关闭、SSE 链路不受影响
