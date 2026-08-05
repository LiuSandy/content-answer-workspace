# 功能规范：专业 Agent 平台拆分

**版本：** 1.0
**日期：** 2026-08-05
**状态：** 待评审
**作者：** 架构设计

---

## 1. 背景与目标

### 1.1 现状评估

当前项目是「单 Agent + 脚本工作流」形态：仅有一个活跃的对话 Agent
（`graphs/conversation.py`），其余 Agent 图（`analysis_graph`、
`refinement_graph`）已被工作流层架空成死代码。核心业务闭环
（`docs/specs/content-creation-pipeline.md` 定义的
选题 → 观点 → 大纲 → 生成 → 质检 → 编辑 → 发布 → 回流）中，只有
"生成/润色/重写"三环有人实现，其余环节全部缺失。

### 1.2 现有能力盘点

| 已有资产 | 实现位置 | 状态 |
| :--- | :--- | :--- |
| 对话 Agent（ReAct + 意图路由） | `graphs/conversation.py` | ✅ 活跃 |
| 16+ 平台/通用工具 | `tools/` | ✅ 活跃（配置开关） |
| RAG 混合检索（BM25 + 向量 + 重排 + Trace） | `application/knowledge/` | ✅ 活跃 |
| URL 解析 + 采集入库节点 | `nodes/tool_nodes.py` + `infrastructure/sources/` | ✅ 活跃（嵌在对话图中） |
| 回答生成/润色/重写工作流 | `app/workflows/` | ✅ 活跃（脚本式） |
| Prompt Registry（YAML + 平台分层 + model profiles） | `app/prompts/` | ✅ 活跃 |
| 热榜分析 Agent | `graphs/analysis.py` | ❌ 死代码 |
| 回答精修 Agent | `graphs/refinement.py` | ❌ 死代码 |
| 版本系统（AI 版 vs 手动版 diff + 乐观锁） | `persistence/models/documents.py` | ✅ 活跃但数据未利用 |

### 1.3 目标

把项目从「LLM 应用内嵌 Agent 子系统」演进为**专业多 Agent 创作平台**：

1. **职责单一**：每个领域一个专职 Agent，独立 State / Prompt / 工具集 / 生命周期
2. **统一编排**：一个 Orchestrator 负责意图理解与跨 Agent 调度
3. **可组合**：领域 Agent 既能被 Orchestrator 编排，也能被前端按功能独立触发
4. **共享底座**：LLM / Prompt / RAG / Source 四类基础设施下沉为公共层，杜绝重复实现

---

## 2. 拆分原则

1. **按业务领域拆，不按工具数量拆**：工具只是 Agent 的手脚，领域才是边界。
2. **每个 Agent 有独立 State 类型与图文件**：避免 `ChatAgentState`
   继续膨胀（当前已混入检索/采集/工具结果 15 个字段）。
3. **不拆成 Agent 的**：纯 CRUD（发布管理、主题设置）保持普通 service，
   避免过度拆分。
4. **遗留图按意图复活**：`analysis_graph`（选题分析）、`refinement_graph`
   （精修）的意图正确，纳入新拆分体系后删除旧实现。

---

## 3. 目标架构

```text
用户输入（对话 / 热榜 / 编辑器操作）
        │
        ▼
Orchestrator Agent ──── 编排主管（保留现有 conversation_graph 的
        │               preprocess / route_intent / knowledge_decision / chat）
        │
        ├──→ Source Collector Agent   采集 / URL 解析 / 平台适配 / 去重入库
        ├──→ RAG Knowledge Agent      混合检索 / 证据提取 / 素材库检索
        ├──→ Topic Analyst Agent      热榜与采集结果批量评估 / 选题推荐
        ├──→ Content Writer Agent     大纲 → 观点采集 → 分段生成
        ├──→ Quality Reviewer Agent   质检 / 合规 / AI 味检测 / 评分
        └──→ Data Analyst Agent       发布数据回流 / 风格学习（远期）
```

### 3.1 Agent 清单与代码映射

