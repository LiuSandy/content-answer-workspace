# Long-term Memory Retrieval and Native HITL Implementation Plan

**Goal:** 完成长期记忆 Embedding 接线、pgvector cosine Top-K、HNSW 迁移验证、RAG 质量评测、专用 Cross-Encoder Reranker，以及聊天 Agent 的 LangGraph 原生 HITL 暂停恢复。

**Architecture:** 长期记忆复用知识库的 Embedding 端口和配置，以 PostgreSQL `vector(1536)` 作为唯一生产存储，通过 workspace/status 过滤后的 cosine Top-K 查询完成召回；检索质量由可重复运行的标注数据集和指标计算器约束，再将现有逐文档 LLM 重排替换成一次批量请求的专用 Rerank Provider。聊天中的约束冲突使用 LangGraph `interrupt()` 暂停，并使用相同 `thread_id` 与 `Command(resume=...)` 从 checkpoint 恢复。

**Tech Stack:** Python 3.11+、FastAPI、SQLAlchemy 2 Async、Alembic、PostgreSQL、pgvector、ParadeDB、OpenAI-compatible Embedding API、专用 Rerank API、LangGraph、pytest。

## Global Constraints

- 按 Task 1 → Task 8 顺序实施；Task 6 和 Task 7 可在 Task 5 基线完成后单独交付。
- 每个 Task 必须先增加失败测试，再实现最小改动，最后运行相关回归。
- 当前数据库已位于 `20260812_outline_versions (head)`；不得修改已部署 revision 的语义来伪造一次“重新迁移”。数据库结构修复必须新增迁移。
- 当前 `user_memories.embedding` 已是 `vector`，并存在 `ix_user_memories_embedding_hnsw`；Task 3 的目标是让全新数据库迁移、现有数据库审计和查询计划验证都可靠，而不是重复创建同名结构。
- 生产代码不得使用 Mock Embedding 或 Mock Reranker；配置缺失和调用失败必须可观测并走明确降级路径。
- Embedding 维度与数据库列固定为 1536；维度不匹配必须拒绝写入，不能截断或补零。
- 长期记忆检索只允许返回同一 `workspace_id` 且 `status = active` 的记录。
- strict RAG 模式下 Reranker 不可用或证据未达阈值时继续拒答；不得用 RRF 分数冒充 Rerank 分数。
- HITL 第一阶段只迁移 Chat Agent 的工具约束冲突选择；`task_plans` 和独立 `multi-agent` API 的中断控制不在本计划范围。
- `interrupt()` 前不得发生不可重复的副作用；恢复时节点会从开头重新执行。
- 不在日志、Trace、测试夹具或计划文件中写入 API Key、Cookie 或用户私密内容。
- 每个功能边界独立 commit；不在本计划中推送远程仓库。

## Verified Baseline

计划制定时已确认：

- `app/application/memory_service.py::_get_embedding_provider()` 导入不存在的 `EmbeddingProviderPort` 和 `KnowledgeEmbeddingProvider`，而实际实现为 `get_embedding_provider()` 与 `OpenAIEmbeddingProvider`。
- `retrieve_memories()` 当前使用 `ILIKE` 与激活次数排序，没有生成查询向量，也没有 cosine Top-K。
- 本地数据库 `user_memories.embedding` 为 pgvector `vector` 类型，HNSW 索引使用 `vector_cosine_ops`。
- `tests/test_memory_pipeline.py` 的离线迁移测试在 `CREATE EXTENSION` 后中断，当前基线为 2 failed、33 passed。
- `docs/evaluations/private-knowledge-rag.jsonl` 只有 3 条不完整样本。
- `tests/knowledge/test_retrieval_quality.py` 将指标直接写死为 `1.0`，没有执行检索或指标计算。
- `LLMRerankerProvider` 对每个候选分别调用 Chat Completions。
- Chat HITL 当前结束图运行，再通过 `/choices` 构造新输入重新运行；尚未使用 `interrupt()` 和 `Command(resume=...)`。

## Delivery Map

