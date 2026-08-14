# 私有资料库 RAG Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans` 按任务顺序实施；每完成一个任务，先验证再提交。

**Goal:** 为现有创作 Agent 增加可维护的私有资料库：非 Markdown 资料经过人工确认后才索引，Markdown 直接索引；创作时按需执行 BM25 + 向量混合检索、重排、证据判断，并返回真实引用和可追踪 Trace。

**Architecture:** 采用三层存储：`output/knowledge/sources/` 保存源文件或网页快照，`output/knowledge/documents/` 保存唯一可分块的 Markdown，PostgreSQL 保存元数据、父子 Chunk、Embedding、BM25/向量索引及 Trace。Application 层编排导入、确认、索引和检索；Infrastructure 层实现解析器、Embedding、PostgreSQL 检索与 Reranker；LangGraph 只负责“是否检索、严格/普通模式和降级”决策，不承载检索算法。

**Tech Stack:** Python 3.11、FastAPI、Pydantic v2、SQLAlchemy 2 Async、Alembic、PostgreSQL、ParadeDB `pg_search`（BM25）、`pgvector`、OpenAI-compatible Embedding/视觉 OCR/LLM Reranker、PyMuPDF4LLM、BeautifulSoup + markdownify、LangGraph、React 19、TypeScript、TanStack Query、Zustand、Tailwind CSS v4。

## Global Constraints

