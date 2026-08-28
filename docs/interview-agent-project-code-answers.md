# Agent 项目面试题：基于当前代码的可核验答案

> 核验时间：2026-08-26  
> 核验范围：当前工作区源码、测试、README、迁移文件与 Git 历史。  
> 口径：只回答仓库能够证明的内容；问题中的错误前提会直接纠正。个人动机、职责归属、团队人数以及没有实验记录支持的指标，不替项目编造。

## 先给结论

这是一个从“本地内容采集与 AI 回答工作台”持续演进而来的 Chat-first Agent 应用。当前核心由 FastAPI、PostgreSQL/ParadeDB、pgvector、LangGraph、DeepSeek 兼容 LLM、React/Tiptap 组成，既能采集内容和生成文章，也实现了私有知识库 RAG、多轮分支对话、长期记忆、HITL 和质量评审。

面试题里有一批前提与代码不符：当前项目**没有** Dify 工作流、HyDE、断崖检测、MongoDB、Milvus、Elasticsearch、模型微调或“93.6% 端到端准确率”的实现证据；PDF 图片资产也没有真正完成提取和落盘。面试时应主动纠正，不能顺着题目虚构。

---

## 2. 项目什么时候开始、为什么诞生、架构是什么

### 可核验的时间与演进

- Git 最早提交是 `152fdbe`，时间为 **2026-06-06 13:28:34 +08:00**，提交信息为 `first commit`。
- 首次提交已经包含 Python/FastAPI 后端、React/Vite 前端、知乎采集、回答生成、会话保存和三栏工作台，共 52 个文件。它说明仓库一开始就是一个可运行产品雏形，而不是只有几段实验代码。
- 私有知识库 RAG 的主要提交是 `a891600`，时间为 **2026-08-14 09:39:50 +08:00**。

首版 README 对项目诞生目的的描述很清楚：把站点内容采集、问题筛选、AI 回答生成、人工编辑和本地保存放进一个可视化工作台，减少在爬虫、模型网页、文档编辑器之间来回切换的成本。当前 README 将它进一步定义为“本地内容采集与回答工作台（Chat-first Agent Architecture）”。

注意：代码可以证明首提交时间和产品目标，但不能证明某位候选人的个人开发起止时间或主观动机。面试时建议说“仓库历史显示……”，不要说“我在某月因为某客户需求做了……”，除非你本人能提供真实经历。

### 当前架构

```text
React 19 + Tiptap + TanStack Query + Zustand
                    │ REST / SSE
                    ▼
FastAPI 路由与统一异常处理
                    │
        ┌───────────┴───────────┐
        ▼                       ▼
Chat LangGraph              业务 Service
意图/RAG/工具/HITL/Writer     文档/知识库/评审/发布
        │                       │
        ├──── LLM Registry ─────┤── DeepSeek 兼容 API
        ├──── Embedding/Reranker ┤── 外部兼容服务
        └──── Collector/Parser ──┘── 知乎/小红书/MinerU
                    │
                    ▼
PostgreSQL（ParadeDB + pgvector）
业务表、BM25、向量、记忆、Trace

另有 SQLite：LangGraph checkpoint
另有文件系统：源文件、Markdown、日志、生成图片
```

分层上接近 Ports & Adapters/Clean Architecture：

- `app/api/` 负责 HTTP、Schema 和 SSE；
- `app/services/` 负责用例编排；
- `app/contracts/` 放 DTO、Port 和业务错误；
- `app/infrastructure/` 放数据库、LLM、Embedding、Reranker、采集器、文件和可观测性实现；
- `app/agents/` 放 LangGraph 图、节点、状态与 Prompt；
- 前端按 `chat / knowledge / settings` feature 组织。

证据：`README.md`、`app/server.py`、`app/graph.py`、`app/agents/chat/graph.py`、`app/agents/writer/graph.py`、Git 提交 `152fdbe` 与 `a891600`。

