# 私有资料库 RAG

## 背景（Background）

当前创作 Agent 主要依赖问题原文、模型通用知识和实时搜索生成回答。对于数据结构与算法教学、个人网站搭建等技术方案，用户可能已经拥有 PDF、Markdown、网页和历史文章等私有资料，但系统无法统一管理、检索和引用这些资料。

本功能为现有创作 Agent 增加可持续更新的私有资料库。系统将各种来源统一转换为可编辑的 Markdown 标准文档，所有分块和索引只从 Markdown 生成。系统在创作时按需检索资料，将相关证据提供给模型，并返回可追溯的引用。私有资料不足时采用普通创作模式继续回答，不把知识库覆盖率变成创作阻塞条件。

## 目标（Goal）

支持用户导入、更新和删除私有资料，并通过混合检索、重排序和上下文构建为创作 Agent 提供可引用证据。系统必须区分私有资料依据与模型通用知识，在资料不足时清晰降级且不得伪造引用。

## 非目标（Non-Goals）

- 不建设自动抓取整个互联网的通用搜索引擎。
- 不自动把全部聊天记录或未审核 AI 草稿加入知识库。
- 不以私有资料库替代最新官方文档和实时搜索。
- 第一版不提供多人协作审核、复杂权限角色或知识图谱。
- 不保证低清晰度、严重遮挡或复杂排版图片的识别结果无需人工校对；低置信度内容不得自动进入可用索引。

## 用户故事（User Stories）

- 作为用户，我希望上传 PDF、Markdown、图片或历史文章，以便 Agent 在技术创作中复用我的资料。
- 作为用户，我希望导入网页 URL，以便将指定网页保存为可检索资料。
- 作为用户，我希望修改或删除资料后索引同步更新，以免检索到过期内容。
- 作为用户，我希望回答展示实际使用的资料来源，以便核查结论。
- 作为用户，我希望私有资料不足时 Agent 仍能正常回答，并明确说明使用了其他知识来源。
- 作为用户，我希望可以明确要求仅依据私有资料回答，此时证据不足应拒答。
- 作为用户，我希望能够编辑转换后的 Markdown，并确保重新解析源文件不会未经确认覆盖人工修改。

## 功能需求（Requirements）

### 资料导入与管理

1. 系统必须支持 PDF、Markdown、纯文本、图片截图、网页 URL 和用户主动选择的历史文章。
2. 非 Markdown 资料必须保留源文件，并生成统一的 Markdown 标准文档；URL 必须保存原始 URL 和网页快照。
3. 用户上传的 Markdown 直接作为正式标准文档保存，不在源文件目录中保留重复副本，并立即进入分块与索引流程。
4. Markdown Front Matter 必须记录文档 ID、来源类型、源文件路径或 URL、内容哈希、转换时间和转换器版本。
5. 导入流程必须保存来源、标准 Markdown、内容哈希、更新时间和处理状态。
6. 系统必须展示待处理、待确认、索引中、可用、失败和已删除状态。
7. 解析、OCR 或索引失败的资料必须保留错误信息并允许重试。
8. 所有非 Markdown 资料转换后都必须进入待确认状态；用户可以查看和编辑候选 Markdown，只有明确确认后才能转为正式标准文档并进入分块与索引流程。
9. 低置信度 OCR 结果必须显示识别质量警告，但仍遵循相同的人工确认门禁。
10. 系统不得自动收录未审核的 AI 回答。
11. 用户编辑候选 Markdown 时，保存操作只能更新候选内容，不得触发索引；确认操作才触发首次分块和索引。
12. 用户必须能够编辑已生效的标准 Markdown；保存后只重建该 Markdown 对应的分块和索引。
13. 已有人工编辑时，重新解析源文件只能生成候选 Markdown 和差异预览，必须经用户确认后才能替换当前版本。

### 解析、分块与索引

1. 系统必须先将来源解析、OCR 和清洗为 Markdown；源文件和未确认的候选 Markdown 不得直接分块或生成 Embedding。
2. 所有分块必须只从当前生效的 Markdown 版本生成。
3. 系统采用父子分块：子块用于检索，父块用于构建模型上下文。
4. 每个分块必须保留标准 Markdown 文档、章节标题、段落锚点和来源元数据。
5. 子块必须同时进入关键词索引和向量索引。
6. Markdown 内容哈希未变化时必须跳过重复索引。
7. Markdown 变化时只重建受影响文档的分块和索引。
8. 文档删除时必须同步软删除源文件、标准 Markdown、分块和索引，使其不再参与检索。
9. 更换 Embedding 模型或分块策略时必须创建新索引版本，完成后再切换当前版本。