| Task | 交付物 | 前置依赖 | 建议 Commit |
|---|---|---|---|
| 1 | 统一 Embedding Provider 接线与配置 | 无 | `fix(memory): wire the embedding provider` |
| 2 | 长期记忆 cosine Top-K | Task 1 | `feat(memory): retrieve memories with cosine top-k` |
| 3 | pgvector/HNSW 迁移与数据库验证 | Task 2 | `fix(db): verify memory vector migration and hnsw index` |
| 4 | 指标计算器与标注数据契约 | Task 2 | `test(rag): add retrieval metric contracts` |
| 5 | 可执行检索质量评测集 | Task 3、4 | `test(rag): establish retrieval quality baseline` |
| 6 | 专用 Cross-Encoder Reranker | Task 5 | `feat(rag): use a dedicated cross-encoder reranker` |
| 7 | LangGraph 原生 Chat HITL | 无，建议 Task 6 后执行 | `refactor(agent): use native langgraph hitl interrupts` |
| 8 | 全量回归、文档和 TODO 收口 | Task 1～7 | `docs: document retrieval and hitl operations` |

---

## Task 1: 统一长期记忆 Embedding Provider 接线

**Files:**

- Modify: `app/application/memory_service.py`
- Modify: `app/application/memory_extractor.py`
- Modify: `app/infrastructure/knowledge/embedding.py`
- Modify: `app/core/config.py`
- Modify: `.env.example`
- Test: `tests/test_memory_service.py`
- Test: `tests/test_memory_pipeline.py`
- Test: `tests/knowledge/test_embedding_provider.py`

**Interfaces:**

```python
class EmbeddingProviderPort(Protocol):
    dimensions: int
    async def embed(self, texts: list[str]) -> list[list[float]]: ...

def get_embedding_provider() -> EmbeddingProviderPort: ...

def validate_embeddings(
    texts: list[str],
    embeddings: list[list[float]],
    expected_dimensions: int,
) -> None: ...
```

- [ ] **Step 1: 为生产 Provider 工厂写失败测试**

增加测试，确认长期记忆调用的是 `app.infrastructure.knowledge.embedding.get_embedding_provider()`，而不是导入不存在的类。

覆盖：

- 配置完整时返回生产 Provider。
- 未配置 Key 时抛出 `EmbeddingNotConfiguredError`。
- 长期记忆提取捕获配置缺失后仍保存文本，但 `embedding is None`。
- 编辑记忆重嵌入失败时保留旧向量。

Run:

```bash
uv run pytest tests/test_memory_service.py tests/test_memory_pipeline.py tests/knowledge/test_embedding_provider.py -q
```

Expected: 新增测试 FAIL，暴露当前错误导入或缺少验证函数。

- [ ] **Step 2: 建立单一 Provider 端口**

将 `EmbeddingProviderPort` 放在 `app/domain/ports.py`，基础设施实现该协议。`memory_service.py` 只通过工厂获取 Provider，不再导入具体实现。

- [ ] **Step 3: 增加输出契约验证**

在写库之前统一验证：

- 返回数量等于输入数量。
- 每个向量长度等于 `embedding_dimensions`。
- 所有元素为有限数值，不允许 NaN/Infinity。
- 空输入直接返回空列表，不调用远端 API。

验证失败时记录明确原因并按调用场景降级：新记忆可以仅保存文本；编辑已有记忆时保留旧向量。

- [ ] **Step 4: 修复配置映射**

确认 `get_knowledge_settings()` 显式传递所有相关字段，而不是只依赖 dataclass 默认值：

- `EMBEDDING_API_KEY`
- `EMBEDDING_BASE_URL`
- `EMBEDDING_MODEL`
- `EMBEDDING_DIMENSIONS`
- `EMBEDDING_BATCH_SIZE`

启动期或 Provider 创建期校验维度必须为 1536。

- [ ] **Step 5: 更新 `.env.example`**

只添加空值和说明，不添加真实凭据。说明长期记忆与知识库共用 Embedding 配置。

- [ ] **Step 6: 运行相关验证**

```bash
uv run pytest tests/test_memory_service.py tests/test_memory_pipeline.py tests/knowledge/test_embedding_provider.py -q
git diff --check
```

- [ ] **Step 7: Commit**

```bash
git add app/domain/ports.py app/application/memory_service.py app/application/memory_extractor.py app/infrastructure/knowledge/embedding.py app/core/config.py .env.example tests/test_memory_service.py tests/test_memory_pipeline.py tests/knowledge/test_embedding_provider.py
git commit -m "fix(memory): wire the embedding provider"
```

---

## Task 2: 将长期记忆检索升级为 pgvector Cosine Top-K

**Files:**