## 3. 是从 0 到 1，还是在基础上增强？为什么先在 Dify 测试？

准确说法是：**仓库历史表现为一个产品从首版工作台持续增强，而不是一次性写成现在的 Agent/RAG 系统。**首提交已有完整前后端雏形，后续才逐步加入多轮对话、LangGraph、SSE、平台工具、私有知识库、长期记忆和多 Agent 写作。

但仅凭当前仓库，不能证明组织层面“绝对从 0 到 1”，也不能证明它是否参考过某个内部系统。仓库远端是项目自己的 GitHub 地址，没有发现 fork/upstream 证据。

关于 Dify：当前文件和 Git 历史中没有 Dify 工作流、DSL、导出文件、接口调用或设计记录，因此**不能回答“为什么先在 Dify 测试”**。如果候选人确实做过 Dify PoC，应基于本人真实经历补充；不能把它说成代码事实。

---

## 4. 从文档导入到 LLM 生成，完整流程是什么

这里要分成“离线摄取/建索引”和“在线问答”两条链路。文档导入后不会立刻让 LLM 写答案，而是先转成可检索索引；用户提问时才检索并调用回答模型。

### A. 离线摄取与建索引

```text
上传 PDF/MD/TXT 或扫描 pending 目录
  → 流式写入临时文件，校验 2GB 上限
  → SHA-256 去重
  → 注册 source_file + ingestion_job
  → worker 以数据库租约领取任务
  → 按类型解析
      MD：直接发布 Markdown，进入索引
      TXT：解码为候选 Markdown，等待人工确认
      PDF：逐页拆成单页 PDF → MinerU；失败则本地 PyMuPDF 提取
  → 单页结果持久化并按页码合并
  → 计算转换置信度，生成候选 Markdown
  → 人工检查/编辑/确认
  → 标题层级 + 父子分块
  → 只对子块批量生成 1536 维 Embedding
  → 父块、子块、标题路径、向量写入 PostgreSQL
  → 切换 active_index_version，旧版本软删除
```

关键设计点：

1. 上传采用固定缓冲区流式写盘和原子 rename，避免把 2GB 文件一次性放进内存。
2. SHA-256 用于同 workspace 的内容去重。
3. 摄取任务、页级任务、重试次数、租约、心跳和进度都落 PostgreSQL，进程重启后可恢复。
4. PDF 默认逐页处理；每页最多重试 3 次。成功页保存成单独 `.md`，最后按页码合并，并插入 `<!-- source-page: N -->` 标记。失败页会放人工补充占位文本。
5. PDF/TXT 先进入候选 Markdown，人工确认后才建索引，避免 OCR 噪声直接污染知识库。
6. Markdown 变更使用内容 Hash 和 `active_index_version` 管理索引版本。

主要证据：`app/services/rag/ingestion_service.py`、`app/infrastructure/files/source_files.py`、`app/infrastructure/files/pdf_pages.py`、`app/services/rag/document_service.py`、`app/services/rag/indexing_service.py`。

### B. 在线检索与回答生成

```text
用户问题
  → Chat Graph：guard
  → route_intent
  → knowledge_decision
  → 查询改写
  → 查询 Embedding
  → BM25 Top 20 + 向量 Top 20
  → RRF(k=60) 融合
  → 取 Top 8 交给 Cross-Encoder rerank
  → 证据阈值 0.55
  → 子块命中后回填父块
  → 按 6000 token 预算组上下文并生成 [S1] 引用
  → 注入 system prompt、对话历史、分支摘要和长期偏好
  → LLM 生成回答
  → SSE 流式返回并持久化消息与检索 Trace
```

BM25 与向量检索不是二选一：BM25 擅长精确术语、编号和关键词，向量检索擅长语义改写；RRF 用排名而非原始分数融合两路结果，避免 BM25 分数和 cosine 分数不可比。Reranker 再对“问题—候选段落”做更精细的相关性判断。