| # | Agent | 职责边界 | 代码来源 | 优先级 |
| :--- | :--- | :--- | :--- | :--- |
| 1 | **Orchestrator** | 多轮对话、意图路由、任务编排、通用工具调用 | `graphs/conversation.py` 瘦身 | P0 |
| 2 | **Source Collector** | URL 解析、关键词采集、去重入库 | `tool_nodes.py` + `sources/registry` 升级 | P0 |
| 3 | **RAG Knowledge** | 混合检索、重排、Trace、证据注入 | `retrieve_knowledge_node` + `KnowledgeRetrievalService` 升级 | P0 |
| 4 | **Topic Analyst** | 选题 worth_score、竞争分析 | **复活** `graphs/analysis.py` 意图 | P2 |
| 5 | **Content Writer** | 大纲 → 观点 → 分段生成 | `workflows/answer_generation` + 结构化输出与大纲 spec 升级 | P1 |
| 6 | **Quality Reviewer** | AI 味、合规、LLM-as-judge 评分 | **新建**（spec 4.3） | P1 |
| 7 | **Data Analyst** | 版本 diff 风格学习、发布归因 | **新建**（spec 4.5/4.6） | P3 |

---

## 4. 各 Agent 详细设计

### 4.1 Orchestrator Agent（编排主管）

**职责：** 理解用户目标，决定直接对话还是分派子 Agent；执行通用工具。

**代码改造：**
- 保留 `conversation_graph` 的 `preprocess` / `route_intent` /
  `knowledge_decision` / `chat`（ReAct 环路）节点
- 将 `parse_url` / `normalize_and_persist` 迁移为对 Source Collector 子图的调用
- 将 `retrieve_knowledge` 迁移为对 RAG Knowledge 子图的调用
- 新增 `assign_agent` 条件路由：当意图命中创作/分析类任务时，交给对应子 Agent
- **创作类意图统一调度 Writer**：首次生成 / 选区润色 / 全文重写 / 大纲
  四类操作全部由 Content Writer Agent 承载（见 4.5），Orchestrator 不保留
  第二套生成实现
- **编辑器直连**：编辑器按钮触发的创作操作不经对话图，由前端直接调用
  Writer 暴露的端点（同一 Agent 能力、不同入口），避免"对话内生成"与
  "编辑器生成"两套实现

**State：** `ChatAgentState` 精简为输入 + 消息 + 调度结果，业务载荷放子图 State。

### 4.2 Source Collector Agent

**职责：** 多平台 URL 解析与关键词采集、去重入库、结构化输出。

**代码改造：**
- 新建 `graphs/collector.py`（`CollectorState`），将
  `parse_url_node` + `normalize_and_persist_node` 移入
- 复用 `infrastructure/sources/registry.py`（zhihu / xiaohongshu / universal 适配器）
- 输出契约：`ToolResult` / `SourceItemDTO`（已存在，`domain/dto.py`）
- **取代遗留批量采集**：`workflow_service` / `generation_job_service` 中的
  采集与生成编排由本子图承接（见 §10 衔接矩阵），P0 后不再走旧脚本流程

**State（`CollectorState`）：**
```python
class CollectorState(TypedDict):
    chat_id: str
    extracted_urls: list[str]
    request: CollectionRequest | None   # 关键词采集参数
    tool_result: ToolResult | None      # 输出
```

### 4.3 RAG Knowledge Agent

**职责：** 判断是否检索、执行混合检索、证据注入、Trace 落库。

**代码改造：**
- 新建 `graphs/knowledge.py`（`RetrievalState`），将
  `knowledge_decision` + `retrieve_knowledge` 移入
- 复用 `KnowledgeRetrievalService`（BM25 `|||` 算子 + pgvector + RRF + 重排）
- 对外暴露两种入口：Orchestrator 调用（normal/strict 模式）、
  写作时的素材库检索（`source_type=material`）

**State（`RetrievalState`）：**
```python
class RetrievalState(TypedDict):
    query: str
    workspace_id: str
    owner_id: str
    mode: str                        # "off" | "normal" | "strict"
    rag_decision: bool
    decision_reason: str | None
    retrieval_result: Any | None     # RetrievalResult
    trace_id: str | None
    fallback_reason: str | None
```