- Modify: `app/application/memory_service.py`
- Modify: `app/application/agent/nodes/memory_retriever.py`
- Modify: `app/persistence/models/user_memories.py`
- Test: `tests/test_memory_service.py`
- Test: `tests/test_memory_pipeline.py`
- Create: `tests/test_memory_vector_integration.py`

**Interfaces:**

```python
@dataclass(frozen=True)
class MemoryRetrievalDiagnostics:
    embedding_latency_ms: int
    query_latency_ms: int
    total_latency_ms: int
    mode: Literal["vector", "text_fallback", "unavailable"]
    degradation_reason: str | None = None

async def retrieve_memories(
    query: str,
    workspace_id: str = "default",
    top_k: int = 5,
) -> list[MemorySnippet]: ...
```

- [ ] **Step 1: 写 cosine 排序失败测试**

使用可预测向量验证：

- 相似度最高的记忆排在第一位。
- `rank_score = 1 - cosine_distance`。
- `top_k` 生效。
- pending/rejected 记忆不返回。
- 其他 workspace 不返回。
- `embedding IS NULL` 的记录不参与向量排序。

SQLite 不支持 pgvector 运算，SQL 形状单测和 PostgreSQL 集成测试分开编写。

- [ ] **Step 2: 抽出可测试的向量查询构造**

生产 SQL 应包含：

```sql
SELECT ...,
       1 - (embedding <=> CAST(:query_vec AS vector)) AS rank_score
FROM user_memories
WHERE workspace_id = :workspace_id
  AND status = 'active'
  AND embedding IS NOT NULL
ORDER BY embedding <=> CAST(:query_vec AS vector)
LIMIT :top_k
```

不要在 SQL 中拼接 query 或 workspace 值。

- [ ] **Step 3: 实现向量检索流程**

流程：

1. 空查询直接返回空列表。
2. 获取 Embedding Provider 并生成一个查询向量。
3. 验证查询向量维度。
4. 执行 workspace/status 限定的 cosine Top-K。
5. 只更新最终命中项的 `activation_count` 与 `last_activated_at`。
6. 返回 `MemorySnippet.rank_score`。

- [ ] **Step 4: 明确降级语义**

- Provider 未配置：允许使用现有文本检索作为 `text_fallback`，但日志与诊断中必须标记。
- Provider 调用错误：返回文本降级结果，不允许跨 workspace。
- PostgreSQL vector 查询错误：返回空或文本降级结果，不抛出到聊天主链路。
- 200ms 数据库查询目标只计算 query 阶段；另记录 embedding 和总耗时。

- [ ] **Step 5: 修复超时测试夹具**

当前 `_slow_factory` 是 coroutine 而不是 async context manager，导致未 await 警告。用真正的异步上下文管理器模拟慢查询，并断言超时后底层任务被取消。

- [ ] **Step 6: PostgreSQL 集成测试**

测试使用显式环境开关：

```text
RUN_MEMORY_DB_TESTS=1
```

向测试 workspace 写入固定向量，验证真实 `<=>` 排序、隔离条件和 Top-K；测试结束只删除该测试 workspace 数据。

- [ ] **Step 7: 验证**

```bash
uv run pytest tests/test_memory_service.py tests/test_memory_pipeline.py -q
RUN_MEMORY_DB_TESTS=1 uv run pytest tests/test_memory_vector_integration.py -q
git diff --check
```

- [ ] **Step 8: Commit**

```bash
git add app/application/memory_service.py app/application/agent/nodes/memory_retriever.py app/persistence/models/user_memories.py tests/test_memory_service.py tests/test_memory_pipeline.py tests/test_memory_vector_integration.py
git commit -m "feat(memory): retrieve memories with cosine top-k"
```

---

## Task 3: 修复 pgvector 迁移验证并证明 HNSW 可用

**Files:**

- Modify: `migrations/versions/20260805_context_memory_evolve.py`
- Create: `migrations/versions/YYYYMMDD_memory_vector_constraints.py`
- Modify: `pyproject.toml`
- Modify: `tests/test_memory_pipeline.py`
- Create: `tests/test_memory_migration_integration.py`

**Migration Rule:**

`20260805_context_memory_evolve` 已在运行数据库应用。只允许修正离线渲染兼容性且不得改变已经部署结构的最终语义。新增约束、过滤索引或数据修复必须通过新 revision 完成。