证据：`app/services/rag/retrieval_service.py`、`app/agents/chat/nodes/retrieve_knowledge.py`、`app/agents/chat/nodes/chat.py`。

---

## 5～9. MinerU、PDF 图片提取与图片格式

这组题最需要纠正错误前提。

### PDF 是怎么交给解析器的

当前主摄取链路不是先把 PDF 页面渲染成 PNG/JPEG。`PdfPageWorkspace.extract_single_page()` 使用 PyMuPDF 的 `insert_pdf()`，从原 PDF 中复制一页，生成一个**单页 PDF 文件**；随后读取其 PDF bytes，交给 `_parse_pdf_to_markdown()`。

如果配置了 MinerU：

1. 向 MinerU `/file-urls/batch` 申请预签名上传地址；
2. 通过 PUT 上传 PDF bytes；
3. 轮询解析状态；
4. 直接读取响应中的 Markdown，或者下载结果 ZIP 并读取第一个 `.md` 文件。

因此它不是把 PDF 交给本项目的普通 Chat LLM 来“看图提取”，而是交给 MinerU 专用解析服务；配置中的模型版本默认为 `vlm`。MinerU 不可用时，本地路径使用 `pymupdf4llm.to_markdown()`，再失败才使用 PyMuPDF `page.get_text()` 提取纯文本。

### 当前代码有没有真正提取图片

**没有。**这是代码级结论：

- ZIP 结果只遍历并读取 `.md`；没有解压 PNG、JPEG、WebP 等资源；
- `KnowledgeStorage` 只保存原始源文件、候选 Markdown 和正式 Markdown，没有文档图片目录或图片资产模型；
- 本地 `pymupdf4llm.to_markdown()` 没有传 `write_images`、`image_path` 等图片导出参数；
- 知识库摄取代码没有任何 `extract_image`、图片格式转换或图片对象存储逻辑。

所以问题 7“图片是什么格式”在当前项目里没有答案：项目没有落盘图片，也没有规定图片 MIME/扩展名。

问题 9 所说的 Markdown 位置标识需要区分两类：

- `<!-- source-page: 3 -->` 是本项目自己插入的**页码锚点**，不是图片地址；
- 如果 MinerU 返回 `![](images/xxx.jpg)` 一类相对链接，当前代码只保留 Markdown 文本，没有把 ZIP 中对应的图片取出并发布到可访问路径，因此链接很可能失效。

这不是一个“可以包装成已完成”的能力，而是当前实现缺口。完整方案至少需要：安全解压结果包、限制文件类型/大小和路径穿越、保存图片资产、重写 Markdown 相对路径、为图片建立文档/页码关联，并决定图片是否参与多模态检索。

证据：`app/infrastructure/files/parsers.py:137`、`app/infrastructure/files/parsers.py:235`、`app/infrastructure/files/pdf_pages.py:27`、`app/infrastructure/database/repositories/knowledge_storage.py`。

---

## 12～17. 文档切分为什么这样设计，Chunk Size 怎么设置

### 先纠正题目中的描述

当前代码不是“标题切分 + RecursiveCharacterTextSplitter + 短文本合并”。真实实现是：

1. **Markdown 标题结构切分**：识别 `#` 到 `######`，维护标题栈和 `heading_path`；代码围栏里的 `#` 不当标题。
2. **Section 内父块聚合**：同一标题路径下按空行形成段落，再按 `parent_max_tokens` 聚合；父块绝不跨标题边界。
3. **父块内子块切分**：优先按中英文句号、问号、感叹号、分号和换行切句；按 `child_max_tokens` 聚合，加入尾部 overlap；只有单句本身超长时才硬切。

没有使用 LangChain 的 `RecursiveCharacterTextSplitter`，也没有“短于某个最小值就向前/向后合并”的显式短文本合并算法。所谓“短文本合并”最多只能对应“多个段落在不超过父块上限时聚合到同一父块”，不能把它描述成独立策略。

### 为什么要先按标题切