- 本计划对应已确认规格：[feature-private-knowledge-rag.md](../specs/feature-private-knowledge-rag.md)，不得把知识图谱、自动全网抓取、自动收录 AI 草稿、多人审核或全局严格模式加入第一版。
- 前端视觉与交互以 [private-knowledge-rag-ui.html](../private-knowledge-rag-ui.html) 为准，并复用当前 `WorkspaceLayout`、UI 组件和三栏布局规则。
- 所有 Chunk 只从已生效 Markdown 生成；源文件和候选 Markdown 永远不能进入检索。
- Markdown 上传不复制到源文件目录；PDF、文本、图片和 URL 必须保留源文件或 HTML 快照，并在 Markdown Front Matter 中指回来源。
- 普通模式证据不足时明确降级并继续创作；单次请求选择严格模式时拒答。不得伪造私有资料引用。
- `workspace_id` 与 `owner_id` 必须出现在所有文档、检索和 Trace 查询条件中；不能依赖前端过滤。
- PostgreSQL 原生 `ts_rank_cd` 不是 BM25。第一版用 `pg_search` 的 `USING bm25` 索引，并用 `pgvector` 的 HNSW cosine 索引；参考 [ParadeDB BM25 索引](https://docs.paradedb.com/documentation/indexing/create-index) 与 [pgvector SQLAlchemy](https://github.com/pgvector/pgvector-python#sqlalchemy)。
- ParadeDB Community 的生产 WAL 保证有限；第一版只将其作为本地/开发实现。生产部署前必须评估自托管扩展或具备相同能力的托管方案，不在本次功能中直接上线 Community 镜像。
- 默认参数固定为：父块最多 1,200 tokens，子块最多 350 tokens，子块重叠 50 tokens；BM25/向量各取 20，RRF `k=60`，Reranker 取前 8，证据阈值 `0.55`，上下文预算 6,000 tokens。参数集中配置，后续只能通过评测集调整。
- 后台任务第一版使用 FastAPI `BackgroundTasks`，每个任务自行打开数据库会话；处理状态持久化，失败可重试。第一版不引入 Celery/Redis。
- 修改 `.py` 后运行相关 pytest；修改 `.ts/.tsx` 后至少运行 `bun run typecheck` 和 `bun run build`。

## 功能概述

实现从资料导入到创作引用的完整闭环：Markdown 直接成为正式文档；其他格式转换成候选 Markdown，经用户编辑并明确确认后才建立父子 Chunk、Embedding、BM25 与向量索引。Agent 根据创作问题决定是否检索，执行查询改写、双路检索、RRF、Reranker、证据判断和父块上下文构建，最终返回回答、简化来源和调试 Trace。

## 目标

- 支持 PDF、Markdown、纯文本、图片、URL 和用户主动选择的历史文章。
- 支持候选编辑、确认门禁、已生效 Markdown 编辑、重新转换差异确认、重试和软删除。
- 支持 workspace/owner 隔离的 BM25 + 向量混合检索与故障降级。
- 支持普通模式降级、严格模式拒答、真实引用和完整 Trace。
- 提供与现有项目主题一致的独立资料库页面和创作入口。

## 范围

**包含：** 规格中的三层存储、解析/OCR、人工确认、父子分块、版本化索引、混合检索、Reranker、证据阈值、Agent 接入、引用/Trace、资料管理页面、安全和评测集。

**不包含：** 自动抓取互联网、未审核内容自动入库、知识图谱、多人审核、复杂权限、自动生产级任务队列，以及替代现有实时搜索和官方资料工具。

## 技术栈

- 后端：Python 3.11、FastAPI、Pydantic v2、SQLAlchemy 2 Async、Alembic、LangGraph。
- 数据与检索：PostgreSQL、ParadeDB `pg_search` BM25、`pgvector` HNSW cosine、OpenAI-compatible Embedding 与 LLM Reranker。
- 文档处理：PyMuPDF4LLM、BeautifulSoup、markdownify、OpenAI-compatible 视觉 OCR、tiktoken。
- 前端：React 19、TypeScript、Vite、Tailwind CSS v4、TanStack Query、Zustand、React Router、Bun。

## 涉及文件

```text
docker-compose.yml
pyproject.toml
uv.lock
.env.example
app/core/config.py
app/models.py
app/server.py
app/domain/ports.py
app/domain/knowledge.py
app/persistence/models/__init__.py
app/persistence/models/knowledge.py
app/persistence/repositories/knowledge_repository.py
migrations/versions/20260722_knowledge_rag.py
app/application/knowledge/{document_service,indexing_service,retrieval_service,context_builder,trace_service}.py
app/infrastructure/knowledge/{storage,parsers,ssrf,embedding,reranker}.py
app/api/routes/knowledge.py
app/application/agent/state.py
app/application/agent/graphs/conversation.py
app/application/agent/nodes/{knowledge_decision,retrieve_knowledge,chat_node}.py
app/domain/dto.py
prompts/knowledge/{decision,query_rewrite,rerank,grounded_answer}.yml
frontend/src/app/App.tsx
frontend/src/features/chat/{workspace-shell,chat-panel}.tsx
frontend/src/features/knowledge/*
frontend/src/lib/api.ts
tests/knowledge/*
tests/test_knowledge_api.py
tests/test_conversation_graph.py
docs/evaluations/private-knowledge-rag.jsonl
docs/specs/feature-private-knowledge-rag.md
docs/private-knowledge-rag-ui.html
```

## 任务拆分

1. PostgreSQL BM25/向量能力与配置。
2. 数据模型、数据库扩展和索引。
3. 三层文件存储、解析器与 URL 安全。
4. 资料生命周期服务和 REST API。
5. 父子分块、Embedding 与版本化索引。
6. 混合检索、RRF、Reranker 和上下文构建。
7. Trace、来源快照和查询 API。
8. LangGraph 创作流程与普通/严格模式。
9. 资料库前端路由、API 和三栏页面。
10. 候选确认、编辑、重新转换和差异交互。
11. 创作 UI 的模式、来源和降级展示。
12. 端到端验收、安全回归和评测基线。

## TDD 执行步骤

### Task 1：准备 PostgreSQL BM25/向量能力与配置

**Files:**

- Modify: `docker-compose.yml`
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Modify: `.env.example`
- Modify: `app/core/config.py`
- Test: `tests/knowledge/test_knowledge_config.py`

**Interfaces:**

- 新增 `KnowledgeSettings`，提供存储目录、模型、维度、分块、Top K、阈值和 token 预算。
- 本地 PostgreSQL 镜像必须同时提供 `pg_search` 和 `vector` 扩展。

- [ ] **Step 1：写失败测试**

在 `tests/knowledge/test_knowledge_config.py` 验证默认目录为 `output/knowledge/sources`、`output/knowledge/documents`，默认 `embedding_dimensions=1536`、`rrf_k=60`、`evidence_threshold=0.55`，非法正整数回退默认值。

- [ ] **Step 2：运行测试确认失败**

```bash
uv run pytest tests/knowledge/test_knowledge_config.py -v
```

Expected: FAIL，`KnowledgeSettings` 或 `get_knowledge_settings` 尚不存在。

- [ ] **Step 3：最小实现**

1. 在 `pyproject.toml` 增加：

```toml
"pgvector>=0.4",
"python-multipart>=0.0.20",
"pymupdf4llm>=0.0.27",
"markdownify>=1.2",
"tiktoken>=0.12",
```

2. 将本地数据库镜像改为官方 `paradedb/paradedb:latest`；切换前执行 `pg_dump`，并改用新 volume `paradedb_data`，避免 PG16 volume 被 PG18 直接打开。保留旧 `postgres_data` volume，验证完成前不删除。
3. `.env.example` 增加 `EMBEDDING_API_KEY/BASE_URL/MODEL/DIMENSIONS`、`OCR_API_KEY/BASE_URL/MODEL`、`KNOWLEDGE_*` 检索参数和存储目录。
4. `app/core/config.py` 新增冻结 dataclass `KnowledgeSettings` 与 `get_knowledge_settings()`；目录基于 `OUTPUT_DIR` 解析，密钥不放入对象的日志表示。

- [ ] **Step 4：运行测试确认通过**

```bash
uv sync
uv run pytest tests/knowledge/test_knowledge_config.py -v
docker compose up -d postgres
docker compose exec postgres psql -U dev -d content_workspace -c "SELECT extname FROM pg_available_extensions WHERE extname IN ('pg_search','vector') ORDER BY extname;"
```

Expected: pytest PASS；SQL 返回 `pg_search`、`vector` 两行。

- [ ] **Step 5：重构与验证**

将所有默认值集中在 `KnowledgeSettings`，禁止路由、服务或前端重复硬编码。

- [ ] **Step 6：Commit**

```bash
git add docker-compose.yml pyproject.toml uv.lock .env.example app/core/config.py tests/knowledge/test_knowledge_config.py
git commit -m "chore: prepare knowledge search infrastructure"
```

### Task 2：建立知识库数据模型、扩展和索引

**Files:**

- Create: `app/domain/knowledge.py`
- Create: `app/persistence/models/knowledge.py`
- Modify: `app/persistence/models/__init__.py`
- Create: `migrations/versions/20260722_knowledge_rag.py`
- Create: `tests/knowledge/test_knowledge_models.py`
- Create: `tests/knowledge/test_knowledge_migration.py`

**Interfaces:**

- `KnowledgeDocumentStatus = pending | awaiting_confirmation | indexing | available | failed | deleted`。
- 表：`knowledge_documents`、`knowledge_chunks`、`knowledge_index_versions`、`retrieval_traces`、`retrieval_hits`。
- `knowledge_chunks.embedding` 为 `VECTOR(1536)`；BM25 只覆盖 `chunk_type='child'` 且未删除的行。

- [ ] **Step 1：写失败测试**

验证 SQLAlchemy model 字段与规格一致、`KnowledgeChunk.parent_chunk_id` 自关联、Trace/Hit 关系完整；数据库测试验证扩展存在、HNSW 与 BM25 索引存在，且 `(workspace_id, document_id, index_version)` 查询有普通 B-tree 索引。

- [ ] **Step 2：运行测试确认失败**

```bash
uv run pytest tests/knowledge/test_knowledge_models.py tests/knowledge/test_knowledge_migration.py -v
```

Expected: FAIL，知识模型和迁移不存在。

- [ ] **Step 3：最小实现**

迁移以 `3b22ddb2e5e9` 为 `down_revision`，执行：

```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_search;

CREATE INDEX knowledge_chunks_vector_hnsw_idx
ON knowledge_chunks USING hnsw (embedding vector_cosine_ops)
WHERE chunk_type = 'child' AND deleted_at IS NULL;

CREATE INDEX knowledge_chunks_bm25_idx
ON knowledge_chunks USING bm25
  (id, content, heading_path, workspace_id, document_id, index_version, deleted_at)
WITH (key_field='id');
```

`KnowledgeDocument` 增加 `candidate_markdown_path`、`conversion_error`、`converter_version` 与 `active_index_version`，用于实现规格已经要求的候选、错误和版本切换；它们是实现字段，不改变对外数据模型。`RetrievalHit` 保存 `context_snapshot`，保证源文档以后删除时历史引用仍可解析。

- [ ] **Step 4：运行测试确认通过**

```bash
uv run alembic upgrade head
uv run pytest tests/knowledge/test_knowledge_models.py tests/knowledge/test_knowledge_migration.py -v
```

Expected: PASS；迁移 head 为 `20260722_knowledge_rag`。

- [ ] **Step 5：重构与验证**

执行 `uv run alembic downgrade 3b22ddb2e5e9 && uv run alembic upgrade head`，确认升级/降级可逆；扩展本身 downgrade 不删除，避免影响同库其他功能。

- [ ] **Step 6：Commit**

```bash
git add app/domain/knowledge.py app/persistence/models migrations/versions/20260722_knowledge_rag.py tests/knowledge/test_knowledge_models.py tests/knowledge/test_knowledge_migration.py
git commit -m "feat: add private knowledge persistence schema"
```

### Task 3：实现三层文件存储、解析器和 URL 安全

**Files:**

- Modify: `app/domain/ports.py`
- Create: `app/infrastructure/knowledge/storage.py`
- Create: `app/infrastructure/knowledge/parsers.py`
- Create: `app/infrastructure/knowledge/ssrf.py`
- Create: `tests/knowledge/test_knowledge_storage.py`
- Create: `tests/knowledge/test_knowledge_parsers.py`
- Create: `tests/knowledge/test_knowledge_ssrf.py`

**Interfaces:**

```python
class DocumentParserPort(Protocol):
    async def parse(self, source: SourceDocument) -> ParsedMarkdown: ...

class KnowledgeStorage:
    def save_source(self, document_id: UUID, filename: str, content: bytes) -> Path: ...
    def save_candidate(self, document_id: UUID, markdown: str) -> Path: ...
    def publish_markdown(self, document_id: UUID, markdown: str) -> Path: ...
```

- [ ] **Step 1：写失败测试**

覆盖 Markdown 不写 source、非 Markdown source 与 candidate 分层、Front Matter 字段、PDF 空/损坏/加密、文本编码、OCR 低置信度、HTML 正文清洗、重定向过多、`localhost`/私网/链路本地地址/DNS rebinding 拒绝。

- [ ] **Step 2：运行测试确认失败**

```bash
uv run pytest tests/knowledge/test_knowledge_storage.py tests/knowledge/test_knowledge_parsers.py tests/knowledge/test_knowledge_ssrf.py -v
```

Expected: FAIL，端口和实现不存在。

- [ ] **Step 3：最小实现**

- `MarkdownParser`：规范换行，校验非空正文，补齐 Front Matter。
- `TextParser`：UTF-8/UTF-8-SIG 解码后转 Markdown。
- `PdfParser`：使用 `pymupdf4llm.to_markdown()`；扫描件无正文时返回可识别错误并允许转 OCR。
- `VisionOcrParser`：通过独立 OpenAI-compatible 视觉模型返回 `{markdown, confidence, warnings}`；`confidence < 0.8` 记录警告但仍保持待确认。
- `UrlParser`：每次重定向前重新执行 scheme、host、DNS 与 IP 检查；只允许 `http/https`，最大 5 次重定向、10 MB 响应；保存 HTML 快照，BeautifulSoup 去除 script/style/nav 后用 markdownify 转换。
- 文件名由服务器生成 `<document_id>/<sanitized-name>`；拒绝路径穿越、`.env`、cookie、证书、SQLite checkpoint 和超过 25 MB 的上传。

- [ ] **Step 4：运行测试确认通过**

```bash
uv run pytest tests/knowledge/test_knowledge_storage.py tests/knowledge/test_knowledge_parsers.py tests/knowledge/test_knowledge_ssrf.py -v
```

Expected: PASS。

- [ ] **Step 5：重构与验证**

解析器注册表按 MIME + 后缀选择，未知格式返回稳定错误码 `unsupported_knowledge_source`；所有异常统一转换为可持久化的转换错误。

- [ ] **Step 6：Commit**

```bash
git add app/domain/ports.py app/infrastructure/knowledge tests/knowledge/test_knowledge_storage.py tests/knowledge/test_knowledge_parsers.py tests/knowledge/test_knowledge_ssrf.py
git commit -m "feat: add guarded knowledge document conversion"
```

### Task 4：实现资料生命周期服务和 REST API

**Files:**

- Create: `app/persistence/repositories/knowledge_repository.py`
- Create: `app/application/knowledge/document_service.py`
- Create: `app/api/routes/knowledge.py`
- Modify: `app/models.py`
- Modify: `app/server.py`
- Create: `tests/knowledge/test_document_service.py`
- Create: `tests/test_knowledge_api.py`

**Interfaces:**

- 完整实现规格列出的 documents 上传、URL 导入、列表、详情、reindex、Markdown GET/PUT、confirm、reconvert、DELETE。
- 所有 API 响应使用 `{"ok": true, "data": ...}`；Pydantic alias 使用 camelCase。

- [ ] **Step 1：写失败测试**

覆盖以下状态机：

```text
Markdown upload -> indexing
non-Markdown upload -> pending -> awaiting_confirmation
candidate PUT -> awaiting_confirmation（不触发索引）
confirm -> indexing
available Markdown PUT -> indexing（仅该文档）
reconvert with manual edits -> awaiting_confirmation + diff
delete -> deleted
failed -> retry -> pending/indexing
```

API 测试同时断言 owner/workspace 不匹配返回 404，防止资源枚举。

- [ ] **Step 2：运行测试确认失败**

```bash
uv run pytest tests/knowledge/test_document_service.py tests/test_knowledge_api.py -v
```

Expected: FAIL，服务、DTO 和路由不存在。

- [ ] **Step 3：最小实现**

`DocumentService` 用内容 SHA-256 去重；Markdown 上传直接写正式文档并排队索引，其他来源保存 source/candidate 后停在 `awaiting_confirmation`。`PUT markdown` 根据当前状态决定只保存 candidate 或发布新 revision。`reconvert` 永不覆盖 active Markdown，只生成 candidate 和统一 diff。DELETE 只写 `deleted_at/status`，保留文件以支持历史引用；所有检索查询排除删除行。

路由通过 `BackgroundTasks` 调用转换/索引函数，后台函数从 session factory 新建会话，不能复用请求会话。

- [ ] **Step 4：运行测试确认通过**

```bash
uv run pytest tests/knowledge/test_document_service.py tests/test_knowledge_api.py -v
```

Expected: PASS。

- [ ] **Step 5：重构与验证**

把状态转换集中到 `DocumentService`，Repository 不包含业务判断，路由不直接访问文件或 ORM。

- [ ] **Step 6：Commit**

```bash
git add app/persistence/repositories/knowledge_repository.py app/application/knowledge/document_service.py app/api/routes/knowledge.py app/models.py app/server.py tests/knowledge/test_document_service.py tests/test_knowledge_api.py
git commit -m "feat: add private knowledge document lifecycle API"
```

### Task 5：实现父子分块、Embedding 和版本化索引

**Files:**

- Create: `app/application/knowledge/chunking.py`
- Create: `app/application/knowledge/indexing_service.py`
- Create: `app/infrastructure/knowledge/embedding.py`
- Create: `tests/knowledge/test_markdown_chunking.py`
- Create: `tests/knowledge/test_indexing_service.py`
- Create: `tests/knowledge/test_embedding_provider.py`

**Interfaces:**

```python
class EmbeddingProviderPort(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...

class IndexingService:
    async def index_document(self, scope: KnowledgeScope, document_id: UUID) -> IndexResult: ...
```

- [ ] **Step 1：写失败测试**

覆盖标题路径和锚点、代码块/表格不被错误截断、父子关系、token 上限、50 token 重叠、只对子块 Embedding、相同 Markdown hash 跳过、单文档重建、并发编辑导致旧任务放弃发布、新索引版本原子切换、Embedding 维度错误进入 failed。

- [ ] **Step 2：运行测试确认失败**

```bash
uv run pytest tests/knowledge/test_markdown_chunking.py tests/knowledge/test_embedding_provider.py tests/knowledge/test_indexing_service.py -v
```

Expected: FAIL，分块和索引服务不存在。

- [ ] **Step 3：最小实现**

- Markdown 按 heading/段落/代码围栏解析；先生成父块，再在父块内生成可检索子块。
- Embedding 批量大小 64、超时 30 秒、最多 3 次指数退避；返回数量或维度不一致立即失败。
- 新版本使用 UUID `index_version`。事务内插入新 Chunk；完成后把文档 `active_index_version` 切换到新值，再软删除旧 Chunk。失败不切换，旧版本继续服务。
- 在任务开始与发布前比较 `markdown_revision/hash`，文档已修改或删除则标记任务 superseded，不发布过期索引。

- [ ] **Step 4：运行测试确认通过**

```bash
uv run pytest tests/knowledge/test_markdown_chunking.py tests/knowledge/test_embedding_provider.py tests/knowledge/test_indexing_service.py -v
```

Expected: PASS。

- [ ] **Step 5：重构与验证**

用同一 `TokenCounter` 完成分块和上下文预算；Embedding 内容包含标题路径和正文，但持久化 `content` 仍只保存原始子块正文。

- [ ] **Step 6：Commit**

```bash
git add app/application/knowledge/chunking.py app/application/knowledge/indexing_service.py app/infrastructure/knowledge/embedding.py tests/knowledge/test_markdown_chunking.py tests/knowledge/test_embedding_provider.py tests/knowledge/test_indexing_service.py
git commit -m "feat: add versioned parent child knowledge indexing"
```

### Task 6：实现混合检索、RRF、Reranker 和上下文构建

**Files:**

- Create: `app/application/knowledge/retrieval_service.py`
- Create: `app/application/knowledge/context_builder.py`
- Create: `app/infrastructure/knowledge/reranker.py`
- Create: `prompts/knowledge/query_rewrite.yml`
- Create: `prompts/knowledge/rerank.yml`
- Create: `tests/knowledge/test_rrf.py`
- Create: `tests/knowledge/test_retrieval_service.py`
- Create: `tests/knowledge/test_context_builder.py`

**Interfaces:**

```python
async def retrieve(request: RetrievalRequest) -> RetrievalResult

RRF score = sum(1 / (60 + rank))
```

- [ ] **Step 1：写失败测试**

覆盖查询改写同时喂给两路、BM25/向量各 Top 20、RRF 去重、Reranker Top 8、子块回填父块、重复父块合并、6,000 token 截断、证据阈值、两路完全不重合、Reranker 故障回退 RRF、单路故障继续、双路故障返回不足证据、workspace/owner/index version 过滤。

- [ ] **Step 2：运行测试确认失败**

```bash
uv run pytest tests/knowledge/test_rrf.py tests/knowledge/test_retrieval_service.py tests/knowledge/test_context_builder.py -v
```

Expected: FAIL，检索服务不存在。

- [ ] **Step 3：最小实现**

BM25 SQL 使用 `content ||| :query` 和 `pdb.score(id)` 排序；向量 SQL 使用 `embedding.cosine_distance(:query_vector)`。两路 SQL 都显式过滤 scope、`chunk_type='child'`、`deleted_at IS NULL` 和文档当前 `active_index_version`。Reranker 只返回 chunk ID 和 0–1 分数，未知 ID 丢弃；超时 8 秒后使用 RRF 排名。证据充分条件固定为“至少一个命中且最高 rerank/RRF 归一化分数 `>= 0.55`”。

Context Builder 回填父块，按重排顺序加入，分配 `[S1]...[Sn]`；每条 source 保存标题、文件/URL、更新时间、命中子块、父块快照和 token 数。

- [ ] **Step 4：运行测试确认通过**

```bash
uv run pytest tests/knowledge/test_rrf.py tests/knowledge/test_retrieval_service.py tests/knowledge/test_context_builder.py -v
```

Expected: PASS。

- [ ] **Step 5：重构与验证**

将 query rewrite、BM25、vector、RRF、rerank、threshold、context 各阶段结果保留在结构化对象，后续 Trace 直接消费，不重新计算。

- [ ] **Step 6：Commit**

```bash
git add app/application/knowledge/retrieval_service.py app/application/knowledge/context_builder.py app/infrastructure/knowledge/reranker.py prompts/knowledge tests/knowledge/test_rrf.py tests/knowledge/test_retrieval_service.py tests/knowledge/test_context_builder.py
git commit -m "feat: add hybrid private knowledge retrieval"
```

### Task 7：持久化 Trace、来源快照和查询 API

**Files:**

- Create: `app/application/knowledge/trace_service.py`
- Modify: `app/persistence/repositories/knowledge_repository.py`
- Modify: `app/api/routes/knowledge.py`
- Modify: `app/models.py`
- Create: `tests/knowledge/test_trace_service.py`
- Modify: `tests/test_knowledge_api.py`

**Interfaces:**

- `GET /api/ai-operations/{operation_id}/sources`
- `GET /api/retrieval-traces/{trace_id}`，仅 `debug=true` 且服务端允许调试时返回完整内容。

- [ ] **Step 1：写失败测试**

验证 Trace 保存原问题、改写、判断原因、过滤条件、所有阶段分数、模型/索引版本、最终上下文、降级和耗时；简化来源不泄漏内部评分；文档删除后历史来源仍由 snapshot 返回；跨 scope 和非调试 Trace 请求不可读取。

- [ ] **Step 2：运行测试确认失败**

```bash
uv run pytest tests/knowledge/test_trace_service.py tests/test_knowledge_api.py -v
```

Expected: FAIL，Trace service 与端点尚未实现。

- [ ] **Step 3：最小实现**

检索开始即创建 Trace，`finally` 中写耗时和失败信息；每个阶段的 hit 以 `retrieval_source` 区分。进入上下文的 hit 必须带稳定 citation label 和 immutable snapshot。普通来源 API 只返回标题、类型、URL/文件、更新时间和片段预览。

- [ ] **Step 4：运行测试确认通过**

```bash
uv run pytest tests/knowledge/test_trace_service.py tests/test_knowledge_api.py -v
```

Expected: PASS。

- [ ] **Step 5：重构与验证**

敏感信息清洗在 Trace 写入前统一执行；不保存 API key、Authorization、Cookie、完整上传路径之外的环境信息。

- [ ] **Step 6：Commit**

```bash
git add app/application/knowledge/trace_service.py app/persistence/repositories/knowledge_repository.py app/api/routes/knowledge.py app/models.py tests/knowledge/test_trace_service.py tests/test_knowledge_api.py
git commit -m "feat: persist retrieval traces and source snapshots"
```

### Task 8：接入 LangGraph 创作流程与普通/严格模式

**Files:**

- Modify: `app/domain/dto.py`
- Modify: `app/application/agent/state.py`
- Create: `app/application/agent/nodes/knowledge_decision.py`
- Create: `app/application/agent/nodes/retrieve_knowledge.py`
- Modify: `app/application/agent/nodes/chat_node.py`
- Modify: `app/application/agent/graphs/conversation.py`
- Create: `prompts/knowledge/decision.yml`
- Create: `prompts/knowledge/grounded_answer.yml`
- Modify: `tests/test_conversation_graph.py`
- Create: `tests/knowledge/test_grounded_answer.py`

**Interfaces:**

- 请求字段：`knowledgeMode: off | normal | strict`，默认 `normal`；`workspaceId`、`ownerId` 必填并由认证上下文覆盖客户端值。
- State 新增 `rag_decision`、`decision_reason`、`retrieval_result`、`trace_id`、`fallback_reason`。

- [ ] **Step 1：写失败测试**

覆盖四条主路径：无需 RAG 直接 chat；证据充分注入私有上下文；普通模式不足，附提示后继续现有工具/通用回答；严格模式不足，直接返回拒答且不调用 chat LLM。另测时效性/API/框架版本问题即使私有资料命中也允许现有官方资料/实时搜索工具补充。

- [ ] **Step 2：运行测试确认失败**

```bash
uv run pytest tests/test_conversation_graph.py tests/knowledge/test_grounded_answer.py -v
```

Expected: FAIL，图中没有 RAG 决策和检索节点。

- [ ] **Step 3：最小实现**

图调整为：

```text
preprocess -> route_intent
chat intent -> knowledge_decision
off/not-needed -> chat
needed -> retrieve_knowledge
sufficient -> chat(grounded context)
insufficient+normal -> chat(fallback notice)
insufficient+strict -> build strict refusal -> END
```

`chat_node` 将 `[Sx]` 上下文作为单独 system block 注入，并在模型返回后校验所有 `[Sx]` 都属于本次 context；未知引用删除并记录 Trace 警告。通用知识或 Web 结论不能获得私有 `[Sx]` 标签。响应返回 `traceId`、`sources`、`knowledgeFallback`。

- [ ] **Step 4：运行测试确认通过**

```bash
uv run pytest tests/test_conversation_graph.py tests/knowledge/test_grounded_answer.py -v
```

Expected: PASS。

- [ ] **Step 5：重构与验证**

保证 SQLite Checkpointer 只保存图运行 state；知识正文、Chunk 和 Trace 仍只在文件层/PostgreSQL，不复制进 checkpoint 的长期消息历史。

- [ ] **Step 6：Commit**

```bash
git add app/domain/dto.py app/application/agent app/application/knowledge prompts/knowledge tests/test_conversation_graph.py tests/knowledge/test_grounded_answer.py
git commit -m "feat: connect private knowledge retrieval to chat agent"
```

### Task 9：实现资料库前端路由、API 和三栏页面骨架

**Files:**

- Modify: `frontend/src/app/App.tsx`
- Modify: `frontend/src/features/chat/workspace-shell.tsx`
- Modify: `frontend/src/lib/api.ts`
- Create: `frontend/src/features/knowledge/types.ts`
- Create: `frontend/src/features/knowledge/knowledge-api.ts`
- Create: `frontend/src/features/knowledge/use-knowledge.ts`
- Create: `frontend/src/features/knowledge/knowledge-page.tsx`
- Create: `frontend/src/features/knowledge/knowledge-list.tsx`
- Create: `frontend/src/features/knowledge/knowledge-detail.tsx`
- Create: `frontend/src/features/knowledge/knowledge-inspector.tsx`
- Create: `frontend/src/features/knowledge/knowledge-logic.test.ts`

**Interfaces:**

- 新路由 `/knowledge`。
- `apiUpload<T>(path, FormData)` 不手工设置 multipart `Content-Type`。
- Query keys 必须包含 `workspaceId` 和筛选条件。

- [ ] **Step 1：写失败测试**

用 Bun 测试状态标签映射、过滤条件、候选/正式编辑模式派生逻辑、普通用户来源 DTO 不展示 score。组件验收通过 typecheck/build 和后续浏览器手测完成。

- [ ] **Step 2：运行测试确认失败**

```bash
cd frontend && bun test src/features/knowledge/knowledge-logic.test.ts
```

Expected: FAIL，knowledge feature 尚不存在。

- [ ] **Step 3：最小实现**

按设计稿实现共享 Header 下的三栏：左栏上传/URL/筛选，中栏资料列表与状态，右栏详情/处理信息。增加 Markdown/PDF/text/image 文件选择与 URL 对话框；处理状态轮询仅针对 pending/indexing 文档，available/failed 后停止。

- [ ] **Step 4：运行测试确认通过**

```bash
cd frontend && bun test src/features/knowledge/knowledge-logic.test.ts
cd frontend && bun run typecheck
cd frontend && bun run build
```

Expected: 全部 PASS。

- [ ] **Step 5：重构与验证**

保持 `workflow-api -> hook -> store/component` 的现有边界；组件中不直接 `fetch`，独立滚动列保持 `flex-1 min-h-0 overflow-auto`。

- [ ] **Step 6：Commit**

```bash
git add frontend/src/app/App.tsx frontend/src/features/chat/workspace-shell.tsx frontend/src/lib/api.ts frontend/src/features/knowledge
git commit -m "feat: add private knowledge library page"
```

### Task 10：实现候选确认、编辑、重新转换和差异交互

**Files:**

- Create: `frontend/src/features/knowledge/knowledge-markdown-editor.tsx`
- Create: `frontend/src/features/knowledge/reconvert-diff-dialog.tsx`
- Modify: `frontend/src/features/knowledge/knowledge-detail.tsx`
- Modify: `frontend/src/features/knowledge/use-knowledge.ts`
- Modify: `frontend/src/features/knowledge/knowledge-logic.test.ts`

**Interfaces:**

- `保存候选` 只调用 PUT markdown；`确认并建立索引` 单独调用 confirm。
- 已生效 Markdown 保存后显示 indexing；reconvert 先展示 diff，再由用户明确确认替换。

- [ ] **Step 1：写失败测试**

测试按钮/动作矩阵：Markdown 上传不出现首次确认；候选保存不 confirm；候选确认必须二次确认；低 OCR 置信度展示警告；manual edits 的 reconvert 必须展示 diff 且取消时不替换；failed 展示错误与重试。

- [ ] **Step 2：运行测试确认失败**

```bash
cd frontend && bun test src/features/knowledge/knowledge-logic.test.ts
```

Expected: FAIL，动作矩阵和 diff 状态不存在。

- [ ] **Step 3：最小实现**

复用现有 Markdown 编辑器样式，右栏提供编辑/预览切换。确认按钮文案明确说明“确认后才会分块并建立索引”。重新转换响应包含 unified diff；只有对话框中的“使用候选版本并重新索引”才调用 confirm，关闭/取消不产生写入。

- [ ] **Step 4：运行测试确认通过**

```bash
cd frontend && bun test src/features/knowledge/knowledge-logic.test.ts
cd frontend && bun run typecheck
cd frontend && bun run build
```

Expected: PASS。

- [ ] **Step 5：重构与验证**

所有 mutation 成功后只失效当前 workspace 的列表/detail/markdown query；编辑中的未保存文本不写 Zustand 持久化。

- [ ] **Step 6：Commit**

```bash
git add frontend/src/features/knowledge
git commit -m "feat: add knowledge markdown confirmation workflow"
```

### Task 11：在创作 UI 展示模式、来源和降级

**Files:**

- Modify: `frontend/src/features/chat/chat-panel.tsx`
- Modify: `frontend/src/features/chat/chat-logic.test.ts`
- Modify: `frontend/src/types/workflow.ts`
- Modify: `frontend/src/features/knowledge/knowledge-api.ts`
- Create: `frontend/src/features/knowledge/source-list.tsx`
- Create: `frontend/src/features/knowledge/retrieval-trace-dialog.tsx`

**Interfaces:**

- 单次请求可选“普通创作 / 仅依据私有资料”；默认普通，不写全局设置。
- 回答展示简化来源和非阻塞降级提示；调试入口按服务端能力显示。

- [ ] **Step 1：写失败测试**

测试默认发送 `knowledgeMode=normal`、严格选项只影响当前发送、来源按 `[Sx]` 映射、fallback 提示、普通来源不展示内部 score、严格拒答不显示伪来源。

- [ ] **Step 2：运行测试确认失败**

```bash
cd frontend && bun test src/features/chat/chat-logic.test.ts
```

Expected: FAIL，请求与响应类型没有知识库字段。

- [ ] **Step 3：最小实现**

输入区增加紧凑的单次模式选择；消息响应渲染 `参考来源` 折叠区，点击 `[Sx]` 定位对应来源；普通模式降级显示“私有资料证据不足，本回答使用了其他知识来源”；调试模式用 trace endpoint 展示阶段信息。

- [ ] **Step 4：运行测试确认通过**

```bash
cd frontend && bun test src/features/chat/chat-logic.test.ts
cd frontend && bun run typecheck
cd frontend && bun run build
```

Expected: PASS。

- [ ] **Step 5：重构与验证**

来源组件同时服务 Chat 回答与未来文章详情；渲染前再次过滤未出现在后端 `sources` 中的引用标签。

- [ ] **Step 6：Commit**

```bash
git add frontend/src/features/chat frontend/src/features/knowledge frontend/src/types/workflow.ts
git commit -m "feat: expose knowledge sources in creation flow"
```

### Task 12：完成端到端验收、安全回归和评测基线

**Files:**

- Create: `tests/knowledge/test_knowledge_e2e.py`
- Create: `tests/knowledge/test_retrieval_quality.py`
- Create: `docs/evaluations/private-knowledge-rag.jsonl`
- Modify: `README.md`
- Modify: `.gitignore`

**Interfaces:**

- 评测集覆盖算法学习路线、题解、概念教学、工程算法选择、个人网站选型/搭建/部署/运维。
- 输出 Recall@K、引用正确率、普通降级准确率、严格拒答准确率和忠实度样本结果。

- [ ] **Step 1：写失败的端到端测试**

将规格 17 条验收标准逐项映射到测试名称；使用固定 fake Embedding/Reranker 做稳定 CI，另设 `RUN_KNOWLEDGE_DB_TESTS=1` 才执行真实 BM25/pgvector 集成测试。

- [ ] **Step 2：运行测试确认存在未覆盖项**

```bash
uv run pytest tests/knowledge/test_knowledge_e2e.py tests/knowledge/test_retrieval_quality.py -v
```

Expected: 首次 FAIL，并指出尚未满足的验收路径，而不是网络或真实 LLM 错误。

- [ ] **Step 3：完成最小修正与文档**

- 补齐所有验收路径，不增加新功能。
- `.gitignore` 增加 `output/knowledge/`，确保源文件、Markdown、候选和快照不提交。
- README 记录数据库扩展、环境变量、三层目录、启动、迁移、备份、严格模式和调试 Trace 使用方式。
- JSONL 每个样本包含 `id/domain/question/relevant_document_ids/expected_mode/expected_citations`，不包含版权原文或凭证。

- [ ] **Step 4：运行完整验证**

```bash
uv run pytest tests/knowledge tests/test_knowledge_api.py tests/test_conversation_graph.py -v
uv run pytest tests/ -v
cd frontend && bun test
cd frontend && bun run typecheck
cd frontend && bun run build
uv run alembic current
git diff --check
```

Expected: 全部 PASS；Alembic current 为 `20260722_knowledge_rag (head)`；`git diff --check` 无输出。

- [ ] **Step 5：手工验收**

依次完成：上传 Markdown 立即索引；上传 PDF/截图后编辑候选、确认再索引；URL 快照；修改正式 Markdown 单文档重建；reconvert diff/取消/确认；删除后双路不命中；普通降级；严格拒答；来源点击；调试 Trace；跨 workspace 查询。浏览器控制台不得出现 error。

- [ ] **Step 6：Commit**

```bash
git add tests/knowledge docs/evaluations/private-knowledge-rag.jsonl README.md .gitignore
git commit -m "test: cover private knowledge rag acceptance criteria"
```

## 验证命令

```bash
docker compose up -d postgres
uv sync
uv run alembic upgrade head
uv run pytest tests/knowledge tests/test_knowledge_api.py tests/test_conversation_graph.py -v
uv run pytest tests/ -v
cd frontend && bun install
cd frontend && bun test
cd frontend && bun run typecheck
cd frontend && bun run build
git diff --check
```

需要真实数据库扩展的测试：

```bash
RUN_KNOWLEDGE_DB_TESTS=1 uv run pytest tests/knowledge/test_knowledge_migration.py tests/knowledge/test_retrieval_service.py -v
```

## 提交计划

1. `chore: prepare knowledge search infrastructure`
2. `feat: add private knowledge persistence schema`
3. `feat: add guarded knowledge document conversion`
4. `feat: add private knowledge document lifecycle API`
5. `feat: add versioned parent child knowledge indexing`
6. `feat: add hybrid private knowledge retrieval`
7. `feat: persist retrieval traces and source snapshots`
8. `feat: connect private knowledge retrieval to chat agent`
9. `feat: add private knowledge library page`
10. `feat: add knowledge markdown confirmation workflow`
11. `feat: expose knowledge sources in creation flow`
12. `test: cover private knowledge rag acceptance criteria`

## 风险与回滚

- **数据库镜像升级：** ParadeDB `latest` 当前基于较新 PostgreSQL，不能直接复用现有 PG16 数据目录。切换前 `pg_dump`，使用新 volume 恢复并验收；失败时把 compose 恢复为 `postgres:16-alpine`、恢复原 `postgres_data`，应用回退到迁移前版本。旧 volume 在验收完成前不得删除。
- **生产 BM25 持久性：** ParadeDB Community 不作为本计划的直接生产承诺。若生产环境不接受其保证，回滚到“功能关闭但数据保留”，待部署受支持的 `pg_search`/等价 BM25 服务后再启用；不得用 `ts_rank_cd` 静默替代。
- **Embedding 模型/维度变化：** 创建新 `index_version` 并完成重建后原子切换；失败继续使用旧版本。迁移中不能原地改变现有 vector 维度。
- **OCR/转换错误：** 所有非 Markdown 资料停在人工确认门禁；低置信度只警告，不自动索引。重新转换只生成候选，不覆盖人工版本。
- **索引并发：** 发布前检查 revision/hash/deleted_at；过期任务放弃切换。失败保留上一可用版本。
- **检索依赖失败：** Reranker 失败用 RRF；BM25 或向量单路失败用另一路；双路失败按普通/严格模式分别降级或拒答。
- **上下文与引用污染：** 上下文严格限制 6,000 tokens；只允许引用实际进入 context 的 source label；历史引用使用 snapshot，不依赖已删除源文档。
- **敏感资料：** 上传和 URL 导入进行文件类型、路径、SSRF 与敏感名称拦截；Trace 写入前清洗 header/cookie/key。若发现泄漏，立即关闭知识库入口、软删除索引记录并轮换相关凭证。

## 完成标准

- 规格中的 17 条验收标准均有自动化测试或明确的浏览器验收步骤，且结果通过。
- Markdown 与非 Markdown 的两条导入路径严格遵守“直接索引”和“人工确认后索引”的区别。
- 源文件、标准 Markdown、PostgreSQL 三层存储关系可从 document metadata 和 Front Matter 双向追溯。
- BM25、向量、RRF、Reranker、父块回填、证据阈值、普通降级和严格拒答均可通过 Trace 还原。
- 回答中的每个 `[Sx]` 都能解析到本次实际进入上下文的快照；无证据时不存在私有引用。
- workspace/owner 隔离、URL SSRF、敏感文件拒绝和删除后不可检索测试通过。
- 后端完整 pytest、前端 Bun tests/typecheck/build、Alembic migration 和 `git diff --check` 全部通过。
- `output/knowledge/`、API 密钥、Cookie 和 SQLite checkpoint 未进入 Git。

## 规格覆盖自检

- **导入与确认：** Tasks 3、4、10 覆盖 Requirement 资料导入 1–13 和 AC 1–8。
- **分块与索引：** Tasks 2、5 覆盖父子分块、双索引、hash 去重、单文档重建、删除和版本切换，覆盖 AC 9–10。
- **检索与创作：** Tasks 6、8、11 覆盖决策、query rewrite、BM25/vector、RRF、Reranker、阈值、普通/严格路径与时效性资料，覆盖 AC 11–15。
- **引用与 Trace：** Tasks 6、7、8、11 覆盖稳定引用、来源快照、完整 Trace 与普通用户简化视图，覆盖 AC 12、16。
- **隔离与安全：** Tasks 3、4、6、7、12 覆盖 workspace/owner、敏感文件与 SSRF，覆盖 AC 17。
- **无占位项：** 规格 Open Questions 为“无”；本计划不存在 TODO/TBD，第一版依赖、默认参数、失败策略和验收命令均已明确。
