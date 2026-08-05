# 功能规范：结构化输出与内容大纲（Structured Output & Outline Generation）

**版本：** 2.2
**日期：** 2026-08-05
**状态：** 待评审
**作者：** 架构设计
**重写说明：** 本文档为《Outlines 受限解码与结构化输出集成》(v1.0) 的重写版。
v1.0 的过时点见 §1.1，本文档同时澄清了"outlines"在本仓库被误当作
"内容大纲生成"spec 引用的命名混淆（见 §1.2）。

> **2.1 修订说明**：远程分支已落地三层意图识别（`route_intent.py`）、
> 机会评分（`opportunity_service.py`）、反思评分（`reflection.py`）、
> 记忆提取（`memory_service.py`）。这些实现**仍大量使用手写 `json.loads` 解析**，
> 场景清单已更新为与代码现状一一对应；未实现的选题/质检/大纲保持 ◻️。
>
> **2.2 修订说明**：评审补齐 schema 与代码的真实匹配——
> ① `IntentRoute` 需含 `knowledge_mode` / `confidence` / `platform` / `query` /
> `reason` 字段（否则替换 `route_intent.py` 时丢功能，§4.1）；
> ② `MemoryExtraction` 的 `memory_type` 需含 `implicit`（对齐 `VALID_TYPES`，§4.5）；
> ③ 结构化输出作为 registry/适配器的**方法**（`generate_structured`）而非第三套
> 独立入口（§2/§3）；
> ④ 大纲/观点的落库载体明确为 `AIOperation.input_metadata`（§4.2）。

---

## 1. 背景与重写说明

### 1.1 v1.0 过时性分析

| 过时点 | v1.0 内容 | 现状 |
| :--- | :--- | :--- |
| 技术方案 | 集成 Outlines 库做 token 级引导解码 | 项目使用 DeepSeek（OpenAI 兼容 API），引导解码仅对本地后端（transformers/vLLM/llama.cpp）有效，对 OpenAI 兼容端点收益大打折扣 |
| 意图路由 | 操作集 `[collect_request, hotlist_analysis, inline_refinement, general_chat]` | 已实现**三层意图识别**（规则 → LLM → 校验，`route_intent.py` + `intent_rules.py`），意图集 `{chat, parse_url, task_plan, multi_agent}`，**LLM 分支仍手写 `json.loads`（`route_intent.py:76`）** |
| 热榜分析 | 热点分析 Agent 提取结构化 Topic | 已改道 `fetch_hotlist` 直连知乎官方 API + 机会评分（`opportunity_service.py`），无独立分析 Agent |
| 配图 / 合规 | 配图 prompt 提取、合规审查模块 | 配图存在于旧采集工作流（`image_service`），将迁入 **Content Writer** 链路（见 agent-platform-split spec §4.5）；合规审查未落地，评分由**反思循环**（`reflection.py`）承担 |

### 1.2 命名澄清

- v1.0 标题指 **Outlines 库**（结构化生成）。
- 但 `docs/specs/content-creation-pipeline.md` 将其引用为 **"内容大纲（outline）生成"** spec。
- 本文档统一覆盖两层语义：
  - **结构化输出（技术底座）**：让 LLM 的"决策类输出"返回合法 Pydantic 对象，消灭手写 JSON 解析
  - **内容大纲（业务场景）**：创作前生成文章大纲，属于结构化输出的一个应用

### 1.3 目标

1. 用 `with_structured_output` 统一替换手写 JSON 解析（`route_intent.py:76` 为真实痛点）
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

**底座统一（避免三套 LLM 入口）**：结构化输出直接基于 **LangChain
`ChatOpenAI`** 构造——与 `chat_node`（bind_tools）同属 langchain 调用体系，
复用同一模型实例与参数装配。**2.2 评审**：结构化输出作为
`infrastructure/llm/registry.py` / `agents/adapters.py` 的一个方法
（如 `DeepSeekLLMAdapter.generate_structured(schema, ...)`）提供，而不是另起一套
独立文件入口，避免"统一消灭手写 JSON"演变成第三套调用体系。registry 只负责按
model profile **提供 `ChatOpenAI` 实例/参数**并透传 provider 差异化能力
（如 DeepSeek 的 JSON mode）；模型调用统一经 `agents/adapters.py` 封装。

---

## 3. 统一基础设施

