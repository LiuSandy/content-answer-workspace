# Automatic Creation Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在每次 AI 创作中自动执行最多三轮“生成—评审—定向重写”，最终只保存一个正式历史版本，并在前端展示评审进度和最终报告。

**Architecture:** 以 `QualityReport` 和 `review.quality_review` 作为唯一评审契约；新增无数据库副作用的创作评审编排器，保留每轮内部草稿并选择最终内容。生成链路先流式产生临时草稿，评审闭环结束后再由 WriterService 一次性创建正式版本，同时把全部评审元数据关联到同一个 `AIOperation`。

**Tech Stack:** Python 3.11+、FastAPI、Pydantic v2、SQLAlchemy async、DeepSeek OpenAI-compatible client、React 19、TypeScript、TanStack Query、SSE、pytest、bun test。

## Global Constraints

- 质量阈值固定为 `75`，评分统一为 `0..100` 整数。
- 首次生成计为第 1 轮，最多执行 `3` 轮。
- 三轮均未达标时选择综合评分最高的草稿；同分选择轮次更晚的草稿。
- 内部草稿和自动重写不得创建 `AnswerVersion`，也不得使用 `INLINE_REFINEMENT`。
- 每次用户触发的完整创作流程只能新增一个正式历史版本。
- `document.completed` 和 `run.completed` 只能在评审结束且正式版本保存成功后发送。
- 自动评审提示词必须接收原始问题、风格、目标字数、轮次和上一轮评审。
- `passed` 必须由系统计算，不能接受模型输出值。
- 不增加第三方依赖；不新增数据库迁移。
- 保留现有手动保存、用户重新创作、恢复版本和局部精修的版本语义。

---

## File Map

| 文件 | 职责 |
|---|---|
| `app/domain/dto.py` | 统一的 0～100 评审结构化输出模型 |
| `prompts/review/quality_review.yml` | 唯一评审提示词及完整创作上下文变量 |
| `app/application/quality_service.py` | 调用结构化 LLM 评审并查询最终创作报告 |
| `app/application/workflows/creation_review.py` | 无数据库副作用的最多三轮评审编排器 |
| `app/application/writer_service.py` | 暂缓生成版本、最终一次性落库、完成 AIOperation |
| `app/workflows/answer_generation.py` | 把首次生成切换为临时草稿模式 |
| `app/api/routes/documents.py` | 编排生成、评审、最终持久化与 SSE 事件顺序 |
| `app/persistence/models/quality_scores.py` | 更新 0～100 评分语义说明；结构不变 |
| `frontend/src/features/chat/creation-review-lifecycle.ts` | SSE 评审进度的纯状态转换 |
| `frontend/src/features/chat/editor-panel.tsx` | 展示创作进度、刷新最终内容与评审查询 |
| `frontend/src/features/chat/quality-review-api.ts` | 最终评审报告的只读 DTO/API |
| `frontend/src/features/chat/quality-review-dialog.tsx` | 只读展示最终报告和内部轮次 |

---

### Task 1: 统一评审模型与提示词

**Files:**
- Modify: `app/domain/dto.py`
- Modify: `prompts/review/quality_review.yml`
- Modify: `app/application/quality_service.py`
- Test: `tests/test_quality_review.py`

**Interfaces:**
- Produces: `ReviewContext`、`evaluate_content(content, context) -> QualityReport`
- Produces: `QualityReport.rewrite_instruction: str | None`
- Consumes: 现有 `DeepSeekLLMAdapter.generate_structured()` 和 `prompt_registry`

- [ ] **Step 1: 为完整上下文和统一输出写失败测试**

在 `tests/test_quality_review.py` 增加：

```python
@pytest.mark.asyncio
async def test_evaluate_content_passes_creation_context(monkeypatch):
    expected = _sample_report().model_copy(
        update={"overall_score": 68, "rewrite_instruction": "补充第二段数据"}
    )
    fake = _FakeLLM(
        StructuredResult(value=expected, method_used="json_schema", attempts=1)
    )
    monkeypatch.setattr("app.application.quality_service._get_llm", lambda: fake)

    report = await evaluate_content(
        "当前草稿",
        ReviewContext(
            question="原始问题",
            style_rules="专业、简洁",
            target_word_count=1000,
            iteration=2,
            previous_review={"overallScore": 68},
        ),
    )

    assert report.overall_score == 68
    assert report.rewrite_instruction == "补充第二段数据"
    rendered_user = fake.calls[0][1]
    assert "原始问题" in rendered_user
    assert "专业、简洁" in rendered_user
    assert "1000" in rendered_user
    assert "2/3" in rendered_user
    assert "68" in rendered_user
```