- [ ] **Step 1: 固化当前失败基线**

```bash
uv run pytest tests/test_memory_pipeline.py::test_migration_sql_contains_vector_conversion tests/test_memory_pipeline.py::test_migration_sql_contains_hnsw_index -q
```

Expected: 当前两项 FAIL，离线 SQL 只输出到 `CREATE EXTENSION`。

- [ ] **Step 2: 让迁移支持 offline/online 两种上下文**

移除离线模式不可用的 `bind.engine.connect()` 路径。`CREATE EXTENSION` 应通过 Alembic autocommit block 或与方言兼容的执行方式产生完整离线 SQL。

离线 SQL 测试必须检查：

- `CREATE EXTENSION IF NOT EXISTS vector`
- `vector(1536)`
- ARRAY 到 vector 的合法转换表达式
- `USING hnsw`
- `vector_cosine_ops`

- [ ] **Step 3: 新增后续修复迁移**

新 revision 至少完成：

- 幂等确认 HNSW 索引存在并使用 cosine ops。
- 根据实际查询过滤增加 `(workspace_id, status)` B-tree 索引。
- 在升级前检查所有非空向量维度；异常数据必须中止迁移并给出数量，不能静默丢弃。
- downgrade 只回滚本 revision 新增结构，不破坏历史向量数据。

- [ ] **Step 4: 注册 pytest marker**

在 `pyproject.toml` 注册 `slow` 和 `postgres`，消除未知 marker 警告。

- [ ] **Step 5: 新数据库迁移集成测试**

使用临时 PostgreSQL 数据库或独立 schema 验证：

1. 从 base 升级到 head 成功。
2. `user_memories.embedding` 为 `vector(1536)`。
3. HNSW index definition 含 `vector_cosine_ops`。
4. `(workspace_id, status)` 索引存在。
5. `alembic current` 为唯一 head。

- [ ] **Step 6: 查询计划验证**

写入足够的固定向量数据，在测试事务中设置适当 planner 参数，通过 `EXPLAIN` 断言 cosine Top-K 查询可以选择 HNSW 索引。不要对极小数据集强行断言 planner 必须用索引。

- [ ] **Step 7: 验证**

```bash
uv run pytest tests/test_memory_pipeline.py -q
RUN_MEMORY_DB_TESTS=1 uv run pytest tests/test_memory_migration_integration.py -q
uv run alembic heads
uv run alembic current
git diff --check
```

- [ ] **Step 8: Commit**

```bash
git add migrations/versions/20260805_context_memory_evolve.py migrations/versions/YYYYMMDD_memory_vector_constraints.py pyproject.toml tests/test_memory_pipeline.py tests/test_memory_migration_integration.py
git commit -m "fix(db): verify memory vector migration and hnsw index"
```

---

## Task 4: 建立检索指标计算器与数据契约

**Files:**

- Create: `app/evaluation/__init__.py`
- Create: `app/evaluation/retrieval_metrics.py`
- Create: `app/evaluation/retrieval_dataset.py`
- Create: `tests/knowledge/test_retrieval_metrics.py`
- Modify: `docs/evaluations/private-knowledge-rag.jsonl`

**Data Contract:**

```json
{
  "id": "algorithm_red_black_tree_001",
  "domain": "algorithm",
  "question": "请解释红黑树的五大性质",
  "relevantDocumentIds": ["doc-red-black-tree"],
  "relevanceGrades": {"doc-red-black-tree": 3, "doc-bst": 1},
  "expectedMode": "normal",
  "expectedRefusal": false,
  "expectedCitationDocumentIds": ["doc-red-black-tree"]
}
```

**Interfaces:**

```python
def recall_at_k(retrieved: list[str], relevant: set[str], k: int) -> float: ...
def reciprocal_rank(retrieved: list[str], relevant: set[str]) -> float: ...
def ndcg_at_k(retrieved: list[str], relevance: dict[str, int], k: int) -> float: ...
def citation_accuracy(cited: list[str], allowed: set[str]) -> float: ...
def refusal_accuracy(predictions: list[bool], expected: list[bool]) -> float: ...
```

- [ ] **Step 1: 为每项指标写数学契约测试**

覆盖：空列表、无相关文档、首位命中、后位命中、重复 ID、分级相关性、无引用、全部拒答和混合结果。

- [ ] **Step 2: 实现纯函数指标**

