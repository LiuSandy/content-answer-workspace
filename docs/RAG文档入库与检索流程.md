# RAG 文档入库与检索流程

本文记录当前项目中私有知识库 RAG 的两条主线：

```text
文档入库：原始文件 → Markdown → 切片 → Embedding → knowledge_chunks
文档检索：用户问题 → 查询改写 → 混合召回 → 重排 → 上下文
```

## 一、文档入库流程

### 1. 发现并登记源文件

系统启动时由 `IngestionExecutor` 启动后台入库运行时，并扫描 `pending` 目录。前端上传文件时，则直接登记已经写入 `pending` 的文件。

- 启动入口：`app/services/rag/ingestion_service.py` 的 `IngestionExecutor.start()`
- 目录扫描：`SourceIngestionService.scan_pending()`
- 上传登记：`SourceIngestionService.register_uploaded()`

### 2. 创建数据库记录

`SourceIngestionService._register()` 会依次创建：

1. `knowledge_source_files`：记录原始文件信息和物理路径。
2. `knowledge_ingestion_jobs`：记录本次文件入库任务。
3. `knowledge_documents`：创建对应的逻辑知识文档，初始状态为 `PENDING`。

文件随后从 `pending` 移动到 `processing`，任务状态进入 `queued`。

代码：`app/services/rag/ingestion_service.py` 的 `SourceIngestionService._register()`。

### 3. Worker 领取任务

后台 worker 从 `knowledge_ingestion_jobs` 中领取最早的 `queued` 任务，将其改为 `running`，并写入 worker 租约、心跳和开始时间。

- 领取任务：`IngestionExecutor._claim_next()`
- 执行任务：`IngestionExecutor._process()`

### 4. 按文件类型转换为 Markdown

#### Markdown

Markdown 文件直接读取并保存为正式 Markdown，然后进入索引流程。

#### TXT

TXT 文件按 UTF-8 读取，失败时尝试 GBK，保存为候选 Markdown，等待确认。

#### PDF

PDF 使用 MinerU 转换为 Markdown。当前未配置 MinerU 或 MinerU 调用失败时会直接抛错，不再使用本地解析降级；入库 worker 会将对应任务和文档标记为失败。

PDF 的处理流程为：

```text
统计页数
→ 创建 knowledge_ingestion_pages 分页记录
→ 逐页调用 MinerU
→ 保存每页 Markdown 和解析置信度
→ 合并页面 Markdown
→ 保存候选 Markdown
```

相关代码：

- PDF 总流程：`app/services/rag/ingestion_service.py` 的 `_process_pdf()`
- 单页处理：`_process_pdf_page()`
- MinerU 入口：`app/api/routes/knowledge.py` 的 `_parse_pdf_to_markdown()`
- MinerU 实现：`app/infrastructure/files/parsers.py` 的 `MinerUCloudParser`

### 5. 候选 Markdown 确认

PDF 和 TXT 通常先保存为：

```text
output/knowledge/documents/{document_id}.candidate.md
```

用户确认后，`DocumentService.confirm_document()` 会：

1. 将候选 Markdown 发布为正式 Markdown。
2. 更新 `markdown_path` 和 `markdown_content_hash`。
3. 将文档状态改为 `INDEXING`。
4. 将源文件从 `recognized` 移到 `archived`。
5. 清理 PDF 入库临时目录。
6. 异步触发索引任务。

相关代码：

- `app/services/rag/document_service.py` 的 `confirm_document()`
- `app/api/routes/knowledge.py` 的 `confirm_document()`

正式 Markdown 的默认路径是：

```text
output/knowledge/documents/{document_id}.md
```

存储实现位于 `app/infrastructure/database/repositories/knowledge_storage.py`。

### 6. 建立切片和向量索引

索引任务由 `_run_indexing_task()` 调用 `IndexingService.index_document()`。

流程如下：

```text
读取正式 Markdown
→ 计算 Markdown SHA-256
→ 判断是否已有相同内容的索引
→ 父子分块
→ 对子块分批生成 Embedding
→ 创建新的 index_version
→ 写入父块和子块
→ 文档切换到新索引版本
→ 旧版本切片软删除
```

其中：

- 父块保存完整上下文，不保存 Embedding。
- 子块是主要检索单元，保存 Embedding。
- 子块通过 `parent_chunk_id` 关联父块。
- Embedding 按 `embedding_batch_size` 分批处理，避免一次性构造全部子块文本。