再增加模型契约测试，确认模型不提供 `passed` 字段：

```python
def test_quality_report_uses_system_computed_pass_status():
    report = _sample_report().model_copy(
        update={"overall_score": 68, "rewrite_instruction": None}
    )
    assert "passed" not in report.model_dump()
    assert report.overall_score == 68
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `uv run pytest tests/test_quality_review.py::test_evaluate_content_passes_creation_context tests/test_quality_review.py::test_quality_report_uses_system_computed_pass_status -v`

Expected: FAIL，原因是 `ReviewContext`、`evaluate_content` 或 `rewrite_instruction` 尚不存在。

- [ ] **Step 3: 扩展统一 Pydantic 契约**

在 `QualityReport` 中保留现有字段，并增加：

```python
rewrite_instruction: str | None = None
```

不要增加 `passed`。`quality_suggestions` 为兼容旧报告保留，但自动闭环不得读取它。

- [ ] **Step 4: 更新唯一评审提示词**

把 `prompts/review/quality_review.yml` 的变量改为：

```yaml
variables:
  required:
    - question
    - content
    - style_rules
    - target_word_count
    - iteration
    - previous_review
  optional: []
```

输出 JSON 必须包含 `overall_score`、`dimension_scores`、`issues`、`suggestions`、`rewrite_instruction` 和 `summary`。提示词明确：未达到 75 时重写指令必填、不能因篇幅更长加分、只评审不直接重写、保留正确内容并只修正具体缺陷。

- [ ] **Step 5: 实现无持久化副作用的评审入口**

在 `app/application/quality_service.py` 增加：

```python
@dataclass(frozen=True)
class ReviewContext:
    question: str
    style_rules: str | None
    target_word_count: int
    iteration: int
    previous_review: dict[str, Any] | None = None


async def evaluate_content(content: str, context: ReviewContext) -> QualityReport:
    rendered = prompt_registry.render(
        QUALITY_REVIEW_PROMPT,
        question=context.question,
        content=content,
        style_rules=context.style_rules or "无额外风格要求",
        target_word_count=context.target_word_count,
        iteration=f"{context.iteration}/3",
        previous_review=json.dumps(
            context.previous_review or {}, ensure_ascii=False
        ),
    )
    messages = rendered.to_llm_request().messages
    result = await _get_llm().generate_structured(
        schema=QualityReport,
        system_prompt=messages[0].content,
        user_prompt=messages[1].content,
    )
    if result.value is None:
        raise LLMOutputError(
            result.degradation_reason or "质检结构化输出失败，请重试"
        )
    return result.value
```

让现有 `QualityService.review()` 使用该入口，并从 `SourceItem.title` 补齐问题；兼容调用使用 `style_rules=None`、`target_word_count=1000`、`iteration=1`。

- [ ] **Step 6: 运行评审测试**

Run: `uv run pytest tests/test_quality_review.py -q`

Expected: PASS。

- [ ] **Step 7: 提交**

```bash
git add app/domain/dto.py prompts/review/quality_review.yml app/application/quality_service.py tests/test_quality_review.py
git commit -m "review: unify creation quality contract"
```

---

### Task 2: 实现三轮内部评审编排器

**Files:**
- Create: `app/application/workflows/creation_review.py`
- Create: `tests/test_creation_review_loop.py`

**Interfaces:**
- Consumes: `ReviewContext`、`QualityReport`
- Produces: `run_creation_review(initial_content, context, evaluate, rewrite) -> AsyncIterator[CreationReviewEvent]`
- Produces: `CreationReviewOutcome(final_content, final_report, iterations, passed, selected_iteration, rounds, review_failed)`

- [ ] **Step 1: 写四种核心路径的失败测试**

创建 `tests/test_creation_review_loop.py`，覆盖：首轮达标、第二轮达标、三轮未达标选择最高分、评审结构化失败保留当前草稿。

关键断言：

```python
def report(score: int, instruction: str = "继续定向修改") -> QualityReport:
    return QualityReport(
        overall_score=score,
        dimension_scores={
            "relevance": score,
            "information_density": score,
            "readability": score,
            "logic_coherence": score,
            "word_count_compliance": score,
        },
        issues=[],
        suggestions=[],
        rewrite_instruction=None if score >= 75 else instruction,
        summary="测试评审",
    )