指标函数不得访问数据库、网络或 LLM。明确约定：

- Recall@K 对 relevant 为空的样本不进入宏平均。
- MRR 使用首个 relevant 文档排名。
- NDCG 使用 `2^grade - 1` gain。
- 引用正确率按引用对应的 document ID 判断，不按 `[S1]` 文本位置猜测。
- 拒答准确率分别输出 strict 与 normal 子集。

- [ ] **Step 3: 实现 JSONL 加载与校验**

重复 ID、缺少 relevant 标注、非法 mode、grade 非整数、expectedRefusal 与样本语义冲突时直接失败。

- [ ] **Step 4: 扩展首批数据结构**

先将现有 3 条转换为完整契约，并增加最小覆盖样本，使每个领域至少包含：

- 明确单文档答案。
- 多文档答案。
- 相似但不相关的干扰项。
- 私有资料无答案。
- strict 应拒答。
- normal 应降级。

- [ ] **Step 5: 验证与 Commit**

```bash
uv run pytest tests/knowledge/test_retrieval_metrics.py -q
git diff --check
git add app/evaluation tests/knowledge/test_retrieval_metrics.py docs/evaluations/private-knowledge-rag.jsonl
git commit -m "test(rag): add retrieval metric contracts"
```

---

## Task 5: 建立可执行的 RAG 质量评测基线

**Files:**

- Create: `app/evaluation/run_retrieval_eval.py`
- Rewrite: `tests/knowledge/test_retrieval_quality.py`
- Expand: `docs/evaluations/private-knowledge-rag.jsonl`
- Create: `docs/evaluations/README.md`
- Optional generated output, ignored by Git: `output/evaluations/*.json`

**Evaluation Result:**

```python
@dataclass(frozen=True)
class RetrievalEvaluationResult:
    sample_count: int
    recall_at_5: float
    recall_at_10: float
    mrr: float
    ndcg_at_10: float
    citation_accuracy: float
    strict_refusal_accuracy: float
    normal_fallback_accuracy: float
    latency_p50_ms: float
    latency_p95_ms: float
```

- [ ] **Step 1: 删除常量指标占位测试**

新测试必须把检索结果传给指标计算器。任何直接赋值 `recall_at_k = 1.0` 的测试都不算评测。

- [ ] **Step 2: 建立确定性 CI 评测后端**

使用固定文档、固定 Embedding 和固定 Reranker，运行与生产相同的 RRF、Top-K、阈值和引用映射逻辑。CI 不访问网络。

- [ ] **Step 3: 扩展至不少于 30 条样本**

覆盖算法教学、算法题解、工程选型、网站搭建、部署、运维和无答案问题。至少 20% 样本为无答案或干扰问题，至少 20% 为多文档相关性。

- [ ] **Step 4: 增加评测 CLI**

```bash
uv run python -m app.evaluation.run_retrieval_eval \
  --dataset docs/evaluations/private-knowledge-rag.jsonl \
  --backend deterministic \
  --output output/evaluations/private-knowledge-rag.json
```

真实数据库模式通过 `--backend postgres` 显式启用；不得默认调用远程模型。

- [ ] **Step 5: 记录基线而非预设完美值**

报告输出总体、领域和模式分组指标。第一版门槛建议：

- Recall@5 ≥ 0.80
- MRR ≥ 0.70
- NDCG@10 ≥ 0.75
- 引用正确率 ≥ 0.90
- strict 拒答准确率 ≥ 0.90
- normal 降级准确率 ≥ 0.90

若当前系统未达标，提交真实基线和失败样本清单，不得把期望结果改成当前错误结果来强行通过。

- [ ] **Step 6: 验证与 Commit**

```bash
uv run pytest tests/knowledge/test_retrieval_metrics.py tests/knowledge/test_retrieval_quality.py -q
uv run python -m app.evaluation.run_retrieval_eval --dataset docs/evaluations/private-knowledge-rag.jsonl --backend deterministic
git diff --check
git add app/evaluation tests/knowledge/test_retrieval_quality.py docs/evaluations
git commit -m "test(rag): establish retrieval quality baseline"
```

---

## Task 6: 将 LLM Reranker 替换为专用 Cross-Encoder 服务

**Files:**