在 `app/infrastructure/llm/` 增加 `structured` 能力（**作为 registry/适配器的
方法**，见 §2；文件命名 `structured.py` 仅作实现模块）：

```python
class DeepSeekLLMAdapter:  # 扩展 agents/adapters.py 现有类
    async def generate_structured(
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
可观测性复用现有 `ai_operations` 表。所有消费方（route_intent / extractor /
summary / reviewer / analyst）统一经此方法，不各自实现解析。

---

## 4. 场景清单（对齐当前代码与设计）

| # | 场景 | 现状 | 输出 Schema | 优先级 |
| :--- | :--- | :--- | :--- | :--- |
| 1 | 意图路由 | ⚠️ 三层识别已实现，LLM 分支仍手写 `json.loads`（`route_intent.py:76`） | `IntentRoute` | P0 |
| 2 | 内容大纲 | ❌ 未实现（Writer 未落地） | `ArticleOutline` | P1 |
| 3 | 选题评估 | ⚠️ `opportunity_service` 规则打分已实现，缺 LLM `TopicEvaluation` | `TopicEvaluation` | P1 |
| 4 | 质检报告 | ⚠️ `reflection.py` 5 维评分已实现，缺 `QualityReport` schema 与采纳链路 | `QualityReport` | P1 |
| 5 | 记忆提取 | ⚠️ `memory_service.extract_memories` 已实现，`_parse_extraction_json` 手写解析（`memory_service.py:56`） | `MemoryExtraction` | P2 |
| 6 | 滚动摘要 | ❌ `summary_updater` 未实现 | `ConversationSummary` | P2 |
| 7 | 工具参数 | ✅ `bind_tools`（chat_node:23） | LangChain 工具 schema | 复用 |
| 8 | 机会选题 | ⚠️ `opportunity_service` 规则评分已实现；`analysis.py` 死代码待删 | 并入场景 3 `TopicEvaluation` | P1 |

### 4.1 场景 1：意图路由（P0，真实痛点）

**现状**：三层意图已实现（规则优先 → LLM 兜底 → 校验降级，`route_intent.py`），
但 LLM 分支仍手写 `json.loads`（`route_intent.py:76`），非法 JSON 才降级 chat；
`collect` 规则已并入 `intent_rules.py`。

```python
class IntentRoute(BaseModel):
    intent: Literal["chat", "parse_url", "task_plan", "multi_agent"] = Field(description="路由意图")
    # 2.2 评审补录：route_intent_node 真实消费这些字段，缺了会在替换时丢功能
    knowledge_mode: Literal["off", "normal", "strict"] = Field(default="normal")
    confidence: float = Field(default=0.9, ge=0.0, le=1.0)   # L2 低置信度降级判断
    platform: str | None = Field(default=None)                # 采集/搜索目标平台
    query: str | None = Field(default=None)                   # 采集/搜索关键词
    reason: str | None = Field(default=None)                  # 路由理由（可观测）
```

**接入点**：替换 `route_intent.py` 中 LLM 分支为 `generate_structured(IntentRoute)`，
**保留 L2 校验逻辑**（`_MIN_CONFIDENCE=0.6` 低置信度降级 chat、`strict`/`off`
显式模式保留、规则层命中结果与 LLM 结果合并——`route_intent.py:104`）。
规则优先分支保持不变。

### 4.2 场景 2：内容大纲生成（P1，业务重点）◻️

**现状**：Writer 未落地，`ArticleOutline` schema 不存在。

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
`generate_structured` → 大纲卡片预览
    → 用户确认/微调 → 分段生成（Content Writer，agent-platform spec §4.5）
```

**数据模型（2.2 评审澄清落库载体）**：大纲作为 `AIOperation`
（`operation_type=outline`）记录存档；**`viewpoint_notes` 与确认后的大纲快照
存入同一 `AIOperation.input_metadata` JSONB**（无需改 `answer_documents` 表——
`source_item_id` 经 document 关联即可定位）。确认后按段落调用 Content Writer
分段生成；观点作为大纲与分段生成的注入素材。若后续需要跨任务查询观点，
再评估为 `answer_documents` 加独立列。

### 4.3 场景 3：选题评估（P1）

**现状**：`opportunity_service.py` 规则打分已实现
（`W_HOT/W_MATCH/W_COMPETITION/W_RECENCY`，落库 `opportunity_feeds`），
缺 LLM 维度 `TopicEvaluation`（`user_match`、原因、建议）。