### 检索与创作

1. Agent 必须判断当前创作请求是否需要私有资料检索，并记录判断结果和原因。
2. 查询改写结果必须同时用于 BM25 和向量检索。
3. 两路检索结果必须通过 RRF 融合、去重，再由 Reranker 重排。
4. 系统必须根据命中的子块取回父块，并在 token 预算内构建上下文。
5. 系统必须在重排后执行证据阈值判断。
6. 证据充分时，模型基于检索上下文生成回答并返回引用。
7. 普通创作模式下证据不足时，系统必须提示私有资料不足，并允许改用最新官方资料、实时搜索或模型通用知识继续回答。
8. 用户明确要求仅依据私有资料时，系统切换为严格知识库模式；证据不足必须拒答。
9. 涉及时效性事实、框架版本、API 或平台规则时，应优先使用最新官方资料，不得仅依赖可能过期的私有资料。

### 引用与 Trace

1. 每个提供给模型的证据片段必须获得稳定的本次请求引用编号，例如 `[S1]`。
2. 模型只能引用本次检索实际返回并进入上下文的资料。
3. 引用必须关联标题、来源、URL 或文件、引用片段和资料更新时间。
4. 使用模型通用知识的内容不得伪装成私有资料引用。
5. 系统必须保存检索 Trace，包括原问题、改写查询、过滤条件、各阶段结果与分数、最终上下文、索引版本、模型信息、降级路径、引用关系和耗时。
6. 普通用户默认只看到简化来源；完整 Trace 用于调试和质量评估。

### 隔离与安全

1. 检索必须按用户或 workspace 隔离，任何用户不得检索到其他用户的私有资料。
2. 系统不得索引密钥、Cookie、凭证或运行时 checkpoint。
3. URL 导入必须遵守既有网络安全约束，并防止访问不允许的内部地址。

## 验收标准（Acceptance Criteria）

1. 上传有效 PDF、图片或纯文本后，系统保留源文件并生成带来源指向的候选 Markdown；用户确认前不能通过关键词或语义查询命中。
2. 用户可以编辑并保存候选 Markdown，保存过程不建立索引；确认后才生成 Chunk、Embedding 和检索索引。
3. 上传 Markdown 后，文件直接进入标准文档目录和分块索引流程，不在源文件目录生成重复副本。
4. 导入有效网页 URL 后，系统保存原始 URL、网页快照和候选 Markdown；无法解析时显示可重试错误。
5. 低置信度 OCR 结果必须显示警告，且未经用户确认时不能参与检索。
6. 用户编辑已生效的 Markdown 后，相关 Chunk 和索引随之更新，源文件保持不变。
7. 存在人工编辑时，重新解析源文件不会直接覆盖 Markdown；只有用户确认候选差异后才替换。
8. 同一内容重复提交时，系统根据内容哈希跳过重复索引。
9. 修改一份资料后，仅该资料生成新分块和索引；旧分块不再被检索。
10. 删除资料后，BM25 和向量检索均不再返回该资料。
11. 同一问题的 BM25 和向量结果能经过 RRF 与 Reranker 得到统一排序结果。
12. 证据充分时，回答中的每个私有资料引用都能解析到实际送入模型的片段。
13. 普通创作模式下证据不足时，系统明确提示降级来源并继续创作。
14. 严格知识库模式下证据不足时，系统拒答且不调用通用知识生成结论。
15. Reranker 故障时，系统使用 RRF 结果继续；单一路检索故障时使用另一路继续。
16. 完整 Trace 能还原本次检索、上下文选择、降级和引用过程。
17. 使用不同用户或 workspace 查询时，只能命中当前范围内的资料。

## 边界情况（Edge Cases）