核心代码：

- 调度：`app/api/routes/knowledge.py` 的 `_run_indexing_task()`
- 索引：`app/services/rag/indexing_service.py` 的 `IndexingService.index_document()`
- 分块：`app/services/rag/chunking.py` 的 `ParentChildChunker`
- Embedding：`app/infrastructure/embeddings/provider.py`

最终写入：

```text
knowledge_chunks
```

文档状态变为：

```text
INDEXING → AVAILABLE
```

## 二、文档检索流程

### 1. 判断是否需要知识库检索

聊天图先通过知识库决策节点判断当前问题是否需要检索私有资料。

- 决策节点：`app/agents/chat/nodes/knowledge_decision.py`
- 图路由：`app/agents/chat/graph.py`

如果不需要检索，则直接进入普通回答流程；如果需要，则进入 `retrieve_knowledge` 节点。

### 2. 查询改写

`KnowledgeRetrievalService.retrieve()` 首先调用 LLM，将用户原始问题改写为更适合全文检索和向量检索的查询语句。

- 查询改写：`KnowledgeRetrievalService._rewrite_query()`
- Prompt：`app/agents/_shared/prompts/knowledge/query_rewrite.yml`

如果改写失败，则使用原始问题继续检索。

### 3. 查询向量化

使用 Embedding Provider 将改写后的查询转换为向量，供后续向量相似度检索使用。

代码位于 `KnowledgeRetrievalService.retrieve()` 的“查询向量化”阶段。

### 4. 双路召回

两路召回都查询 `knowledge_chunks` 中的子块：

```sql
chunk_type = 'child'
AND deleted_at IS NULL
```

#### BM25 全文召回

使用 ParadeDB 的 `pg_search` 对子块 `content` 进行全文检索，并按 BM25 分数排序。

代码：`KnowledgeRetrievalService._search_bm25()`。

#### 向量召回

使用 PostgreSQL/pgvector 的向量距离计算，比较查询向量与子块 `embedding` 的相似度。

代码：`KnowledgeRetrievalService._search_vector()`。

### 5. RRF 融合

将 BM25 结果和向量结果合并，使用 Reciprocal Rank Fusion（RRF）进行统一排序，并去除重复切片。

代码：`compute_rrf()`。

### 6. LLM 重排与证据判断

从 RRF 结果中取出候选切片，交给 Reranker 计算相关性分数，然后根据阈值判断是否有足够证据。

- 重排：`KnowledgeRetrievalService._rerank_or_fallback()`
- 调用位置：`KnowledgeRetrievalService.retrieve()`

### 7. 回填父块并构建上下文

检索命中的是子块，但最终上下文优先使用对应的父块内容：

```text
子块命中
→ 根据 parent_chunk_id 查询父块
→ 使用父块补充上下文
→ 按 token 预算裁剪
```

父块仍然来自 `knowledge_chunks` 表，只是查询条件为：

```sql
chunk_type = 'parent'
AND deleted_at IS NULL
```

上下文构建代码：`app/services/rag/context_builder.py` 的 `ContextBuilder`。

### 8. 返回检索结果并记录追踪信息

最终返回：

- `context_text`：注入回答生成的上下文。
- `sources`：前端展示的引用来源。
- `trace_hits`：每个命中切片的分数和排名。
- `rewritten_query`：改写后的查询。

检索节点会将结果写入：

```text
retrieval_traces
retrieval_hits
```

相关代码：

- 检索服务：`app/services/rag/retrieval_service.py`
- Chat 检索节点：`app/agents/chat/nodes/retrieve_knowledge.py`
- 追踪记录：`app/services/rag/trace_service.py`

## 三、核心数据流总结

```text
原始文件
  ↓
knowledge_source_files
  ↓
knowledge_ingestion_jobs
  ↓
knowledge_ingestion_pages（PDF）
  ↓
knowledge_documents
  ↓
正式 Markdown
  ↓
父子分块 + Embedding
  ↓
knowledge_chunks
  ↓
BM25 / 向量双路检索
  ↓
RRF 融合 + 重排
  ↓
父块上下文
  ↓
retrieval_traces / retrieval_hits
  ↓
注入回答生成流程
```