- Modify: `app/domain/ports.py`
- Rewrite: `app/infrastructure/knowledge/reranker.py`
- Modify: `app/application/knowledge/retrieval_service.py`
- Modify: `app/application/knowledge/trace_service.py`
- Modify: `app/core/config.py`
- Modify: `.env.example`
- Create: `tests/knowledge/test_cross_encoder_reranker.py`
- Modify: `tests/knowledge/test_retrieval_service.py`
- Modify: `tests/knowledge/test_retrieval_quality.py`

**Provider Contract:**

```python
@dataclass(frozen=True)
class RerankResult:
    index: int
    score: float

class RerankerProviderPort(Protocol):
    model_name: str
    async def rerank(self, query: str, documents: list[str]) -> list[float]: ...
```

- [ ] **Step 1: 写批量 API 契约失败测试**

覆盖：

- 一次请求携带一个 query 和全部 documents。
- 服务返回乱序 index 时正确恢复输入顺序。
- 拒绝缺失 index、重复 index、越界 index、NaN、超出允许范围的分数。
- 空 documents 不发送请求。
- 429、5xx、超时按配置重试，4xx 配置错误不重试。
- 日志不得包含完整私有文档正文或 API Key。

- [ ] **Step 2: 拆分专用配置**

配置至少包含：

- `RERANKER_API_KEY`
- `RERANKER_BASE_URL`
- `RERANKER_MODEL`
- `RERANKER_TIMEOUT_SECONDS`
- `RERANKER_MAX_DOCUMENTS`

不再默认继承 Chat Completions 的 `OPENAI_BASE_URL`。允许 Key 复用，但 endpoint 和协议必须独立。

- [ ] **Step 3: 实现 Cross-Encoder Provider**

Provider 负责适配专用服务协议，上层继续只接收与输入 documents 等长的 `[0,1]` 分数。候选超过服务上限时由上层先按 RRF 截断，不能拆批后直接比较未校准分数，除非供应商明确保证跨批可比。

- [ ] **Step 4: 保持严格降级语义**

- normal：Reranker 缺失或失败时保持 RRF 顺序，并标记 degradation。
- strict：Reranker 缺失或失败时返回无证据并拒答。
- 不再保留逐文档 Chat LLM 打分作为默认降级方案。

- [ ] **Step 5: Trace 与可观测性**

记录：模型名、候选数、调用耗时、最高分、是否降级、错误类别。不得记录私有文档全文。

- [ ] **Step 6: 用评测集做变更门禁**

比较替换前后的 Recall、MRR、NDCG、引用正确率、P50/P95 延迟和请求次数。要求：

- Recall@5 不低于旧基线 0.02 以上。
- MRR/NDCG 不明显下降。
- 单次检索 Rerank 请求数从候选数降为 1。
- P95 低于旧逐文档 LLM 实现。

- [ ] **Step 7: 验证与 Commit**

```bash
uv run pytest tests/knowledge/test_cross_encoder_reranker.py tests/knowledge/test_retrieval_service.py tests/knowledge/test_retrieval_quality.py -q
uv run python -m app.evaluation.run_retrieval_eval --dataset docs/evaluations/private-knowledge-rag.jsonl --backend deterministic
git diff --check
git add app/domain/ports.py app/infrastructure/knowledge/reranker.py app/application/knowledge/retrieval_service.py app/application/knowledge/trace_service.py app/core/config.py .env.example tests/knowledge
git commit -m "feat(rag): use a dedicated cross-encoder reranker"
```

---

## Task 7: 将 Chat HITL 升级为 LangGraph 原生 Interrupt/Command

**Scope:** 只处理 `chat_tools → hitl_decision` 的约束冲突选择。不改造 `task_plans` 的用户停止控制，也不改造独立 `/api/multi-agent` 的运行控制。

**Files:**

- Modify: `app/application/agent/nodes/hitl_decision.py`
- Modify: `app/application/agent/graphs/conversation.py`
- Modify: `app/application/agent/scheduling.py`
- Modify: `app/application/context/run_inputs.py`
- Modify: `app/api/routes/chats.py`
- Modify: `app/application/agent/state.py`
- Modify: `tests/test_hitl_decision.py`
- Rewrite: `tests/test_hitl_graph.py`
- Rewrite: `tests/test_hitl_choice_api.py`
- Modify: `tests/test_chat_checkpoint_resume.py`

**Native Flow:**