@pytest.mark.asyncio
async def test_three_failed_rounds_choose_highest_score_and_latest_on_tie():
    reports = iter([report(70), report(72), report(72)])

    async def evaluate(content, context):
        return next(reports)

    async def rewrite(content, instruction):
        return {"draft-1": "draft-2", "draft-2": "draft-3"}[content]

    events = [event async for event in run_creation_review(
        initial_content="draft-1",
        context=ReviewContext("问题", None, 1000, 1),
        evaluate=evaluate,
        rewrite=rewrite,
    )]
    outcome = events[-1].outcome

    assert outcome is not None
    assert outcome.iterations == 3
    assert outcome.passed is False
    assert outcome.selected_iteration == 3
    assert outcome.final_content == "draft-3"
```

首轮达标必须断言 `rewrite` 未调用；第二轮达标必须断言事件顺序为 `review.started`、`review.completed`、`rewrite.started`、`review.started`、`review.completed`；评审失败必须断言 `review_failed is True` 且没有伪造分数。

- [ ] **Step 2: 运行测试并确认失败**

Run: `uv run pytest tests/test_creation_review_loop.py -v`

Expected: FAIL，模块尚不存在。

- [ ] **Step 3: 定义编排数据结构**

实现以下公开类型：

```python
QUALITY_THRESHOLD = 75
MAX_CREATION_ROUNDS = 3

ReviewFn = Callable[[str, ReviewContext], Awaitable[QualityReport]]
RewriteFn = Callable[[str, str], Awaitable[str]]

@dataclass(frozen=True)
class CreationReviewRound:
    iteration: int
    content: str
    report: QualityReport

@dataclass(frozen=True)
class CreationReviewOutcome:
    final_content: str
    final_report: QualityReport | None
    iterations: int
    passed: bool
    selected_iteration: int
    rounds: Sequence[CreationReviewRound]
    review_failed: bool = False
    error_message: str | None = None

@dataclass(frozen=True)
class CreationReviewEvent:
    name: str
    data: dict[str, Any]
    outcome: CreationReviewOutcome | None = None
```

- [ ] **Step 4: 实现最多三轮的 async generator**

每轮按以下顺序执行：

```python
round_context = dataclasses.replace(
    context,
    iteration=iteration,
    previous_review=(
        rounds[-1].report.model_dump(mode="json", by_alias=True)
        if rounds
        else None
    ),
)
yield CreationReviewEvent("review.started", {
    "iteration": iteration,
    "maxIterations": MAX_CREATION_ROUNDS,
})
report = await evaluate(current_content, round_context)
passed = report.overall_score >= QUALITY_THRESHOLD
rounds.append(CreationReviewRound(iteration, current_content, report))
yield CreationReviewEvent("review.completed", {
    "iteration": iteration,
    "overallScore": report.overall_score,
    "passed": passed,
})
```

未达标且可继续时，校验 `rewrite_instruction` 非空，发送 `rewrite.started` 后调用 `rewrite(current_content, instruction)`。结束时按 `(overall_score, iteration)` 取最大值，并通过最后一个仅供后端消费的 `creation_review.outcome` 事件返回 `outcome`。

只捕获 `LLMOutputError` 作为评审失败；不能吞掉 `asyncio.CancelledError` 或未知编程错误。

- [ ] **Step 5: 运行测试**

Run: `uv run pytest tests/test_creation_review_loop.py -q`

Expected: PASS。

- [ ] **Step 6: 提交**

```bash
git add app/application/workflows/creation_review.py tests/test_creation_review_loop.py
git commit -m "review: add bounded creation review loop"
```

---

### Task 3: 让首次生成延迟创建正式版本

**Files:**
- Modify: `app/application/writer_service.py`
- Modify: `app/workflows/answer_generation.py`
- Test: `tests/test_writer_service.py`
- Test: `tests/test_answer_generation_lock_retry.py`

**Interfaces:**
- Produces: `WriterRunCapture`
- Produces: `finalize_deferred_writer_run(session, capture, final_content, expected_lock_version, output_metadata) -> AnswerVersion`
- Consumes: 现有 `run_writer_stream()` 和 `DocumentService.create_version()`

- [ ] **Step 1: 写“生成期间零版本、完成后一个版本”的失败测试**

在 `tests/test_writer_service.py` 增加：

```python
async def _version_count(session: AsyncSession, document_id: uuid.UUID) -> int:
    rows = (
        await session.execute(
            select(AnswerVersion).where(AnswerVersion.document_id == document_id)
        )
    ).scalars().all()
    return len(rows)


