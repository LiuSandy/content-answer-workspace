# 功能规范：结构化输出与内容大纲（Structured Output & Outline Generation）

**版本：** 2.0
**日期：** 2026-08-05
**状态：** 待评审
**作者：** 架构设计
**重写说明：** 本文档为《Outlines 受限解码与结构化输出集成》(v1.0) 的重写版。
v1.0 的过时点见 §1.1，本文档同时澄清了"outlines"在本仓库被误当作
"内容大纲生成"spec 引用的命名混淆（见 §1.2）。

---

## 1. 背景与重写说明

### 1.1 v1.0 过时性分析

| 过时点 | v1.0 内容 | 现状 |
| :--- | :--- | :--- |
| 技术方案 | 集成 Outlines 库做 token 级引导解码 | 项目使用 DeepSeek（OpenAI 兼容 API），引导解码仅对本地后端（transformers/vLLM/llama.cpp）有效，对 OpenAI 兼容端点收益大打折扣 |
| 意图路由 | 操作集 `[collect_request, hotlist_analysis, inline_refinement, general_chat]` | 实际意图仅 `{chat, parse_url}`，且**规则优先 + LLM 兜底**（`route_intent.py:45`） |
| 热榜分析 | 热点分析 Agent 提取结构化 Topic | 已改道 `fetch_hotlist` 直连知乎官方 API + SSE 返回 `HotlistResponse`，无 Agent 分析 |
| 配图 / 合规 | 配图 prompt 提取、合规审查模块 | 配图存在于旧采集工作流（`image_service`），将迁入 **Content Writer** 链路（见 agent-platform-split spec §4.5）；合规审查未落地，已演化为 **Quality Reviewer**（见 agent-platform-split spec） |

### 1.2 命名澄清

- v1.0 标题指 **Outlines 库**（结构化生成）。
- 但 `docs/specs/content-creation-pipeline.md` 将其引用为 **"内容大纲（outline）生成"** spec。
- 本文档统一覆盖两层语义：
  - **结构化输出（技术底座）**：让 LLM 的"决策类输出"返回合法 Pydantic 对象，消灭手写 JSON 解析
  - **内容大纲（业务场景）**：创作前生成文章大纲，属于结构化输出的一个应用

### 1.3 目标

1. 用 `with_structured_output` 统一替换手写 JSON 解析（`route_intent.py:39-45` 为真实痛点）
2. 定义内容大纲生成规范，支撑 Content Writer 的「大纲 → 分段生成」链路
3. 明确失败兜底与降级策略，适配 DeepSeek 对 structured output 支持不稳定的现状

---

## 2. 方案选型

| 方案 | token 级约束 | 兼容 DeepSeek | 与流式兼容 | 结论 |
| :--- | :--- | :--- | :--- | :--- |
| Outlines 引导解码 | ✅ | ❌ 仅本地后端 | 部分 | **不采用** |
| **LangChain `with_structured_output`** | ❌（schema 引导 + JSON mode） | ✅ | ✅ | **✅ 采用** |
| 原生 JSON mode（`response_format`） | ❌ | ✅ | ✅ | 降级兜底 |
| 工具调用 `bind_tools` | — | ✅ | ✅ | 已有（chat_node:23），复用 |

**选定方案**：`ChatOpenAI.with_structured_output(PydanticModel)`，失败时降级
JSON mode → 通用解析。项目已依赖 `langchain-openai`，无新增依赖。

**底座统一（避免双体系）**：`StructuredOutputClient` 直接基于 **LangChain
`ChatOpenAI`** 构造——与 `chat_node`（bind_tools）同属 langchain 调用体系，
复用同一模型实例与参数装配。`infrastructure/llm/registry.py` 只负责按 model
profile **提供 `ChatOpenAI` 实例/参数**，不另起一套裸 OpenAI client；
provider 差异化能力（如 DeepSeek 的 JSON mode）通过 registry 透传模型参数实现。

---

## 3. 统一基础设施

新建 `app/infrastructure/llm/structured.py`：