标题是文档天然的语义边界。若把“退款规则”和“权限管理”拼进同一块，即使 token 数合适，Embedding 也会混合两个主题，检索结果难解释。标题路径还可以保留 `第一章 > 退款 > 特殊情况` 这样的层级，供检索结果展示和 Trace 使用。

“标题内部”指的是：某个标题出现以后，到下一个标题出现以前，属于当前标题路径的正文。例如：

```markdown
# 第一章
第一章导语

## 小节 A
小节 A 正文
```

会形成 `第一章` 和 `第一章 > 小节 A` 两个 Section。长度切分只在各自 Section 内进行，不跨 Section。

### 为什么要父子块

- **子块用于召回**：更短、更聚焦，Embedding 和 BM25 更容易命中具体问题；
- **父块用于回答上下文**：命中子块后回填父块，让 LLM 获得完整解释、条件和例外；
- 这解决了“检索需要小颗粒、生成需要大上下文”的矛盾。

### 当前参数

| 参数 | 当前默认值 | 用途 |
|---|---:|---|
| `parent_max_tokens` | 1200 | 回填给 LLM 的父上下文上限 |
| `child_max_tokens` | 350 | 建向量、BM25 检索的子块上限 |
| `overlap_tokens` | 50 | 保留相邻子块语义连续性 |

项目使用确定性近似 token 估算：CJK 字符约 1 token，其他字符约 0.25 token。它不是精确 tokenizer，因此这些数值是工程预算，不等于模型真实 token 数。

代码中**没有 500 的 Chunk Size**，也没有实验记录证明“500 是最优值”。面试时不能说“我们经过评测选择 500”。

更深一层看，`KnowledgeSettings` 虽然允许通过环境变量配置父块和子块大小，但 `IndexingService` 当前直接调用 `ParentChildChunker()`，没有把 settings 传进去；所以环境变量配置实际上不会影响建索引，仍使用类默认值。这是配置接线缺口。

### 为什么块太大可能检不出来，块小反而能检出来

这是通用检索原理，不是本仓库已有的对比实验结论：

- 大块包含多个主题，向量是多种语义的平均，目标句子的信号被稀释；
- BM25 中无关词增多，目标关键词的相对贡献下降；
- Reranker 面对长且混杂的候选，问题对应的局部证据占比变小；
- 小块语义更单一，召回更准，但过小会丢失条件、主语和例外。

因此不能简单追求越小越好。本项目用“小子块召回 + 大父块回填 + overlap”平衡召回率与上下文完整性。

证据：`app/services/rag/chunking.py`、`app/services/rag/indexing_service.py:56`、`app/config/runtime.py:137`、`tests/knowledge/test_markdown_chunking.py`。

---

## 18～19. 知识库里存什么文件，文档有多大

当前受管目录摄取真正支持的扩展名只有：

- `.pdf`
- `.md`
- `.markdown`
- `.txt`

另有 URL 导入接口：安全抓取 HTML 后清理脚本、样式、导航等，再转 Markdown。`SourceType` 枚举中虽然预留了 `image/history/material`，但不能据此声称图片文件已经支持摄取；实际扩展名白名单不包含图片。

存储层分三类：

1. 原始源文件：在 `pending / processing / recognized / archived / failed` 状态目录间原子移动；
2. 候选/正式 Markdown：`{document_id}.candidate.md` 与 `{document_id}.md`；
3. PostgreSQL 元数据和 Chunk：标题、来源、Hash、状态、父子块、标题路径、Embedding、索引版本、Trace。

代码不能证明真实业务文档“通常有多大”。能证明的是工程边界：单个受管源文件默认上限 **2GB**；旧的直接上传配置另有 50MB 字段，但当前上传路由实际使用 2GB 的 `max_source_file_bytes`。PDF 解析器还保留 150 页/150MB 分卷能力；当前异步摄取主链路则是逐页生成单页 PDF。

证据：`app/services/rag/ingestion_service.py:32`、`app/config/runtime.py:137`、`app/infrastructure/database/models/knowledge.py`。