@pytest.mark.asyncio
async def test_deferred_writer_creates_exactly_one_final_version(monkeypatch):
    db, engine = await _make_db()
    doc_id, _ = await _setup_doc(db)
    _mock_provider(monkeypatch, content="internal draft")
    capture = WriterRunCapture()

    async with db() as session:
        parts = [part async for part in run_writer_stream(
            session,
            "generate",
            doc_id,
            _fake_rendered(),
            1,
            defer_version=True,
            capture=capture,
        )]
        assert parts == ["internal draft"]
        assert capture.content == "internal draft"
        assert await _version_count(session, doc_id) == 0

        version = await finalize_deferred_writer_run(
            session=session,
            capture=capture,
            final_content="reviewed final",
            expected_lock_version=1,
            output_metadata={"creationReview": {"iterations": 3}},
        )
        assert version.content == "reviewed final"
        assert await _version_count(session, doc_id) == 1

    await engine.dispose()
```

再断言 AIOperation 在暂缓阶段为 `running`，最终为 `completed`，且 `result_version_id` 指向唯一版本。

- [ ] **Step 2: 运行测试并确认失败**

Run: `uv run pytest tests/test_writer_service.py::test_deferred_writer_creates_exactly_one_final_version -v`

Expected: FAIL，暂缓接口尚不存在。

- [ ] **Step 3: 增加 WriterRunCapture**

在 `writer_service.py` 定义：

```python
@dataclass
class WriterRunCapture:
    operation_id: uuid.UUID | None = None
    document_id: uuid.UUID | None = None
    content: str = ""
    prompt_id: str | None = None
    prompt_version: str = "1.0.0"
    provider: str | None = None
    model: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0
```

- [ ] **Step 4: 给 run_writer_stream 增加显式暂缓参数**

签名增加：

```python
defer_version: bool = False,
capture: WriterRunCapture | None = None,
```

当 `defer_version=True` 时要求 `capture` 非空；生成结束只填充 capture，保留 AIOperation 为 `running`，不得调用 `create_version()`。`refine` 和 `full_rewrite` 默认值不变，继续沿用现有落库行为。

- [ ] **Step 5: 实现最终一次性落库**

```python
async def finalize_deferred_writer_run(
    session: AsyncSession,
    capture: WriterRunCapture,
    final_content: str,
    expected_lock_version: int,
    output_metadata: dict[str, Any],
) -> AnswerVersion:
    operation = await session.get(AIOperation, capture.operation_id)
    version = await DocumentService(session).create_version(
        document_id=capture.document_id,
        content=final_content,
        version_type=_VT_INIT,
        expected_lock_version=expected_lock_version,
        prompt_id=capture.prompt_id,
        prompt_version=capture.prompt_version,
        provider=capture.provider,
        model=capture.model,
    )
    operation.status = "completed"
    operation.result_version_id = version.id
    operation.output_metadata = output_metadata
    operation.input_tokens = capture.input_tokens
    operation.output_tokens = capture.output_tokens
    operation.latency_ms = capture.latency_ms
    await session.commit()
    return version
```

保留现有锁冲突重试行为，但重试仍只能创建一个版本。

- [ ] **Step 6: 切换首次生成工作流**

给 `generate_answer_workflow()` 增加必填 `capture: WriterRunCapture`，并把现有参数原样传给 `run_writer_stream`，同时设置 `defer_version=True, capture=capture`。不要改局部精修和全文重写工作流。

- [ ] **Step 7: 运行写作与锁测试**

Run: `uv run pytest tests/test_writer_service.py tests/test_answer_generation_lock_retry.py -q`

Expected: PASS。

- [ ] **Step 8: 提交**

```bash
git add app/application/writer_service.py app/workflows/answer_generation.py tests/test_writer_service.py tests/test_answer_generation_lock_retry.py
git commit -m "writer: defer initial version persistence"
```

---

### Task 4: 接入生成 API、SSE 顺序和评审持久化

**Files:**
- Modify: `app/api/routes/documents.py`
- Modify: `app/application/quality_service.py`
- Modify: `app/persistence/models/quality_scores.py`
- Create: `tests/test_document_generation_review.py`
- Modify: `tests/test_quality_score_model.py`

**Interfaces:**
- Consumes: `run_creation_review()`、`WriterRunCapture`、`finalize_deferred_writer_run()`、`evaluate_content()`
- Produces: `persist_creation_review(session, document_id, version_id, operation_id, outcome)`
- Produces SSE: `review.started`、`review.completed`、`rewrite.started`、`document.completed`、`run.completed`

- [ ] **Step 1: 写 API 事件顺序和单版本失败测试**

创建 `tests/test_document_generation_review.py`，mock 初始生成、评审与重写，使用测试客户端消费 SSE。至少覆盖：

```python
assert event_names == [
    "run.started",
    "document.delta",
    "review.started",
    "review.completed",
    "rewrite.started",
    "review.started",
    "review.completed",
    "document.completed",
    "run.completed",
]
assert completed_payload["currentContent"] == "final draft"
async with db() as verify_session:
    versions = (
        await verify_session.execute(
            select(AnswerVersion).where(AnswerVersion.document_id == document_id)
        )
    ).scalars().all()