- PDF 为空、加密、损坏或仅包含扫描图片。
- 图片分辨率过低、文字遮挡、表格或代码识别错误。
- Markdown 包含超长代码块、表格、重复导航或无正文内容。
- URL 无法访问、重定向过多、正文为空或内容随后发生变化。
- 同一资料通过文件和 URL 重复导入。
- 文档在索引过程中被修改或删除。
- 人工编辑过 Markdown 后再次请求从源文件转换，产生内容冲突。
- BM25 与向量结果完全不重合，或全部低于证据阈值。
- 多个资料给出相互冲突或不同版本的结论。
- 上下文超过模型 token 预算。
- Embedding、Reranker、向量索引或关键词索引暂时不可用。
- 引用来源被删除，但历史回答仍保留引用记录。

## 交互与界面行为（UX / UI Behavior）

1. 设置或工作区提供“私有资料库”入口，支持上传文件或图片、输入 URL、查看资料列表和处理状态。
2. 每条资料提供重新索引和删除操作；失败状态展示简明原因。
3. 创作结果展示“参考来源”，包含标题、来源类型、更新时间和命中片段预览。
4. 私有资料不足并发生降级时，在回答区域显示非阻塞提示。
5. 用户可在单次创作请求中选择“仅依据私有资料”，无需修改全局默认模式。
6. 调试模式可查看完整检索 Trace，普通模式不展示检索分数等内部细节。
7. 用户可以查看和编辑标准 Markdown；重新解析可能覆盖人工内容时必须展示差异并请求确认。

前端页面采用与现有 Chat 工作台一致的顶部 Header、紧凑信息密度和三栏结构。独立设计稿见 [私有资料库前端设计预览](../private-knowledge-rag-ui.html)。

## 数据模型（Data Model）

### KnowledgeDocument

- `id`
- `workspace_id` / `owner_id`
- `source_type`：PDF、Markdown、text、image、URL、history
- `title`
- `source_uri`
- `author`
- `published_at`
- `source_path`：非 Markdown 资料的源文件或网页快照路径
- `source_url`
- `markdown_path`
- `source_content_hash`
- `markdown_content_hash`
- `markdown_revision`
- `has_manual_edits`
- `conversion_confidence`
- `status`
- `metadata`
- `index_version`
- `created_at` / `updated_at` / `deleted_at`

### KnowledgeChunk

- `id`
- `document_id`
- `parent_chunk_id`
- `chunk_type`：parent、child
- `chunk_index`
- `heading_path`
- `markdown_anchor`
- `content`
- `token_count`
- `embedding`
- `embedding_model`
- `index_version`
- `metadata`

### RetrievalTrace

- `id`
- `workspace_id` / `owner_id`
- `chat_id` / `ai_operation_id`
- `original_query`
- `rewritten_query`
- `rag_decision` / `decision_reason`
- `mode`：normal、strict
- `filters`
- `index_version`
- `embedding_model` / `reranker_model`
- `fallback_reason`
- `latency_ms`
- `created_at`

### RetrievalHit

- `trace_id`
- `chunk_id`
- `retrieval_source`：bm25、vector、fused、reranked
- `rank`
- `bm25_score`
- `vector_score`
- `rrf_score`
- `rerank_score`
- `included_in_context`
- `citation_label`

## 接口设计（API / Interface Design）

接口沿用现有 `{"ok": true, "data": ...}` 响应结构，提供以下端点：

- `POST /api/knowledge/documents`：上传文件并创建资料。
- `POST /api/knowledge/documents/import-url`：导入网页 URL。
- `GET /api/knowledge/documents`：分页查询资料及处理状态。
- `GET /api/knowledge/documents/{document_id}`：获取资料详情与解析错误。
- `POST /api/knowledge/documents/{document_id}/reindex`：重新索引资料。
- `GET /api/knowledge/documents/{document_id}/markdown`：读取当前标准 Markdown。
- `PUT /api/knowledge/documents/{document_id}/markdown`：保存 Markdown；候选状态只保存草稿，已生效状态才增量重建索引。
- `POST /api/knowledge/documents/{document_id}/confirm`：确认候选 Markdown，将其转为正式标准文档并启动首次分块和索引。
- `POST /api/knowledge/documents/{document_id}/reconvert`：从源文件生成候选 Markdown；存在人工编辑时必须携带用户确认结果后才能替换。
- `DELETE /api/knowledge/documents/{document_id}`：软删除资料及其索引。
- `GET /api/ai-operations/{operation_id}/sources`：查询一次创作使用的简化来源。
- `GET /api/retrieval-traces/{trace_id}`：在调试模式下获取完整 Retrieval Trace。