---

## 20～26. HyDE、问题大小判断、Prompt 和“断崖检测”

### 当前实现不是 HyDE

HyDE 的典型做法是：先让模型生成一段“假设性答案/文档”，再对这段假设文档做 Embedding，用它去召回真实文档。当前代码没有这一步。

本项目实现的是**查询改写**：Prompt 要求提取核心关键词、删除语气词、保留实体，并只输出改写后的查询。随后改写查询同时用于 BM25 和查询向量化。

示意如下，注意改写结果由 LLM 动态产生：

```text
用户问题：合同解除以后，保证金到底多久能退？
查询改写：合同解除 保证金 退还期限
后续：对改写查询做 Embedding，同时执行 BM25，再融合和重排
```

若是 HyDE，中间产物会更像“合同解除后，保证金应当在……日内退还……”的一段假设答案；当前 Prompt 明确没有要求生成答案，因此不能把查询改写包装成 HyDE。

查询改写 Prompt 的核心内容是：

```text
请将用户的问题改写为更适合在知识库中进行全文和向量检索的查询语句，
提取核心关键词，去除多余语气词，保留原始问题中的关键实体。
只输出改写后的查询，不要输出任何解释。
用户问题：{{ query }}
```

### 系统怎样判断是否需要检索

当前不是按“问题偏差大/小”判断，也不计算问题与知识库的预先距离：

- `off`：不检索；
- `strict`：强制检索；
- `normal`：空输入、纯寒暄、长度不超过 2 的短消息跳过，其余实质问题默认检索。

真正的相关性判断发生在召回后：Reranker 对 Top 8 打 `[0,1]` 分，只要有一个分数达到 0.55 就认为有证据。严格模式下不达阈值则拒答；普通模式可降级用通用知识回答。

### 没有“断崖检测算法”

代码没有比较相邻排序分数的差值、比值、拐点或最大 gap，也没有 elbow/knee/cliff 算法。当前证据判定只是：

```python
any(score >= threshold for score in scores)
```

所以问题 25～26 中“在哪一步完成断崖检测、怎样判断断崖式数据”的前提不成立。最接近的能力是 Reranker 的固定阈值判定，但固定阈值与分数断崖是两种算法，不能混为一谈。

证据：`app/agents/_shared/prompts/knowledge/query_rewrite.yml`、`app/agents/chat/nodes/knowledge_decision.py`、`app/services/rag/retrieval_service.py:101`。

---

## 27～28. 多轮对话怎么实现，历史很多会不会丢

当前不是写 MongoDB，而是三层状态协作：

1. **PostgreSQL 是业务事实源**：`chats` 和 `messages` 表保存消息；`parent_message_id` 构成邻接表消息树，支持编辑旧问题后产生分支。
2. **SQLite 是 LangGraph 执行状态**：`AsyncSqliteSaver` 写入 `output/agent_checkpoints.sqlite`，用于同一分支增量续跑和 HITL `interrupt()/resume`。
3. **PostgreSQL 长期上下文**：`branch_summaries` 保存分支滚动摘要；`user_memories` 保存可语义检索的用户偏好和工作习惯。

每轮执行时，以 `{chat_id}_{branch_root_message_id}` 作为 LangGraph `thread_id`：

- 有 checkpoint：只把当前用户消息作为增量传入，LangGraph reducer 合并；
- 没有 checkpoint：从 PostgreSQL 回溯当前分支的完整消息路径，重建图输入。

当历史超过模型上下文预算时，不删除数据库记录，而是由 `ContextComposer`：

- 从最旧消息开始裁剪；
- 优先保留最近两轮；
- 最后一条用户消息不能丢；
- 注入滚动摘要补偿早期语义；
- 单条过长时按剩余预算截断。

所以应区分“存储丢失”和“本轮不再把全文发给模型”：数据库历史原则上保留，但模型输入会有预算裁剪，这是必要的成本和注意力控制。