assert len(versions) == 1
assert versions[0].content == "final draft"
```

再增加三轮未达标测试，断言最终版本等于最高分轮次而不是最后一轮；增加评审失败测试，断言仍保存当前草稿一个版本，完成载荷中的 `reviewStatus` 为 `failed`。

- [ ] **Step 2: 运行测试并确认失败**

Run: `uv run pytest tests/test_document_generation_review.py -v`

Expected: FAIL，当前接口在评审前创建版本并提前发送完成事件。

- [ ] **Step 3: 重排 generate_answer_stream**

将生成端点严格改为：

```python
capture = WriterRunCapture()
async for chunk in generate_answer_workflow(
    session=session,
    source_item_id=source_item_id,
    document_id=doc_id,
    platform=req.platform or platform,
    title=title,
    content=content,
    expected_lock_version=req.expected_lock_version,
    style_rules=req.style_rules,
    word_count=req.word_count,
    instruction=req.instruction,
    capture=capture,
):
    yield sse_named_event("document.delta", {"delta": chunk})

outcome = None
async for review_event in run_creation_review(
    initial_content=capture.content,
    context=ReviewContext(
        question=title,
        style_rules=req.style_rules,
        target_word_count=req.word_count,
        iteration=1,
    ),
    evaluate=evaluate_content,
    rewrite=_rewrite_creation_draft,
):
    if review_event.outcome is not None:
        outcome = review_event.outcome
    else:
        yield sse_named_event(review_event.name, review_event.data)

if outcome is None:
    raise RuntimeError("creation review completed without an outcome")
if capture.operation_id is None:
    raise RuntimeError("deferred writer run has no operation id")

version = await finalize_deferred_writer_run(
    session,
    capture,
    outcome.final_content,
    req.expected_lock_version,
    output_metadata=_creation_review_metadata(outcome),
)
await persist_creation_review(
    session,
    document_id=doc_id,
    version_id=version.id,
    operation_id=capture.operation_id,
    outcome=outcome,
)
state = await DocumentService(session).get_document_state(doc_id)
yield sse_named_event("document.completed", {
    **state.model_dump(mode="json", by_alias=True),
    "creationReview": _final_review_summary(outcome),
})
yield sse_named_event("run.completed", {"runId": run_id})
```

删除当前 `document.completed`/`run.completed` 之后的 `reflect_and_refine` 块。

- [ ] **Step 4: 实现定向重写适配器**

`_rewrite_creation_draft(content, instruction)` 调用 `DeepSeekLLMAdapter.refine(instruction="保留已正确内容，只修复评审指出的问题。\n" + instruction, current_answer=content)`，不得创建版本。

- [ ] **Step 5: 保存同一创作操作的评审记录**

在 `quality_service.py` 增加：

```python
async def persist_creation_review(
    session: AsyncSession,
    *,
    document_id: uuid.UUID,
    version_id: uuid.UUID,
    operation_id: uuid.UUID,
    outcome: CreationReviewOutcome,
) -> None:
    for round_result in outcome.rounds:
        session.add(QualityScoreModel(
            ai_operation_id=operation_id,
            document_id=document_id,
            version_id=version_id,
            iteration=round_result.iteration,
            overall_score=round_result.report.overall_score,
            dimensions=round_result.report.dimension_scores,
            weakness_summary=round_result.report.summary,
            refinement_instruction=round_result.report.rewrite_instruction,
            converged="true" if round_result.report.overall_score >= 75 else "false",
        ))
    await session.commit()