领域层增加文档解析、Embedding、知识索引、知识检索和重排序端口。Application 层负责导入编排、增量索引、混合检索、上下文构建和降级决策；具体解析器、模型和索引实现位于 Infrastructure 层。

## 架构说明（Architecture Notes）

系统由资料管理、文档处理、索引服务、检索服务、上下文构建、创作 Agent 和 Trace 服务组成。

资料采用三层存储：源文件位于 `output/knowledge/sources/`，标准 Markdown 位于 `output/knowledge/documents/`，PostgreSQL 保存文档元数据、Chunk、Embedding、检索索引和 Trace。Markdown 上传件直接保存在标准文档目录，不在源文件目录保留重复副本。

索引链路：

```text
PDF / Image / Text / URL / History → 保留源文件或网页快照
→ 解析、OCR 与清洗 → 候选 Markdown
→ 用户查看、编辑并确认 → 正式标准 Markdown
Markdown 上传件 → 正式标准 Markdown
→ 仅从正式标准 Markdown 进行父子分块
→ 子块 BM25 索引 + 子块 Embedding/向量索引
→ 发布新索引版本
```

创作链路：

```text
用户问题
→ RAG 使用决策
→ 查询改写
→ BM25 + 向量检索
→ RRF 融合去重
→ Reranker
→ 证据阈值判断
→ 父块回填与上下文构建
→ 带引用生成或普通模式降级
→ 答案 + 来源 + Trace
```

优先复用现有 PostgreSQL，在同一数据边界内保存资料元数据、Trace、关键词索引和向量索引。LangGraph checkpoint 只保存运行状态，不作为知识库。Agent 负责是否检索和降级决策；检索算法封装在独立服务中，不能散落在 Prompt 或 Agent 节点内。

资料库初始支持数据结构与算法、个人网站搭建两个内容方向，但数据模型不写死领域枚举。资料可通过 metadata 或标签标识领域，未来新增技术方向无需修改检索主流程。

## 测试策略（Testing Strategy）

- 单元测试：解析清洗、OCR 状态、Markdown Front Matter、父子分块、内容哈希、查询改写、RRF、阈值判断、上下文预算和引用映射。
- 数据库集成测试：增量索引、版本切换、软删除、workspace 隔离和 Trace 持久化。
- 检索集成测试：BM25、向量、混合检索与 Reranker 的排序及降级。
- Agent 流程测试：无需 RAG、证据充分、普通模式证据不足、严格模式证据不足四条路径。
- API 测试：上传、URL 导入、Markdown 编辑、重新转换确认、状态查询、重试、删除、来源与 Trace 查询。
- 前端测试：上传状态、错误状态、来源展示、降级提示和严格模式入口。
- 安全测试：跨 workspace 检索隔离、敏感文件拒绝和 URL 导入限制。
- 建立小型标注评测集，分别覆盖算法教学、算法题解、工程算法选择、个人网站选型、搭建、部署和运维问题，用于评估 Recall@K、引用正确率、拒答/降级准确率和回答忠实度。

验收标准 1–10 由导入、转换与索引测试覆盖；11、15 由检索集成测试覆盖；12、16 由引用与 Trace 测试覆盖；13、14 由 Agent 流程测试覆盖；17 由隔离测试覆盖。

## 风险（Risks）

- 私有资料本身错误或过期，会使检索结果看似有依据但结论不可靠。
- 中文分词、代码片段和专业术语会影响 BM25 与分块质量。
- 证据阈值过高会频繁降级，过低会引入弱相关资料。
- Reranker 增加调用延迟和成本，需要超时与降级策略。
- 网页内容的版权、更新和可访问性需要在导入时保留来源信息。
- 父块过大可能挤占上下文，过小则破坏教学内容完整性。
- OCR 或转换错误可能进入 Markdown；低置信度门禁和人工编辑用于降低该风险。
- 人工编辑与源文件重新转换可能冲突，任何覆盖操作都必须由用户确认。
- 更换 Embedding 模型需要重建向量索引，并保留可回滚的旧版本。

## 待确认问题（Open Questions）

无。第一版默认使用普通创作模式；仅在用户单次明确选择时启用严格知识库模式。