```python
class StructuredOutputClient:
    """结构化输出统一客户端；封装 schema 生成、调用与降级重试。"""

    async def generate(
        self,
        *,
        schema: type[BaseModel],
        system_prompt: str,
        user_prompt: str,
        retries: int = 1,
    ) -> BaseModel:
        # ① 优先 with_structured_output（json_schema 模式）
        # ② provider 不支持或校验失败 → JSON mode + model_validate_json
        # ③ 仍失败 → 通用解析（提取 JSON 片段），记录降级日志
        ...
```

**降级顺序与日志**：每次降级记录 `degraded: reason` 到 `AIOperation.model_parameters`，
可观测性复用现有 `ai_operations` 表。

---

## 4. 场景清单（对齐当前代码与设计）

| # | 场景 | 现状 | 输出 Schema | 优先级 |
| :--- | :--- | :--- | :--- | :--- |
| 1 | 意图路由 | ❌ `route_intent.py:39-45` 手写 `json.loads` + try-except | `IntentRoute` | P0 |
| 2 | 内容大纲 | ❌ 未实现 | `ArticleOutline` | P1 |
| 3 | 选题评估 | ❌ Topic Analyst 未实现 | `TopicEvaluation` | P1 |
| 4 | 质检报告 | ❌ Quality Reviewer 未实现 | `QualityReport` | P1 |
| 5 | 记忆提取 | ❌ memory_extract 未实现 | `MemoryExtraction` | P2 |
| 6 | 滚动摘要 | ❌ summary_updater 未实现 | `ConversationSummary` | P2 |
| 7 | 工具参数 | ✅ `bind_tools`（chat_node:23） | LangChain 工具 schema | 复用 |
| 8 | 热榜选题 | ⚠️ 遗留 `analysis.py` 死代码 | 并入场景 3 `TopicEvaluation` | P1（对齐 Topic Analyst） |

### 4.1 场景 1：意图路由（P0，真实痛点）

**现状**：`route_intent.py:39-45` 手写 JSON 解析，非法 JSON 直接降级 chat。

```python
class IntentRoute(BaseModel):
    intent: Literal["chat", "parse_url"] = Field(description="路由意图")
```

**接入点**：替换 `route_intent.py` 中 LLM 分支为 `StructuredOutputClient.generate`；
规则优先分支（URL 检测）保持不变。

### 4.2 场景 2：内容大纲生成（P1，业务重点）

**输入**：题目 title + 原文 content + 平台 + 风格规则 + 用户观点（可选）。

```python
class OutlineSection(BaseModel):
    heading: str = Field(description="小节标题")
    key_points: list[str] = Field(description="该小节的核心要点，最多 5 条")
    word_count_estimate: int = Field(description="该小节预估字数")

class ArticleOutline(BaseModel):
    hook_suggestion: str = Field(description="开头钩子建议")
    sections: list[OutlineSection] = Field(description="正文大纲段落")
    closing_suggestion: str = Field(description="结尾收束建议")
```

**流程**：

```text
编辑器「生成大纲」
    ├─（可选）前置观点采集：向用户提 2~3 个采访问题，回答记为 viewpoint_notes
    │         （衔接 content-creation-pipeline §4.2，观点注入 → 大纲 → 生成）
    ▼
StructuredOutputClient → 大纲卡片预览
    → 用户确认/微调 → 分段生成（Content Writer，agent-platform spec §4.5）
```

**数据模型**：大纲作为 `AIOperation`（operation_type=`outline`）记录存档，
确认后按段落调用 Content Writer 分段生成；`viewpoint_notes` 关联 `AnswerDocument`
（`content-creation-pipeline` §4.2），观点作为大纲与分段生成的注入素材；
无需新增表。

### 4.3 场景 3：选题评估（P1）

**输入**：采集元数据（标题、浏览量、回答数、热度）。

```python
class TopicEvaluation(BaseModel):
    worth_score: int = Field(ge=0, le=100, description="值得答指数")
    reason: str = Field(description="一句话理由")
    competition_level: Literal["low", "medium", "high"]
    suggestion: str = Field(description="作答建议")
```

**接入点**：Topic Analyst Agent 的 `evaluate_topic` 节点。

### 4.4 场景 4：质检报告（P1）

**输入**：回答全文 + 平台。