**输入**：采集元数据（标题、浏览量、回答数、热度）或机会扫描候选。

```python
class TopicEvaluation(BaseModel):
    worth_score: int = Field(ge=0, le=100, description="值得答指数")
    reason: str = Field(description="一句话理由")
    competition_level: Literal["low", "medium", "high"]
    suggestion: str = Field(description="作答建议")
```

**接入点**：`opportunity_service` 打分后追加 LLM `evaluate_topic` 节点
（agent-platform-split spec §4.4）。

### 4.4 场景 4：质检报告（P1）

**现状**：`reflection.py` 5 维评分已实现
（relevance/information_density/readability/logic_coherence/word_count_compliance，
阈值 0.75），`reflect_refine.py` 迭代修正 ≤3 轮；
缺 `QualityReport` schema 与一键采纳链路（`quality_adopt`）。

**输入**：回答全文 + 平台。

```python
class QualityReport(BaseModel):
    ai_flavor_score: int = Field(ge=0, le=100, description="AI 味检测分，越高越自然")
    hook_score: int = Field(ge=0, le=100)
    compliance_issues: list[str] = Field(default_factory=list, description="合规问题清单")
    suggestions: list[str] = Field(default_factory=list, description="逐条修改建议")
    recommend_rewrite: bool = Field(description="是否建议重写")
```

**接入点**：Quality Reviewer 节点；报告作为 `AIOperation` 存档，`quality_adopt`
一键采纳（agent-platform-split spec §4.6）。

### 4.5 场景 5：记忆提取（P2）

**现状**：`memory_service.extract_memories` 已实现，`_parse_extraction_json`
手写 `json.loads`（`memory_service.py:56`）；仅 multi_agent 的 MemoryAgent 调用，
未接主对话图。

```python
class MemoryItem(BaseModel):
    memory_type: Literal["explicit", "implicit", "work_pattern"]  # 2.2 评审：补 implicit，对齐 memory_service.VALID_TYPES
    content: str
    confidence: float = Field(ge=0, le=1)

class MemoryExtraction(BaseModel):
    items: list[MemoryItem]
```

### 4.6 场景 6：滚动摘要（P2）◻️

**现状**：未实现；`chats.py:262` 仍全量拼接历史、thread_id 每次新建。

```python
class ConversationSummary(BaseModel):
    summary: str
    covered_message_ids: list[str]
```

---

## 5. 数据流

- **路由/决策链路**（同步）：chat → `route_intent` 用 `generate_structured` → 后续节点
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
| **P0** | `generate_structured` + 意图路由替换 | 路由无手写 JSON；非法输出自动降级且可观测 |
| **P1** | 大纲 + 选题评估 + 质检报告 | 大纲可生成/确认/分段生成；选题与质检输出 100% 合法 |
| **P2** | 记忆提取 + 滚动摘要 | 与 context-memory spec §4.3/§3.3 衔接 |

### P0 验收细节

- [ ] `route_intent.py` 移除 `json.loads` 手写解析，`IntentRoute` 全字段（含 knowledge_mode/confidence/platform/query/reason）正常消费，L2 校验行为与重构前一致
- [ ] 结构化失败重试 1 次，降级不抛异常
- [ ] 降级路径写入 `AIOperation.model_parameters.degraded`
- [ ] 现有 SSE 流式链路回归通过

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
| `route_intent.py` | 手写 JSON 解析（`route_intent.py:76`） | 改用 `generate_structured(IntentRoute)`，保留 L2 校验 |
| `infrastructure/llm/` | registry + deepseek provider（已含 `planning`/`memory`/`writing.reflection` prompt 目录） | + `structured.py` 实现模块；`DeepSeekLLMAdapter` 增加 `generate_structured` 方法；registry 按 model profile 提供 `ChatOpenAI` 实例/参数 |
| `prompts/` | planning/memory/writing.reflection 等 | + `outline/` 提示词目录 |
| `application/` | workflow_service 等 | + 大纲生成逻辑（Content Writer 子能力） |
| `api/routes/` | 现有路由 | + outline 端点 |
| `ai_operations` | 已有表 | operation_type 增加 `outline`，model_parameters 记录降级；观点/大纲快照存 `input_metadata` |
| 前端 | 编辑器 | + 大纲生成/预览卡片 |
