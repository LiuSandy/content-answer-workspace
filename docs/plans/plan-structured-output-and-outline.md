# [实现计划] 结构化输出与内容大纲

> **文档状态**：已制定 (Drafting) - 等待用户评审确认
> **关联 Spec**：[docs/specs/feature-outlines-structured-generation.md](../specs/feature-outlines-structured-generation.md)
> **跨 Spec 依赖**：本计划为其他两份 spec 的**技术底座**——`StructuredOutputClient` 被
> agent-platform 的 reviewer/analyst 与记忆系统的 extractor/summary 共用，应最先落地。

---

## 1. 拟修改与新增的文件列表

### 1.1 统一基础设施
* **[NEW] `app/infrastructure/llm/structured.py`**：`StructuredOutputClient.generate(schema, system, user, retries)`——json_schema → JSON mode → 通用解析三级降级，降级原因写入参数
* **[MODIFY] `app/infrastructure/llm/registry.py`**：按 model profile **提供 LangChain `ChatOpenAI` 实例/参数**（与 chat_node 同体系，不另起裸 OpenAI client），并透传 provider 的 JSON mode 支持能力
* **[MODIFY] `app/infrastructure/llm/providers/deepseek.py`**：向 registry 透传 `response_format=json_object` 等 JSON mode 参数（`with_structured_output` 由 `ChatOpenAI` 原生承担）
* **[NEW] `tests/test_structured_output.py`**：三级降级链路、校验失败重试、降级可观测

### 1.2 意图路由替换（P0）
* **[MODIFY] `app/application/agent/nodes/route_intent.py`**
  * 移除 `route_intent.py:39-45` 手写 `json.loads` + try-except
  * LLM 分支改用 `StructuredOutputClient.generate(IntentRoute)`
  * 保留规则优先（URL 检测）分支
* **[NEW] `app/domain/dto.py`**：新增 `IntentRoute` schema

### 1.3 内容大纲生成（P1，业务重点）
* **[NEW] `app/application/outline_service.py`**：`OutlineService.generate_outline()`——组装 `ArticleOutline`、校验、返回给前端预览
* **[MODIFY] `app/api/routes/documents.py`**：新增 `POST /api/source-items/{id}/outline`（一次性返回供预览）
* **[MODIFY] `app/workflows/answer_generation.py`**：按大纲段落分段生成（大纲确认后调用）；生成前置**观点采集**（可选，viewpoint_notes 注入）
* **[NEW] `prompts/outline/answer_outline.yml`**：大纲生成 Few-shot 模板（含平台包/风格规则装配）
* **[MODIFY] `frontend/src/features/chat/editor-panel.tsx`**：「生成大纲」按钮 + 大纲预览卡片（钩子/段落/要点/收束）→ 确认后进入生成

### 1.4 其余场景接入（供跨 spec 消费）
* **[NEW] `app/domain/dto.py`**：`TopicEvaluation` / `QualityReport` / `MemoryExtraction` / `ConversationSummary` schema
* **接入点**（实现归各 spec 计划）：
  * 选题评估 → agent-platform plan Phase 2
  * 质检报告 → agent-platform plan Phase 1
  * 记忆提取/滚动摘要 → memory plan Phase 1 / Phase 0

### 1.5 遗留热榜
* **[MODIFY] `app/application/agent/graphs/analysis.py`**（agent-platform 删除前）：热榜选题**并入 `TopicEvaluation`** schema（选题评估共用），agent-platform 落地时随旧图一并删除

### 1.6 测试
* **[NEW] `tests/test_outline_service.py`**：大纲生成合法结构、平台装配、分段生成衔接
* **[NEW] `tests/test_structured_output.py`**：见 1.1
* **[MODIFY] `tests/test_prompt_composer.py`**：outline 模板装配回归

---

## 2. 详细执行步骤（TDD 流程）

### Phase 0：StructuredOutputClient + 意图路由替换
1. **Step 1 (TDD)**：写 `tests/test_structured_output.py`——json_schema 优先、失败降级 JSON mode、再失败降级通用解析、重试 1 次、降级可观测（失败测试先行）。
2. **Step 2**：实现 `infrastructure/llm/structured.py` + registry/provider 扩展。
3. **Step 3 (TDD)**：替换 `route_intent.py` 手写解析，写回归断言（合法 JSON、非法 JSON 不抛异常）。
4. **Step 4**：`uv run pytest tests/test_structured_output.py tests/test_chat_branching.py -v`——现有对话链路回归。

### Phase 1：内容大纲生成
5. **Step 5 (TDD)**：写 `tests/test_outline_service.py`——大纲结构合法、平台/风格装配、确认后分段生成衔接。
6. **Step 6**：`prompts/outline/answer_outline.yml` + `outline_service.py`。
7. **Step 7**：`POST /api/source-items/{id}/outline` 端点。
8. **Step 8**：前端大纲按钮 + 预览卡片 + 确认进入生成。
9. **Step 9**：端到端验证：选题 → 生成大纲 → 确认 → 分段生成 → 写 AnswerVersion。

### Phase 2：schema 就绪 + 跨 spec 接入
10. **Step 10**：补齐 `TopicEvaluation` / `QualityReport` / `MemoryExtraction` / `ConversationSummary` schema 定义与导出。
11. **Step 11**：将 `StructuredOutputClient` 注入 reviewer / analyst / extractor / summary 各消费方（随各 spec 计划落地时接线）。

---

## 3. 验证计划

### 自动化测试命令
```bash
uv run pytest tests/test_structured_output.py tests/test_outline_service.py tests/test_prompt_composer.py -v
cd frontend && bun run typecheck && bun run build
```

### 实际链路校验
1. 意图路由：对话/URL 粘贴均正确分流，无手写 JSON 解析残留
2. 构造非法 LLM 输出（mock）：走降级链路，请求不失败，`AIOperation.model_parameters.degraded` 有记录
3. 编辑器生成大纲 → 预览卡片 → 确认 → 按段落生成回答
4. 各消费方（质检/选题/记忆/摘要）输出均为合法 Pydantic 对象

### 里程碑验收（对应 spec §7）
- [ ] P0：`route_intent.py` 移除手写 JSON；降级不抛异常且可观测；SSE 链路回归
- [ ] P1：大纲生成/确认/分段生成全通；选题/质检输出 100% 合法
- [ ] P2：记忆提取/摘要 schema 就绪并接入消费方