```python
from langgraph.types import Command, interrupt

async def hitl_decision_node(state: ChatAgentState) -> dict:
    conflict = _find_conflict(state.get("messages") or [])
    if conflict is None:
        return {}
    choice = _build_choice_payload(conflict)
    selection = interrupt(choice)
    return {
        "hitl_selection": selection,
        "hitl_choice": choice,
    }
```

恢复必须使用：

```python
await graph.astream_events(
    Command(resume=selection_payload),
    config={"configurable": {"thread_id": original_thread_id}},
    version="v2",
)
```

- [ ] **Step 1: 为原生暂停写失败图测试**

测试真实编译图与 checkpointer：

1. 工具冲突触发 interrupt。
2. checkpoint 的 `next` 保持在 HITL 节点。
3. interrupt payload 是现有前端可理解的 choice payload。
4. 此时图没有执行后续 chat 回复。

- [ ] **Step 2: 为 Command 恢复写失败测试**

使用相同 `thread_id` 和 `Command(resume=...)`：

- `interrupt()` 返回用户选择。
- 图从暂停点继续，不重新运行 preprocess、意图识别和工具搜索。
- 工具搜索调用次数保持 1。
- 恢复后产生最终回复。

- [ ] **Step 3: 将选择节点改为原生 interrupt**

中断 payload 必须是 JSON-serializable。中断之前只执行纯解析和 payload 构造，不写数据库、不发送外部请求。

删除用 `hitl_pending=True` 路由到 END 的模拟逻辑；保留 `hitl_choice` 仅用于状态和持久化兼容时，需要明确其生命周期。

- [ ] **Step 4: 让调度层识别 interrupt**

`run_agent_stream()` 应将 LangGraph interrupt 转换成稳定事件：

```text
choice.requested
```

事件负载包含 choice payload 和稳定的 checkpoint/thread 标识，但不暴露内部 checkpoint 数据。

- [ ] **Step 5: 首次运行持久化 choice_request**

`send_message_stream` 在收到 interrupt 事件时：

- 保存一条 `choice_request` 消息。
- 记录它对应的 `thread_id`、branch root 和 run ID；优先复用现有 message payload，避免新表。
- 不发送 `run.completed` 作为正常完成；发送明确的 paused 终态事件，或让 `choice.requested` 成为本轮终态。
- 释放 chat 运行锁。

- [ ] **Step 6: `/choices` 改用 Command(resume=...)**

选择提交 API：

- 校验 choice_request 属于当前 chat。
- 校验 selection 在允许 option IDs 内；若允许自由文本，单独定义 schema。
- 保持同一 choice + selection 的幂等语义。
- 从保存的 branch/thread 信息恢复相同 `thread_id`。
- 输入只能是 `Command(resume=selection_payload)`，不得重新拼装历史消息和新一轮 user input。
- 恢复成功后保存 `hitl_selection` 和最终 assistant 消息。

- [ ] **Step 7: 重放和副作用安全测试**

覆盖：

- 节点恢复时从开头重放，但工具调用不重复。
- 重复提交不会再次恢复已完成 checkpoint。
- 不同 selection 对同一已完成 interrupt 返回 409 或稳定业务错误。
- 错误 thread ID 不能恢复其他 chat。
- 服务重启后使用持久 checkpointer 仍可恢复。
- 恢复期间同 chat 并发请求返回 409，完成后锁释放。

- [ ] **Step 8: 清理遗留字段和测试**

只有确认没有消费者后才删除 `hitl_pending`。若前端或历史 checkpoint 仍依赖，保留一版兼容读取但停止写入，并在代码中注明移除条件。

- [ ] **Step 9: 验证与 Commit**

```bash
uv run pytest tests/test_hitl_decision.py tests/test_hitl_graph.py tests/test_hitl_choice_api.py tests/test_chat_checkpoint_resume.py tests/test_conversation_graph.py -q
git diff --check
git add app/application/agent/nodes/hitl_decision.py app/application/agent/graphs/conversation.py app/application/agent/scheduling.py app/application/context/run_inputs.py app/api/routes/chats.py app/application/agent/state.py tests/test_hitl_decision.py tests/test_hitl_graph.py tests/test_hitl_choice_api.py tests/test_chat_checkpoint_resume.py
git commit -m "refactor(agent): use native langgraph hitl interrupts"
```

---

## Task 8: 全量回归、运行文档与 TODO 收口

**Files:**