当前还有两个真实风险：

- `GET /api/chats/{chat_id}/messages` 默认只返回按时间升序的前 100 条，超过 100 条的后续消息不会出现在该列表响应中；它们没有从数据库删除，但前端读取可能看不到最新消息。
- `thread_id` 使用分支根消息。若两个中途分叉共享同一个最早根消息，可能复用同一 checkpoint，兄弟分支隔离不够严格。

证据：`app/context.py`、`app/services/chat_service.py`、`app/services/context/composer.py`、`app/services/context/summary_updater.py`、`app/infrastructure/database/models/chats.py`、`app/server.py:85`。

---

## 29～32. “93.6% 准确率”、测试集、QA 统计和评估指标

### 93.6% 不能从仓库得到

全仓没有 `93.6`、对应评测报告、运行产物或计算代码，因此不能声称“端到端专业问答准确率达到 93.6%”。

项目确实有检索评测框架，但它不能支撑这个数字：

- 数据集加载器定义了 JSONL Schema；
- 当前仓库缺少 README 和测试引用的 `docs/evaluations/private-knowledge-rag.jsonl`；
- Runner 只提供 `DeterministicBackend`，它直接把标注的相关文档作为预测结果返回，目的是测试指标聚合逻辑，不是真实检索或真实 LLM 评测；
- 没有端到端回答正确性、忠实度或人工专家评分流水线。

### 测试集能证明什么

代码要求每条检索样本至少包含：

- `id`
- `domain`
- `question`
- `relevantDocumentIds`
- `relevanceGrades`
- `expectedMode`
- `expectedRefusal`
- `expectedCitationDocumentIds`

这说明设计上希望覆盖可回答问题、无证据问题、normal/strict 模式、相关文档等级和引用预期。但实际 JSONL 不在仓库，无法核验样本来源、专家标注流程、去重、难例比例、训练/测试污染或领域分布，也无法回答“怎么整理出来”的事实过程。

仓库也没有“统计 QA 对话数据”的实现或报表，不能回答问题 31。

### 已实现的指标

| 指标 | 含义 | 适用层 |
|---|---|---|
| Recall@5 / Recall@10 | 相关文档有多少进入前 K | 召回覆盖率 |
| MRR | 第一个相关文档排名的倒数 | 首个正确结果是否靠前 |
| NDCG@10 | 考虑多级相关性和位置折损 | 排序质量 |
| Citation Accuracy | 引用文档是否在允许引用集合中 | 引用合法性 |
| Strict Refusal Accuracy | 严格模式无证据时是否拒答 | 安全拒答 |
| Normal Fallback Accuracy | 普通模式无证据时是否正确降级 | 降级行为 |
| P50 / P95 Latency | 检索预测延迟分位数 | 性能 |

这些是检索/行为指标，不等于“最终回答准确率”。若要可信地给出端到端百分比，还需冻结真实测试集、运行真实检索与生成后端、定义答案正确性和证据忠实度 rubric、做专家双人标注与分歧仲裁，并报告置信区间和分领域结果。

证据：`app/evaluation/datasets/retrieval.py`、`app/evaluation/metrics/retrieval.py`、`app/evaluation/runners/retrieval.py`、`tests/knowledge/test_retrieval_quality.py`。

---

## 33～34. LangChain 和 LangGraph 的区别，什么时候选哪个

根据当前 LangGraph 官方文档：LangGraph 是偏底层的状态化编排框架，重点是 durable execution、streaming、human-in-the-loop 和长时间运行；LangChain 提供更高层的模型/工具集成、可组合组件和常见 Agent 抽象，而且 LangChain 的 Agent 抽象本身构建在 LangGraph 之上。LangGraph 可以使用 LangChain 组件，但不强制依赖 LangChain。

简单区分：