```

完整 `issues`、`suggestions`、每轮内容选择结果存入生成 AIOperation 的 `output_metadata.creationReview`；`quality_scores` 只保存可索引的分数摘要。不得保存内部草稿为 AnswerVersion。

`_creation_review_metadata(outcome)` 返回以下确定结构，`_final_review_summary(outcome)` 返回其中的 `creationReview` 值：

```python
def _creation_review_metadata(outcome: CreationReviewOutcome) -> dict[str, Any]:
    report = outcome.final_report
    return {
        "creationReview": {
            "reviewStatus": "failed" if outcome.review_failed else "completed",
            "iterations": outcome.iterations,
            "passed": outcome.passed,
            "selectedIteration": outcome.selected_iteration,
            "finalReport": (
                report.model_dump(mode="json", by_alias=True) if report else None
            ),
            "rounds": [
                {
                    "iteration": row.iteration,
                    "overallScore": row.report.overall_score,
                    "passed": row.report.overall_score >= 75,
                }
                for row in outcome.rounds
            ],
            "errorMessage": outcome.error_message,
        }
    }


def _final_review_summary(outcome: CreationReviewOutcome) -> dict[str, Any]:
    return _creation_review_metadata(outcome)["creationReview"]
```

- [ ] **Step 6: 更新 QualityScore 语义与测试**

只修改模型注释和测试期望为 0～100；表字段仍为 Float，不创建迁移。测试断言 `overall_score=82` 可往返、`ai_operation_id` 和最终 `version_id` 相同。

- [ ] **Step 7: 运行后端集成测试**

Run: `uv run pytest tests/test_document_generation_review.py tests/test_quality_score_model.py tests/test_writer_service.py -q`

Expected: PASS。

- [ ] **Step 8: 提交**

```bash
git add app/api/routes/documents.py app/application/quality_service.py app/persistence/models/quality_scores.py tests/test_document_generation_review.py tests/test_quality_score_model.py
git commit -m "api: complete review before saving generation"
```

---

### Task 5: 让评审查询返回当前正式版本的自动报告

**Files:**
- Modify: `app/application/quality_service.py`
- Modify: `app/api/routes/documents.py`
- Modify: `tests/test_quality_review.py`

**Interfaces:**
- Produces: `QualityService.list_creation_reviews(document_id) -> list[dict[str, Any]]`
- Consumes: `AIOperation.output_metadata.creationReview` 和 `AnswerDocument.current_version_id`

- [ ] **Step 1: 写只返回正式版本关联报告的失败测试**

增加测试：同一文档存在两次生成操作，当前版本指向第二次；查询结果按时间倒序，第一条必须是当前版本报告，包含：

```python
assert row == {
    "reportId": str(operation.id),
    "sourceVersionId": str(current_version.id),
    "overallScore": 82,
    "dimensionScores": {
        "relevance": 86,
        "informationDensity": 80,
        "readability": 84,
        "logicCoherence": 81,
        "wordCountCompliance": 90,
    },
    "issues": [{"severity": "minor", "description": "第二段论据较少"}],
    "suggestions": ["为第二段补充一个具体案例"],
    "summary": "文章已回答核心问题，论据可以进一步加强。",
    "rewriteInstruction": None,
    "iterations": 2,
    "passed": True,
    "selectedIteration": 2,
    "reviewStatus": "completed",
    "rounds": [
        {"iteration": 1, "overallScore": 68, "passed": False},
        {"iteration": 2, "overallScore": 82, "passed": True},
    ],
    "createdAt": operation.created_at.isoformat(),
}
```

评审失败记录必须返回 `reviewStatus="failed"`、`overallScore=None`，不能伪造零分。

- [ ] **Step 2: 运行测试并确认失败**

Run: `uv run pytest tests/test_quality_review.py -k "creation_reviews" -v`

Expected: FAIL，现有查询只读取 `operation_type=quality_review`。

- [ ] **Step 3: 实现生成操作报告映射**

查询 `operation_type="generate"`、`status="completed"`、`result_version_id IS NOT NULL` 的操作，读取 `output_metadata.creationReview`，按 `created_at DESC` 返回。保留旧 `quality_review` 数据的只读兼容映射，但新自动流程不再创建 `quality_review` 操作。

- [ ] **Step 4: 让 REST 查询使用新方法**

`GET /api/documents/{document_id}/quality/reviews` 调用 `list_creation_reviews()`。保持响应包装 `{"ok": true, "data": rows}`，其中 `rows` 是服务返回的报告列表。

- [ ] **Step 5: 运行质量 API 测试**

Run: `uv run pytest tests/test_quality_review.py -q`

Expected: PASS。

- [ ] **Step 6: 提交**

```bash
git add app/application/quality_service.py app/api/routes/documents.py tests/test_quality_review.py
git commit -m "review: expose automatic creation reports"
```

---

### Task 6: 更新前端生成进度与只读评审界面

**Files:**
- Create: `frontend/src/features/chat/creation-review-lifecycle.ts`
- Create: `frontend/src/features/chat/creation-review-lifecycle.test.ts`
- Modify: `frontend/src/features/chat/editor-panel.tsx`
- Modify: `frontend/src/features/chat/quality-review-api.ts`
- Modify: `frontend/src/features/chat/quality-review-dialog.tsx`
- Delete: `frontend/src/features/chat/quality-score-panel.tsx`

**Interfaces:**
- Consumes SSE: `review.started`、`review.completed`、`rewrite.started`、`document.completed`、`run.completed`
- Produces: `CreationProgressState` 和 `reduceCreationProgress()`
- Consumes REST: `GET /api/documents/{documentId}/quality/reviews`

- [ ] **Step 1: 写进度状态转换失败测试**

创建 `creation-review-lifecycle.test.ts`：

```typescript
test("maps review and rewrite events to user-facing progress", () => {
  let state = initialCreationProgress;
  state = reduceCreationProgress(state, "review.started", { iteration: 1, maxIterations: 3 });
  expect(state.label).toBe("正在进行第 1/3 轮评审");

  state = reduceCreationProgress(state, "review.completed", { iteration: 1, overallScore: 68, passed: false });
  state = reduceCreationProgress(state, "rewrite.started", { iteration: 2, maxIterations: 3 });
  expect(state.label).toBe("未达到质量阈值，正在根据建议优化");

  state = reduceCreationProgress(state, "run.completed", {});
  expect(state.label).toBe("创作完成");
  expect(state.running).toBe(false);
});
```

再测试 `document.completed` 不会提前把 `running` 设为 false，只有 `run.completed` 才结束。

- [ ] **Step 2: 运行测试并确认失败**

Run: `cd frontend && bun test src/features/chat/creation-review-lifecycle.test.ts`

Expected: FAIL，模块不存在。

- [ ] **Step 3: 实现纯状态转换**

```typescript
export type CreationProgressState = {
  running: boolean;
  label: string;
  iteration: number;
  maxIterations: number;
  score: number | null;
};

