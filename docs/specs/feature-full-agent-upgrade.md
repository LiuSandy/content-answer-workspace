# 功能规范：升级为完整 Agent 项目

**版本：** 1.0
**日期：** 2026-07-25
**状态：** 待评审
**作者：** 产品设计

---

## 1. 背景与目标

### 1.1 现状评估

当前项目是一个「轻 Agent」应用，具备基础的 LangGraph 多轮对话和 ReAct 工具调用能力，
但核心业务流程（采集 → 生成 → 编辑）仍以人工逐步触发为主，Agent 仅扮演"对话机器人"
角色，尚未具备自主规划、长期记忆与主动感知等完整 Agent 能力。

### 1.2 现有 Agent 基础盘点

| 已有能力 | 实现位置 | 成熟度 |
| :--- | :--- | :--- |
| LangGraph ReAct 循环 | `graphs/conversation.py` | ✅ 已上线 |
| 意图路由（规则 + LLM） | `nodes/route_intent.py` | ✅ 已上线 |
| 18 个平台工具 | `tools/` | ✅ 已上线 |
| SQLite Checkpoint | `output/agent_checkpoints.sqlite` | ✅ 已上线 |
| RAG 私有知识库检索 | `application/knowledge/` | ✅ 已上线 |
| 热榜分析节点 | `nodes/analyze_hotlist.py` | ✅ 已上线 |
| 回答精修节点 | `graphs/refinement.py` | ✅ 已上线 |

### 1.3 升级目标

将项目从「LLM 应用内嵌 Agent 子系统」演进为「以 Agent 为核心驱动力的创作平台」，
覆盖以下五个核心能力维度：

1. **自主规划（Planning）**：Agent 能将模糊大目标自动拆解为可执行子任务序列
2. **长期记忆（Long-term Memory）**：跨会话保存用户偏好、历史质量反馈与写作风格
3. **反思与自我修正（Reflection）**：Agent 自评生成结果质量，主动触发修正迭代
4. **主动感知（Proactive Sensing）**：定时监控热榜与内容机会，主动推送创作建议
5. **多 Agent 协作（Multi-Agent）**：拆分专职 Agent，实现并行研究与内容分工协同

---

## 2. 功能一：自主规划引擎（Autonomous Planning）

### 2.1 问题描述

当前 Agent 仅能处理单轮意图（chat / parse_url），无法接受如「帮我在知乎写一篇
关于 DeepSeek 的爆款回答」这种需要多步骤编排的复合目标。

### 2.2 功能描述

用户在对话框输入复合创作目标，Agent 自动生成并执行**任务计划（Task Plan）**，
包含以下能力：

- **目标分解**：将自然语言目标拆解为有序子任务列表（如：搜索热度 → 竞品分析 →
  生成提纲 → 逐段写作 → 自评修正）
- **并行执行**：无依赖关系的子任务可并行调度（如：同时抓取多平台相关内容）
- **动态调整**：执行中若发现中间结果质量不达标，自动重新规划剩余步骤
- **进度透明**：前端实时流式展示每个子任务的执行状态（等待 / 执行中 / 完成 / 失败）

### 2.3 技术方案

```
用户输入复合目标
    ↓
PlannerNode（LLM 生成 TaskPlan JSON）
    ↓
TaskExecutorGraph（按 DAG 依赖关系调度子任务）
    ├── SearchSubTask    → 调用 web_search / zhihu_tool 等
    ├── AnalyzeSubTask   → 热榜分析、竞品分析
    ├── OutlineSubTask   → 生成写作提纲
    ├── WritingSubTask   → 逐节段生成正文
    └── ReviewSubTask    → 自评与修正
    ↓
结果汇总 → 写入 WorkSession / Document
```

### 2.4 数据模型扩展

```python
class TaskPlan(BaseModel):
    plan_id: str
    goal: str                           # 用户原始目标
    tasks: list[SubTask]                # 有序子任务列表
    status: Literal["pending", "running", "done", "failed"]
    created_at: datetime

class SubTask(BaseModel):
    task_id: str
    type: Literal["search", "analyze", "outline", "write", "review"]
    description: str
    depends_on: list[str]               # 依赖的 task_id 列表
    status: Literal["pending", "running", "done", "failed"]
    result: str | None
```

### 2.5 前端 UI 需求