### 4.4 Topic Analyst Agent

**职责：** 对热榜/采集结果批量评估，输出「值得答指数」+ 理由，按分值排序。

**代码改造：**
- **复活** `graphs/analysis.py`，删除 `_analysis_graph` 单例，改为
  `build_analysis_graph()` 每次请求构建
- 新增节点 `evaluate_topic`：输入采集元数据（标题、浏览量、回答数、热度），
  调用 LLM 输出结构化 JSON
- **输入增加记忆匹配度**：并入 L2 记忆中的用户兴趣领域（`user_memories` 检索），
  输出 `user_match` 字段，衔接 context-memory spec（对齐
  `content-creation-pipeline` §2.1 的"匹配度"维度）
- Prompt：新建 `prompts/analysis/topic_evaluation.yml`（spec 4.1）
- 数据：`SourceItem` 增加评估字段（或独立 `TopicEvaluation` 表）
- **入口覆盖热榜**：热榜页现有「一键建对话」保留，另加"评估"入口；
  热榜与采集结果列表均按 `worth_score` 排序展示徽章（见 §6）

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

### 4.5 Content Writer Agent

**职责：** 创作全链路的生成方——观点采集（采访问题）→ 大纲 → 分段生成，
**统一承载三类生成操作**（首次生成 / 选区润色 / 全文重写），可选触发配图。

**代码改造：**
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

### 4.6 Quality Reviewer Agent

**职责：** 质检审稿：AI 味检测、平台合规、质量评分、修改建议。

**代码改造：**
- **新建** `graphs/reviewer.py` + `application/quality_service.py`
- Prompt：新建 `prompts/review/quality_review.yml`（spec 4.3）
- 报告不新增表，作为 `AIOperation` 记录存档
- 建议一键采纳：复用 Writer 的 `refine_selection`（原
  `workflows/inline_refinement.py`），生成版本操作类型记为
  `operation_type=quality_adopt`，**归为 AI 生成版**——StyleLearner 只学习
  "AI 生成版 → 用户手动编辑版"的 diff，跳过 AI→AI 版本对（见
  context-memory spec §4.5），避免质检采纳污染风格学习数据

**输出协议：**
```json
{
  "ai_flavor_score": 0.65,
  "hook_score": 0.8,
  "compliance_issues": ["广告法禁用词：顶级"],
  "suggestions": ["开头第 2 句改为反问句式"]
}
```

### 4.7 Data Analyst Agent

**职责：** 发布数据回流分析、版本 diff 风格学习（spec 4.5 / 4.6）。

**代码改造：**
- **新建**（依赖 P3 发布状态数据积累）
- 数据源：`AnswerVersion` 中 AI 生成版与手动编辑版的 diff、
  `PublishMetrics` 表
- 风格学习结果必须经用户确认后才合并进 `style_rules`，不静默改写

---

## 5. 共享基础设施下沉

| 公共层 | 现有实现 | 要求 |
| :--- | :--- | :--- |
| LLM Provider | `infrastructure/llm/registry.py` | 所有 Agent 统一走 Registry，按 model profile 选择规格 |
| Prompt | `app/prompts/registry.py` | 每个 Agent 的提示词独立 YAML，平台分层复用；**前端模板编辑可覆盖新增五类提示词**（见 §6） |
| RAG 检索 | `application/knowledge/retrieval_service.py` | Orchestrator / Writer 均调用同一服务 |
| Source 采集 | `infrastructure/sources/registry.py` | Collector / 各平台工具复用同一适配器 |
| 消息持久化 | `ChatService` / `DocumentService` | Agent 输出统一经此落库，不直接碰 Session |

---

## 6. 前端 UI 需求

- 对话流中展示 Agent 执行链：`正在分析选题 → 正在检索素材 → 正在写作 → 正在质检`
  （复用现有 `agent.status` / `tool.started` SSE 事件命名）