| 需求 | 更适合 |
|---|---|
| Prompt → 模型 → Parser，步骤固定、无复杂恢复 | LangChain 组件或直接 SDK |
| 快速使用预置工具调用 Agent | LangChain 高层 Agent |
| 多分支、循环、显式 State、并行任务 | LangGraph |
| HITL 暂停/恢复、checkpoint、长任务容错 | LangGraph |
| 需要精确控制每个节点、边和失败语义 | LangGraph |

本项目两者一起用：节点内部用 `langchain_core.messages`、ChatModel 和 `bind_tools()`；节点之间用 LangGraph `StateGraph`、条件边、ToolNode、checkpoint 和 interrupt 编排。

官方文档：[LangGraph overview](https://docs.langchain.com/oss/python/langgraph/overview)。

---

## 35～39. 问答节点怎样编排、是否 14 个节点、索引是否也在图里、API 和 Query Graph

### 当前 Chat Graph

当前工作区的 Chat Graph 有 **15 个显式节点**，不是 14 个：

```text
START
  → guard
  → route_intent
      ├─ parse_url → normalize_and_persist → build_response → END
      ├─ writer → END
      ├─ platform_collect → END
      └─ knowledge_decision
          ├─ 不检索 → chat_memory → chat
          └─ retrieve_knowledge
              ├─ 有证据 → answer_preference_memory → chat
              ├─ 普通模式无证据 → chat_memory → chat
              └─ 严格模式无证据 → strict_refusal → END

chat
  ├─ 无 tool call → END
  └─ chat_tools → hitl_decision → chat
```

15 个节点是：`guard`、`route_intent`、`knowledge_decision`、`retrieve_knowledge`、`chat_memory`、`answer_preference_memory`、`strict_refusal`、`writer`、`platform_collect`、`hitl_decision`、`chat`、`chat_tools`、`parse_url`、`normalize_and_persist`、`build_response`。

Writer 不是这 15 个节点全部展开在同一张图里，而是一张独立编译的 **12 节点 Writer Graph**，在 Chat Graph 中作为 `writer` 节点调用。Writer Graph 包含 guard、记忆检索、文档生成/精修/重写，以及 `generate_plan → assign_tasks → research → write → review → memory → finalize` 复合创作链路。

### 建索引与查询是否都在一个 LangGraph

不是。

- 文档转换、切分、Embedding 和索引写入由 `IngestionExecutor`、`DocumentService`、`IndexingService` 完成；确认文档后以后台任务触发，不属于 Chat Graph。
- 在线检索作为 Chat Graph 的 `retrieve_knowledge` 节点执行。

这种分离是合理的：索引构建是耗时、可重试、面向文档生命周期的离线任务；查询是低延迟、面向每轮对话的在线任务。把二者塞进同一 Query Graph 会让状态、超时、重试和资源模型互相污染。

### 当前有多少 API

通过导入当前 FastAPI app 并统计已注册路由，当前有：

- **89 个 `/api/*` HTTP 业务端点**；
- 另有 FastAPI 自动生成的 4 个 OpenAPI/Docs 路由；
- 合计 93 个带 HTTP methods 的路由对象。

`/api/*` 按首段分组：

| 分组 | 数量 | 分组 | 数量 |
|---|---:|---|---:|
| documents | 17 | settings | 14 |
| knowledge | 12 | chats | 8 |
| memories | 7 | opportunities | 6 |
| task-plans | 6 | publishing | 6 |
| multi-agent | 5 | source-items | 2 |
| prompts | 2 | health/config/ai-operations/retrieval-traces | 各 1 |

不要死背“89”作为长期不变的产品指标；新增或删除路由后它会变化。面试更重要的是能按聊天、文档、知识库、记忆、任务计划、多 Agent 和发布域解释 API 边界。

证据：`app/agents/chat/graph.py:68`、`app/agents/writer/graph.py:29`、`app/server.py:213`、`app/api/routes/`。

---

## 40. 为什么 Milvus 和 Elasticsearch 都用了

当前项目两者都没用。真实方案是把两类检索能力收敛在一个 PostgreSQL/ParadeDB 实例中：

- ParadeDB `pg_search` 的 BM25 索引负责全文检索；
- `pgvector vector(1536)` + HNSW 负责向量检索；
- 业务元数据、权限字段、文档、Chunk 和 Trace 也在 PostgreSQL；
- RRF 在应用层融合两路排名。

这样做的优势是部署简单、事务和租户过滤一致、不需要同步 ES 与向量库的多份数据；代价是超大规模向量或全文场景的水平扩展能力不如专用集群，需要在真实数据量上验证。

证据：`docker-compose.yml`、`migrations/versions/20260722_knowledge_rag.py`、`migrations/versions/20260726_bm25_chinese_tokenizer.py`、`app/services/rag/retrieval_service.py`。

---

## 41～45. 模型训练做了什么、为什么训练、提升多少、训练数据怎么做、为什么不用 RAG

当前仓库没有训练脚本、LoRA/SFT 配置、训练数据转换器、训练 checkpoint、实验记录或模型对比报告，因此问题 41～44 不应回答成“项目做过模型训练”。项目使用的是外部模型能力：

- DeepSeek 兼容 Chat LLM；
- OpenAI 兼容 Embedding；
- BAAI Cross-Encoder 或 DashScope VL Reranker 服务；
- MinerU PDF 解析服务。

“为什么不用 RAG”的前提也相反：项目已经实现了完整 RAG。选择 RAG 而不是微调来注入私有手册，主要是因为知识可更新、可追溯引用、可按 workspace/owner 隔离，并且无需每次资料变化都重新训练。微调更适合改变模型的稳定行为、格式和领域表达习惯，不适合承担频繁变化的事实存储。

本项目也没有把 RAG 用于所有消息：纯寒暄和过短输入会跳过；普通模式证据不足时允许降级；严格模式要求达到证据阈值，否则拒答。这体现的是“按问题选择检索”，而不是“RAG 或模型二选一”。

---

## 不应在面试中虚构的内容

以下题目缺少仓库证据，除非候选人能用本人真实经历补充，否则建议明确说“代码无法证明”：

- 问题 10：这一块由自己还是同事完成；
- 问题 11：团队人数和个人职责；
- Dify PoC 的原因和结果；
- 真实文档平均大小、业务数据量；
- HyDE 和断崖检测的线上效果；
- 93.6% 端到端准确率；
- QA 数据统计过程；
- 任何模型训练、训练集制作和微调提升数字。

---

## 关键代码证据索引

- 项目入口与依赖装配：`app/server.py`
- Chat Graph：`app/agents/chat/graph.py`
- Writer Graph：`app/agents/writer/graph.py`
- PDF/MinerU：`app/infrastructure/files/parsers.py`
- PDF 逐页工作区：`app/infrastructure/files/pdf_pages.py`
- 摄取任务：`app/services/rag/ingestion_service.py`
- 标题与父子分块：`app/services/rag/chunking.py`
- 索引构建：`app/services/rag/indexing_service.py`
- 混合检索：`app/services/rag/retrieval_service.py`
- Query 改写 Prompt：`app/agents/_shared/prompts/knowledge/query_rewrite.yml`
- 多轮输入与 checkpoint：`app/context.py`
- 上下文预算：`app/services/context/composer.py`
- 分支摘要：`app/services/context/summary_updater.py`
- 长期记忆：`app/services/memory/service.py`
- 检索评测：`app/evaluation/`
- 数据库和索引迁移：`migrations/versions/20260722_knowledge_rag.py`

## 本次核验

与本文核心结论相关的测试已执行：

```text
36 passed in 1.56s
```

覆盖 Markdown 父子分块、检索阈值/RRF 基础逻辑、检索指标、上下文裁剪、checkpoint 恢复和 Writer Graph。未运行依赖真实 PostgreSQL、真实 MinerU、真实 Embedding/Reranker/LLM 的网络端到端测试，因此本文不据此宣称线上准确率或真实服务效果。