- 对话框新增「任务模式」切换入口
- 对话流中以可折叠卡片形式展示实时 TaskPlan 进度树
- 每个子任务节点显示状态指示灯与耗时
- 任务完成后自动将最终文章填入工作台编辑器

### 2.6 验收标准

- [ ] 用户输入「帮我写一篇知乎回答：xxx」，Agent 自动生成并执行 5 步以上的 TaskPlan
- [ ] 前端实时流式渲染 TaskPlan 进度
- [ ] 单个子任务失败时，其他已完成任务结果保留，失败任务可单独重试
- [ ] TaskPlan 执行总耗时不超过 120 秒（对于 5 步计划）

---

## 3. 功能二：长期记忆系统（Long-term Memory）

### 3.1 问题描述

当前每次对话完全无状态（仅有当前 session 上下文），Agent 不记得：
- 用户偏好的写作风格（幽默 / 严肃 / 数据驱动）
- 历史回答中哪些质量好、哪些被用户删改
- 用户常用的信息来源偏好（偏好知乎 vs 小红书）

### 3.2 功能描述

建立**用户记忆档案（User Memory Profile）**，持久化存储以下三类记忆：

#### 3.2.1 显式记忆（Explicit Facts）
用户在对话中明确告知的信息：
- 「我的写作风格偏向幽默风趣」
- 「我不想引用百度百科的内容」
- 「我的目标读者是大学生」

#### 3.2.2 隐式偏好（Implicit Preferences）
从用户行为中学习的偏好：
- 用户编辑回答时删除了哪些类型的内容 → 该类型写法得分降低
- 用户确认索引的知识库文档类型分布 → 推断领域偏好
- 用户在哪些话题上产出效率最高 → 优先推荐相关热榜

#### 3.2.3 工作习惯（Work Patterns）
- 常用平台组合（如固定搜索知乎 + Reddit）
- 常用生成配置（回答字数、段落数、Prompt 偏好）

### 3.3 技术方案

```
每次 Agent 运行结束后：
    MemoryExtractorNode
        ↓
    提取本次对话中的可记忆信息（LLM 抽取）
        ↓
    写入 user_memories 表（向量化存储 + 结构化标签）

每次 Agent 运行开始时：
    MemoryRetrieverNode
        ↓
    从 user_memories 检索与当前任务相关的记忆片段
        ↓
    注入 System Prompt 上下文
```

### 3.4 数据模型

```python
class UserMemory(Base):
    __tablename__ = "user_memories"
    id: str (UUID PK)
    workspace_id: str
    memory_type: Literal["explicit", "implicit", "work_pattern"]
    content: str                        # 记忆内容文本
    embedding: vector(1536)             # 向量化存储（pgvector）
    confidence: float                   # 置信度 0.0~1.0
    source: str                         # 来源（session_id / 行为事件）
    created_at: datetime
    last_activated_at: datetime         # 最近一次被检索激活的时间
    activation_count: int               # 被激活次数（高频记忆优先）
```

### 3.5 前端 UI 需求

- 设置页新增「我的记忆」标签页，展示 Agent 记录的所有记忆条目
- 支持用户手动编辑、确认或删除记忆条目
- 对话界面显示「已应用 N 条记忆」的 Badge 提示

### 3.6 验收标准

- [ ] 第二次打开 Agent 后，Agent 能在回答中体现上次用户明确告知的写作风格
- [ ] 用户频繁删除「列表式结尾」后，Agent 后续生成中减少该写法
- [ ] 记忆条目在设置页可视化展示和管理
- [ ] 单次记忆检索耗时不超过 200ms

---

## 4. 功能三：反思与自我修正循环（Reflection Loop）

### 4.1 问题描述

当前生成的回答质量依赖单次 LLM 输出，没有自评机制。用户需要手动判断质量并
点击「润色」按钮，Agent 无法主动发现并修正低质量内容。

### 4.2 功能描述

在内容生成后自动触发**自评-修正迭代循环**：

- **自评维度**：信息密度、逻辑连贯性、可读性、与提问的相关性、字数合规性
- **评分阈值**：综合评分 < 0.75 时自动触发一次修正（最多迭代 3 次）
- **修正方向**：根据评分维度中的短板定向修正（而非全文重写）
- **结果对比**：前端 Diff 展示修正前后的具体变更

### 4.3 技术方案