export function reduceCreationProgress(
  state: CreationProgressState,
  event: string,
  data: Record<string, unknown>,
): CreationProgressState {
  // 对 run.started/review.started/review.completed/rewrite.started/
  // document.completed/run.completed/run.failed 做穷举转换
}
```

未知事件原样返回 state；`run.failed` 结束运行但不显示“创作完成”。

- [ ] **Step 4: 接入编辑器 SSE**

`handleGenerateAnswer()` 开始时显示“正在生成内容”。收到评审事件时更新状态文案；收到 `document.completed` 时用 `currentContent` 覆盖编辑器并刷新：

```typescript
queryClient.invalidateQueries({ queryKey: ["versions", data.documentId] });
queryClient.invalidateQueries({ queryKey: ["quality-reviews", data.documentId] });
```

在收到 `run.completed` 前保持 `isGenerating=true`。历史版本只因最终 `document.completed` 刷新一次。

- [ ] **Step 5: 更新只读报告 DTO**

```typescript
export interface QualityReviewRecordDTO {
  reportId: string;
  sourceVersionId?: string | null;
  overallScore?: number | null;
  dimensionScores?: Record<string, number>;
  issues?: Array<{ severity?: "major" | "minor"; description: string }>;
  suggestions?: string[];
  rewriteInstruction?: string | null;
  summary?: string;
  iterations: number;
  passed: boolean;
  selectedIteration: number;
  reviewStatus: "completed" | "failed";
  rounds?: Array<{ iteration: number; overallScore: number; passed: boolean }>;
  createdAt?: string | null;
}
```

删除前端的 `runQualityReview()`、`adoptQualitySuggestion()` 及相关请求 DTO；保留 `listQualityReviews()`。

- [ ] **Step 6: 把评审弹窗改为只读最终报告**

删除“开始质检”“重新质检”“采纳”按钮和 mutations。弹窗展示最新记录：综合分、五维分、达标状态、问题、建议、轮数、选中轮次。三轮未达标时显示：

```text
已完成 3 轮评审，当前为三轮中评分最高的结果
```

评审失败时显示“内容已生成，但自动评审失败”，不得显示 0 分。

- [ ] **Step 7: 修改入口文字并移除重复评分面板**

把编辑器顶部按钮从“评审”改为“查看评审”，Tooltip 改为“查看本次创作的自动评审结果”。删除 `QualityScorePanel` 的 import、渲染和文件，内部轮次统一在评审弹窗展示。

- [ ] **Step 8: 运行前端验证**

Run: `cd frontend && bun test src/features/chat/creation-review-lifecycle.test.ts`

Expected: PASS。

Run: `cd frontend && bun run typecheck`

Expected: PASS。

- [ ] **Step 9: 提交**

```bash
git add frontend/src/features/chat/creation-review-lifecycle.ts frontend/src/features/chat/creation-review-lifecycle.test.ts frontend/src/features/chat/editor-panel.tsx frontend/src/features/chat/quality-review-api.ts frontend/src/features/chat/quality-review-dialog.tsx frontend/src/features/chat/quality-score-panel.tsx
git commit -m "frontend: show automatic creation reviews"
```

---

### Task 7: 删除旧反思链路并完成回归验证

**Files:**
- Delete: `app/application/workflows/reflection.py`
- Delete: `app/application/workflows/reflect_refine.py`
- Delete: `prompts/writing/reflection.yml`
- Delete: `tests/test_reflection_loop.py`
- Delete: `tests/test_refinement_loop_integration.py`
- Modify: `app/api/routes/documents.py`
- Modify: `tests/test_new_architecture.py`

**Interfaces:**
- Consumes: Task 1～6 的统一自动评审链路
- Produces: 仓库中不再存在 `writing.reflection` 或 `reflect_and_refine` 运行时引用

- [ ] **Step 1: 写遗留引用守卫测试**

在 `tests/test_new_architecture.py` 增加：

```python
def test_legacy_reflection_prompt_and_workflow_are_removed():
    root = Path(__file__).parents[1]
    runtime_files = list((root / "app").rglob("*.py"))
    runtime_text = "\n".join(path.read_text() for path in runtime_files)
    assert "writing.reflection" not in runtime_text
    assert "reflect_and_refine" not in runtime_text
    assert not (root / "prompts/writing/reflection.yml").exists()