- Modify: `README.md`
- Modify: `docs/todo.md`
- Create: `docs/evaluations/README.md` if Task 5 has not already created it
- Modify: `.gitignore` when evaluation output is not already ignored

- [ ] **Step 1: 后端相关全量验证**

```bash
uv run pytest tests/test_memory_service.py tests/test_memory_pipeline.py tests/test_memory_vector_integration.py tests/knowledge tests/test_hitl_decision.py tests/test_hitl_graph.py tests/test_hitl_choice_api.py tests/test_chat_checkpoint_resume.py -q
```

- [ ] **Step 2: 数据库验证**

```bash
docker compose up -d postgres
uv run alembic upgrade head
uv run alembic current
uv run alembic heads
RUN_MEMORY_DB_TESTS=1 uv run pytest tests/test_memory_migration_integration.py tests/test_memory_vector_integration.py -q
```

Expected:

- 单一 Alembic head。
- 当前 revision 等于 head。
- vector/HNSW/过滤索引检查通过。
- cosine Top-K 集成测试通过。

- [ ] **Step 3: 评测门禁**

```bash
uv run python -m app.evaluation.run_retrieval_eval \
  --dataset docs/evaluations/private-knowledge-rag.jsonl \
  --backend deterministic \
  --output output/evaluations/private-knowledge-rag.json
```

保存报告摘要到 CI 日志；生成的逐样本报告不提交 Git。

- [ ] **Step 4: 完整项目回归**

```bash
uv run pytest tests/ -q
cd frontend && bun test
cd frontend && bun run typecheck
cd frontend && bun run build
git diff --check
```

- [ ] **Step 5: 手工验收**

长期记忆：

1. 配置真实 Embedding 后创建显式记忆。
2. 用语义相近但不含相同关键词的问题检索，确认能召回。
3. 创建其他 workspace 的相似记忆，确认不串数据。
4. 将记忆设为 rejected，确认不再召回。
5. 检查日志不包含向量、Key 或完整私密内容。

RAG：

1. normal 模式相关问题返回引用。
2. normal 模式无答案显示降级说明。
3. strict 模式无答案拒答。
4. 断开 Reranker 后 strict 模式仍拒答、normal 模式显式降级。

HITL：

1. 触发采集数量冲突并看到选择卡片。
2. 选择“使用已有结果”，确认搜索工具不重复调用。
3. 刷新或重启服务后恢复另一个暂停流程。
4. 重复点击同一选择不产生重复消息。

- [ ] **Step 6: 更新运维文档**

README 至少记录：

- Embedding 和 Reranker 独立配置。
- 数据库迁移命令。
- 如何检查 vector/HNSW。
- 如何运行 deterministic 和 PostgreSQL 评测。
- strict/normal 降级语义。
- HITL 暂停恢复依赖持久 checkpointer 和稳定 thread ID。

- [ ] **Step 7: 更新 TODO 状态**

只有对应验收全部通过后才把 `docs/todo.md` 条目标记为完成。若评测指标未达门槛，保留该项未完成并附当前基线，不得只因评测脚本存在就勾选。

- [ ] **Step 8: Final Commit**

```bash
git add README.md docs/todo.md docs/evaluations/README.md .gitignore
git commit -m "docs: document retrieval and hitl operations"
```

## Final Definition of Done

- [ ] 长期记忆生产路径使用统一 Embedding Provider，错误导入消失。
- [ ] 语义查询通过 pgvector cosine Top-K 返回正确 workspace 的 active 记忆。
- [ ] 全新数据库可以升级到 head，已有数据库可以安全升级到新 revision。
- [ ] HNSW 索引定义与真实查询计划均有 PostgreSQL 集成验证。
- [ ] 评测集不少于 30 条，并真实计算 Recall@K、MRR、NDCG、引用与拒答指标。
- [ ] Reranker 使用一次批量 Cross-Encoder 请求，逐文档 Chat LLM 默认实现已移除。
- [ ] strict/normal 模式在 Reranker 故障时保持约定语义。
- [ ] Chat HITL 使用 `interrupt()` 与相同 `thread_id` 的 `Command(resume=...)`。
- [ ] HITL 恢复不重复调用搜索工具，重复选择保持幂等。
- [ ] 相关测试、全量后端测试、前端测试、类型检查和构建全部通过。
- [ ] `git diff --check` 无输出，工作区不包含凭据或生成报告。