- 编辑器侧边新增「质检」按钮 → 报告面板，逐条建议可一键采纳
- 热榜/采集结果列表按 `worth_score` 排序，展示评分徽章 + 理由 tooltip
- 设置页「我的记忆 / 风格学习」入口（Data Analyst 阶段）
- **提示词模板编辑扩展**：现有 `prompt-templates-dialog` 升级为通用提示词管理，
  在「通用原则 + 平台包」之外，新增可编辑分组：
  `outline`（大纲）、`review`（质检）、`analysis`（选题评估）、
  `memory`（记忆提取/注入）、`summary`（滚动摘要）——对齐 Prompt Registry
  分层（§5），新增场景提示词不必改代码即可调优

---

## 7. 实现优先级与路线图

| Phase | 内容 | 说明 |
| :--- | :--- | :--- |
| **P0 重构** | 1 + 2 + 3 落地 | 抽子图，Orchestrator 编排调通，删除 2 个死图 |
| **P1** | 6 Quality Reviewer | 一个 prompt + 一个面板，最高性价比 |
| **P2** | 4 Topic Analyst | 复活 analysis 意图，接热榜与采集数据 |
| **P3** | 5 Writer 接 RAG 素材库 + 发布状态 | spec 4.2/4.4 |
| **P4** | 7 Data Analyst | 依赖 P3 积累数据，闭环收口 |

### P0 验收标准

- [ ] `parse_url` / `retrieve_knowledge` 作为独立子图被 Orchestrator 调用
- [ ] 对话、URL 导入、RAG 检索三条路径行为与重构前一致（回归测试通过）
- [ ] 删除 `graphs/analysis.py`、`graphs/refinement.py` 旧实现
- [ ] `ChatAgentState` 字段收敛，业务载荷移入各子图 State

---

## 8. 依赖与风险

| 风险 | 影响 | 应对方案 |
| :--- | :--- | :--- |
| 重构引入回归 | 对话/采集/检索主链路断裂 | P0 前补齐相关回归测试，逐图灰度切换 |
| 子图编排调试困难 | Bug 定位复杂 | 复用 LangGraph checkpoint + SSE 事件埋点，子图独立可测 |
| 子 Agent 挂死/长时间无响应 | 对话/创作链路卡住，SSE 空等 | 子图运行级超时 + 分任务降级 + 可取消（§11） |
| LLM 评估结果不稳定 | 选题/质检分数失真 | JSON Schema 约束 + Few-shot 示例 + 阈值提示重试 |
| RAG 接入主流程开销 | 每次生成多一次检索 | 只在 Writer 明确请求素材时触发，聊天链路保持现状 |
| 风格学习误改风格 | 用户风格被破坏 | 必须人工确认才合并，提供一键回滚 |

---

## 9. 技术架构影响评估

| 组件 | 当前状态 | 变化后 |
| :--- | :--- | :--- |
| `graphs/conversation.py` | 单图全职责 | 瘦身为 Orchestrator，新增子图调度 |
| `graphs/` | 3 个文件（2 个死代码） | 新增 `collector.py` / `knowledge.py` / `writer.py` / `reviewer.py`，删除旧 analysis/refinement |
| `nodes/` | 12 个节点 | 按子图重新分组 |
| `state.py` | ChatAgentState 15 字段 | 收敛为 Orchestrator 核心字段，各子图独立 State |
| `prompts/` | writing/chat/refinement 等 | 新增 `analysis/topic_evaluation.yml`、`review/quality_review.yml` |
| `application/` | workflow_service + workflows | 新增 `quality_service.py`，writer 图替代 answer_generation workflow |
| 前端 | chat/knowledge/hotlist/settings | 新增质检面板、评分徽章、Agent 执行链展示 |

---

## 10. 与现有功能的衔接矩阵

> 本节回答「已有业务功能在新架构下怎么处置」。标注 **保留** = 不动或仅加薄层；
> **迁移** = 逻辑移入对应 Agent/服务；**废弃** = 由新实现取代并删除。
> 时机列对齐 §7 优先级路线。