```python
class QualityReport(BaseModel):
    ai_flavor_score: int = Field(ge=0, le=100, description="AI 味检测分，越高越自然")
    hook_score: int = Field(ge=0, le=100)
    compliance_issues: list[str] = Field(default_factory=list, description="合规问题清单")
    suggestions: list[str] = Field(default_factory=list, description="逐条修改建议")
    recommend_rewrite: bool = Field(description="是否建议重写")
```

**接入点**：Quality Reviewer Agent；报告作为 `AIOperation` 存档。

### 4.5 场景 5：记忆提取（P2）

```python
class MemoryItem(BaseModel):
    memory_type: Literal["explicit", "work_pattern"]
    content: str
    confidence: float = Field(ge=0, le=1)

class MemoryExtraction(BaseModel):
    items: list[MemoryItem]
```

### 4.6 场景 6：滚动摘要（P2）

```python
class ConversationSummary(BaseModel):
    summary: str
    covered_message_ids: list[str]
```

---

## 5. 数据流

- **路由/决策链路**（同步）：chat → `route_intent` 用 StructuredOutputClient → 后续节点
- **大纲链路**（交互）：编辑器 → 生成大纲 → 用户确认 → 分段生成
- **批量分析链路**（异步）：选题评估 / 质检 / 记忆提取 / 摘要，走 `BackgroundTasks`

---

## 6. API 与前端

| 端点 | 说明 |
| :--- | :--- |
| `POST /api/source-items/{id}/outline` | 生成大纲（SSE 或一次性返回均可，建议一次性返回供预览） |

前端：
- 编辑器新增「生成大纲」按钮 → 大纲预览卡片（钩子/段落/要点）→ 确认后进入生成
- 选题评分徽章、质检报告面板（复用 agent-platform-split spec 设计）

---

## 7. 实现优先级与验收

| Phase | 内容 | 验收标准 |
| :--- | :--- | :--- |
| **P0** | StructuredOutputClient + 意图路由替换 | 路由无手写 JSON；非法输出自动降级且可观测 |
| **P1** | 大纲 + 选题评估 + 质检报告 | 大纲可生成/确认/分段生成；选题与质检输出 100% 合法 |
| **P2** | 记忆提取 + 滚动摘要 | 与 context-memory spec §4.3/§3.3 衔接 |

### P0 验收细节

- [ ] `route_intent.py` 移除 `json.loads` 手写解析
- [ ] 结构化失败重试 1 次，降级不抛异常
- [ ] 降级路径写入 `AIOperation.model_parameters.degraded`
- [ ] 现有 4 条 SSE 链路回归通过

---

## 8. 依赖与风险

| 风险 | 影响 | 应对 |
| :--- | :--- | :--- |
| DeepSeek structured output 支持不稳定 | schema 校验失败率高 | 自动降级 JSON mode + 重试；降级可观测 |
| schema 过严导致输出失败 | 决策链路中断 | 字段尽量可选，description 给足语义引导 |
| 大纲生成改变创作心智 | 用户不适应 | 大纲仅预览+确认，不自动生成；可关闭 |
| 与流式创作冲突 | 润色/重写被误约束 | **只约束决策类输出**，自由文本（正文/润色）不接入 |
| 大规模批量分析成本 | API 配额上升 | 批量场景走异步 + 阈值触发（同 context-memory spec） |

---

## 9. 技术架构影响评估

| 组件 | 当前状态 | 变化后 |
| :--- | :--- | :--- |
| `route_intent.py` | 手写 JSON 解析 | 改用 StructuredOutputClient |
| `infrastructure/llm/` | registry + deepseek provider | + `structured.py` 统一客户端；registry 改为按 model profile 提供 `ChatOpenAI` 实例/参数 |
| `prompts/` | writing/chat/refinement | + `outline/` 提示词目录 |
| `application/` | workflow_service 等 | + 大纲生成逻辑（Content Writer 子能力） |
| `api/routes/` | 7 个路由 | + outline 端点 |
| `ai_operations` | 已有表 | operation_type 增加 `outline`，model_parameters 记录降级 |
| 前端 | 编辑器 | + 大纲生成/预览卡片 |