```
WritingNode（首次生成）
    ↓
ReflectionNode（LLM 自评，输出结构化评分 JSON）
    ├── score >= 0.75 → 直接输出
    └── score < 0.75 → RefinementNode（定向修正）
                            ↓
                       ReflectionNode（再次自评）
                            ↓
                       最多循环 3 次后强制输出
```

### 4.4 评分协议

```json
{
  "overall_score": 0.68,
  "dimensions": {
    "relevance": 0.85,
    "information_density": 0.60,
    "readability": 0.72,
    "logic_coherence": 0.70,
    "word_count_compliance": 0.65
  },
  "weakness_summary": "信息密度不足，缺少具体数据和案例支撑",
  "refinement_instruction": "在第 2、3 段补充具体数据，删除冗余的过渡句"
}
```

### 4.5 前端 UI 需求

- 工作台底部展示「质量评分」进度条与维度雷达图
- 生成完成后显示自评过程（「已自评 2 轮，最终得分 0.82」）
- 提供「查看修正历程」按钮，展示每轮 Diff

### 4.6 验收标准

- [ ] 首次生成评分 < 0.75 时，自动触发修正而无需用户手动操作
- [ ] 每个评分维度有明确的数值展示
- [ ] 迭代修正后综合评分相比首次提升 ≥ 0.08
- [ ] 反思循环最多 3 轮，超过后强制输出并提示用户

---

## 5. 功能四：主动感知与推送（Proactive Sensing）

### 5.1 问题描述

当前热榜分析完全被动（用户在对话中主动询问才触发），用户需要时刻盯着平台才
能发现内容机会，Agent 没有主动创造价值的能力。

### 5.2 功能描述

Agent 定时自主运行**内容机会扫描（Opportunity Scanner）**：

- **定时扫描**：每小时自动扫描知乎、小红书等平台热榜
- **机会识别**：结合用户的长期记忆（兴趣领域、历史产出），识别高匹配内容机会
- **主动推送**：在工作台顶部展示「今日内容机会」通知卡片
- **一键启动**：用户点击通知卡片，自动以该热榜问题为目标启动 TaskPlan

### 5.3 触发时机

| 触发类型 | 说明 | 频率 |
| :--- | :--- | :--- |
| 定时扫描 | 每小时自动抓取热榜并评分 | 每小时 |
| 启动触发 | 用户打开应用时立即扫描一次 | 每次启动 |
| 手动触发 | 用户点击「立即扫描」按钮 | 按需 |

### 5.4 机会评分模型

```
机会得分 = 热度权重 × 0.4
          + 用户领域匹配度 × 0.35
          + 竞争程度（现有回答质量低则分高）× 0.15
          + 时效性（越新越高）× 0.10
```

### 5.5 前端 UI 需求

- 工作台顶部「今日机会」横幅（可折叠），最多展示 3 条推荐卡片
- 每张卡片显示：平台、标题、热度分、匹配度、现有回答数
- 点击「一键创作」直接拉起 TaskPlan
- 设置页支持配置感兴趣的领域 Tag、每日推送时间窗口

### 5.6 验收标准

- [ ] 后端定时任务每小时执行一次热榜扫描，结果写入数据库
- [ ] 推荐算法结合用户历史产出领域，排除已创作过的问题
- [ ] 前端「今日机会」卡片实时刷新（SSE 推送）
- [ ] 用户可在设置页关闭主动推送

---

## 6. 功能五：多 Agent 协作框架（Multi-Agent Collaboration）

### 6.1 问题描述

当前所有任务由单一 Chat Agent 串行处理，对于需要同时从多平台深度研究的复杂
创作任务，串行效率低下，且单个 Agent 的上下文窗口容易被大量信息撑爆。

### 6.2 功能描述

拆分为**专职子 Agent**，由**协调 Agent（Orchestrator）**统一调度：

| Agent 名称 | 职责 | 工具集 |
| :--- | :--- | :--- |
| **OrchestratorAgent** | 接受用户目标，拆解 TaskPlan，分配给子 Agent | 无工具，只做调度 |
| **ResearchAgent** | 多平台并行信息采集与分析 | web_search, zhihu_tool, reddit_tool, github_tool 等 |
| **WritingAgent** | 根据 Research 结果生成结构化内容 | 无外部工具，依赖 RAG + LLM |
| **ReviewAgent** | 自评与修正，输出质量评分 | 无外部工具，纯 LLM 推理 |
| **MemoryAgent** | 管理用户长期记忆的读写 | 向量检索工具 |