| 现有功能 | 新架构承接 | 动作 | 时机 |
| :--- | :--- | :--- | :--- |
| 对话 / 意图路由 / 通用工具 | Orchestrator（§4.1） | 保留 + 瘦身 | P0 |
| URL 解析 / 采集入库节点 | Source Collector（§4.2） | 迁移 | P0 |
| RAG 检索 / 证据注入 / Trace | RAG Knowledge（§4.3） | 迁移 | P0 |
| 生成 / 润色 / 重写（编辑器触发） | Content Writer 三类 operation（§4.5） | 迁移 + 统一 | P1/P3 |
| 提示词模板编辑对话框 | 通用提示词管理（§6） | 扩展 | P1 |
| 版本系统 / 乐观锁 / `AIOperation` | 保留；新增 `outline`/`quality_adopt` 操作类型 | 保留 + 扩展 | P1/P2 |
| 知识库管理 CRUD（上传/编辑/确认/重解析/删除） | 普通 service（不 Agent 化） | 保留 | 不变 |
| RAG 检索测试面板 / Trace 面板 | 保留；记忆检索复用同 Trace 机制 | 保留 | 不变 |
| 热榜拉取 + 一键建对话 | 保留；接入 Topic Analyst 评分（§4.4） | 保留 + 扩展 | P2 |
| 设置页 | 保留；新增记忆管理、创作背景开关 | 保留 + 扩展 | 记忆 spec |
| 旧批量采集工作流（`workflow_service` / `generation_job_service`） | 被 Source Collector 取代 | **废弃** | P0 后 |
| 配图（`image_service`） | 迁入 Writer 可选步骤（§4.5） | 迁移 | P3 |
| 主题扩展（`topic_expansion_service`） | 纯 CRUD，保持 service | 保留 | 不变 |
| 死代码 `analysis_graph` / `refinement_graph` | 意图复活为 Topic Analyst / Quality Reviewer | 删除旧实现 | P0 |

**收敛原则**：同一业务能力只有一条实现路径——编辑器按钮与对话意图均落到
Writer / Reviewer / Analyst 子图；CRUD 一律不 Agent 化。废弃动作统一在
P0 重构时删净，避免新旧双轨长期并存。

---

## 11. 子 Agent 调度：超时与降级策略

> 本节定义 Orchestrator 调用子图时的运行级超时、失败降级与取消恢复。
> 底层单次调用（HTTP / 子进程工具 / LLM / RAG 组件）的超时已存在，
> 本节解决的是「整个子图运行挂死」这一层。

### 11.1 超时分级总览

| 层级 | 机制 | 现状 |
| :--- | :--- | :--- |
| 网络 / HTTP | httpx `timeout`（fetch 15s / client 30s） | ✅ 已有 |
| 子进程工具 | `subprocess.run(timeout=30~60)` | ✅ 已有 |
| 浏览器采集 | Playwright `goto` 30s | ✅ 已有 |
| RAG 组件 | reranker 8s / embedding 30s | ✅ 已有 |
| LLM 调用 | `StructuredOutputClient` 重试 + 降级 | ✅ outline spec |
| **子图运行级** | `asyncio.wait_for` 包裹子图调用 | ❌ **本节新增** |

### 11.2 子图运行级超时

`assign_agent` 调度统一经 `invoke_subgraph()` 包装：

```python
async def invoke_subgraph(name: str, run: Coroutine, budget: float) -> SubgraphResult:
    try:
        return await asyncio.wait_for(run, timeout=budget)
    except asyncio.TimeoutError:
        return SubgraphResult(status="timeout", agent=name)
```

按 Agent 分级的默认预算（可配置，入 `app/config/`）：

| Agent | 默认预算 | 说明 |
| :--- | :--- | :--- |
| RAG Knowledge | 15s | 单次检索，已有组件级超时兜底 |
| Topic Analyst | 30s | 批量评分，可部分返回 |
| Quality Reviewer | 30s | 单次审稿 |
| Source Collector | 60s | 含网络抓取/解析 |
| Content Writer | 90s | 分段生成最长 |

### 11.3 超时/失败后的降级策略

按任务性质分三类，`invoke_subgraph()` 内部选择：

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
  "agent": "collector",
  "reason": "timeout",
  "duration_ms": 60000,
  "fallback": "chat"
}
```

前端收到后按 §11.3 的分类展示对应提示；不影响对话与编辑流程。