```

- [ ] **Step 2: 运行守卫测试并确认失败**

Run: `uv run pytest tests/test_new_architecture.py::test_legacy_reflection_prompt_and_workflow_are_removed -v`

Expected: FAIL，旧模块和提示词仍存在。

- [ ] **Step 3: 删除旧文件和全部运行时引用**

删除旧 0～1 评审模块、提示词和对应测试。确认 `documents.py` 中不存在生成完成后的非阻塞 reflection 块，也不存在 `reflection.completed` 事件。

- [ ] **Step 4: 运行后端相关测试**

Run: `uv run pytest tests/test_creation_review_loop.py tests/test_document_generation_review.py tests/test_quality_review.py tests/test_writer_service.py tests/test_quality_score_model.py tests/test_new_architecture.py -q`

Expected: PASS。

- [ ] **Step 5: 运行前端完整验证**

Run: `cd frontend && bun test`

Expected: PASS。

Run: `cd frontend && bun run typecheck && bun run build`

Expected: PASS。

- [ ] **Step 6: 运行后端完整测试并记录既有失败**

Run: `uv run pytest tests/ -q`

Expected: 新增和相关测试全部通过；若仍出现与本功能无关的既有失败，记录测试名和失败原因，不得把它们描述为本次通过。

- [ ] **Step 7: 检查版本与事件不变量**

Run: `rg -n "reflect_and_refine|writing\.reflection|reflection\.completed" app prompts frontend/src`

Expected: 无输出。

Run: `git diff --check`

Expected: 无输出。

- [ ] **Step 8: 提交**

```bash
git add app/application/workflows/reflection.py app/application/workflows/reflect_refine.py prompts/writing/reflection.yml tests/test_reflection_loop.py tests/test_refinement_loop_integration.py app/api/routes/documents.py tests/test_new_architecture.py
git commit -m "review: remove legacy reflection workflow"
```

---

## Final Acceptance Checklist

- [ ] 首轮达标只增加一个正式版本。
- [ ] 第二或第三轮达标仍只增加一个正式版本。
- [ ] 三轮未达标保存最高分草稿，同分选择更晚轮次。
- [ ] 自动内部重写不产生 `INLINE_REFINEMENT` 版本。
- [ ] 评审失败保存当前草稿一个版本，并显示明确失败状态。
- [ ] 完成事件严格晚于评审闭环和正式版本提交。
- [ ] 提示词包含原始问题、风格、字数、轮次和上一轮结果。
- [ ] 页面在运行期间显示实时评审进度。
- [ ] “查看评审”只读展示最终报告和内部轮次。
- [ ] 历史版本列表不显示内部草稿。
- [ ] 后端相关测试、前端测试、类型检查和构建通过。