### 6.3 协作流程

```
用户输入目标
    ↓
OrchestratorAgent（生成 TaskPlan，分配给子 Agent）
    ├── ResearchAgent × N（并行抓取多平台）
    │       ↓（研究报告）
    ├── WritingAgent（基于研究报告生成初稿）
    │       ↓（初稿）
    └── ReviewAgent（自评 + 修正）
            ↓（终稿）
MemoryAgent（沉淀本次创作记忆）
    ↓
用户收到完成通知
```

### 6.4 技术方案

- 使用 **LangGraph Multi-Agent** 模式（子图嵌套）
- 子 Agent 之间通过**共享状态频道**传递中间结果
- 使用 **LangGraph 的 interrupt/resume** 机制，在关键节点暂停等待用户确认

### 6.5 前端 UI 需求

- 对话界面「Agent 工作区」面板：实时展示各子 Agent 的运行状态树
- 每个子 Agent 有独立的日志折叠区，展示其工具调用记录
- 用户可在 OrchestratorAgent 分配完子任务后，手动调整分配策略

### 6.6 验收标准

- [ ] ResearchAgent 能真正并行调用多个平台工具（并发 > 3）
- [ ] 各子 Agent 之间状态隔离，单个子 Agent 失败不影响其他子 Agent
- [ ] 前端实时展示多 Agent 协作树状态图
- [ ] 整体协作执行时间比串行方案缩短 ≥ 40%

---

## 7. 实现优先级与路线图

根据技术复杂度与对用户价值的影响，建议按以下顺序实现：

```
Phase 1（当前版本已完成）
├── ReAct 工具调用 ✅
├── 意图路由 ✅
├── RAG 私有知识库 ✅
└── 热榜分析 ✅

Phase 2（短期目标，建议 4~6 周）
├── 功能三：反思与自我修正循环    ← 复用现有 refinement 节点，改造最小
└── 功能四：主动感知（定时扫描）  ← 复用现有热榜工具，增加定时任务即可

Phase 3（中期目标，建议 6~10 周）
└── 功能一：自主规划引擎          ← 核心复杂度最高，需要新建 PlannerNode + TaskExecutorGraph

Phase 4（长期目标，建议 10~16 周）
├── 功能二：长期记忆系统           ← 需要引入 pgvector + 记忆提取/检索管道
└── 功能五：多 Agent 协作框架      ← 架构重构，需要 LangGraph 子图嵌套
```

---

## 8. 依赖与风险

| 风险 | 影响 | 应对方案 |
| :--- | :--- | :--- |
| LLM 规划结果不稳定 | 功能一 TaskPlan 质量无法保证 | 使用 Few-shot 示例 + JSON Schema 约束 LLM 输出 |
| 长期记忆隐私合规 | 用户敏感信息被持久化 | 全本地存储，不上传任何记忆数据；提供一键清空 |
| 多 Agent 调试困难 | 功能五 Bug 定位复杂 | LangGraph Studio 可视化调试 + 完整结构化日志 |
| 定时任务资源占用 | 功能四 每小时扫描消耗 API 配额 | 非活跃时间段（如凌晨 1-7 点）跳过扫描 |
| 反思循环死循环 | 功能三 迭代不收敛 | 硬性上限 3 轮，超过强制输出 + 用户告警 |

---

## 9. 技术架构影响评估

| 组件 | 当前状态 | 升级后变化 |
| :--- | :--- | :--- |
| `graphs/conversation.py` | 单图 ReAct | 新增 `planner_graph.py`、`multi_agent_graph.py` |
| `nodes/` | 12 个节点 | 新增 PlannerNode、MemoryExtractor、MemoryRetriever、ReflectionNode |
| `tools/` | 18 个工具 | 新增 MemorySearchTool、OpportunityScanTool |
| `state.py` | ChatAgentState | 新增 TaskPlanState、MultiAgentState |
| `models.py` | 无记忆/计划模型 | 新增 UserMemory、TaskPlan、SubTask、QualityScore |
| 数据库 | SQLite checkpoint | 新增 `user_memories`、`task_plans`、`opportunity_feeds` 表 |
| 基础设施 | 无定时任务 | 引入 APScheduler 或 Celery Beat |
