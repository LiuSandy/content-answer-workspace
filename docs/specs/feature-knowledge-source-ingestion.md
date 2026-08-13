# RAG 源文件异步识别与持久化任务设计

**日期：** 2026-08-12
**状态：** 已确认并实施
**范围：** 源文件发现、校验、去重、异步识别和候选 Markdown 生成

## 1. 背景

当前知识库文件必须通过前端上传，并在上传请求内同步完成 PDF 或文本到 Markdown 的转换。批量文件会导致请求等待时间长；系统也没有可恢复的识别任务、阶段进度或源目录扫描能力。

本设计引入统一的源文件摄取管道。用户既可以从前端上传，也可以直接将文件放入源文件目录。系统在后端启动时自动检查源目录，并允许用户从前端主动触发检查。识别任务、状态和进度持久化到数据库；页面刷新不丢失状态，后端异常终止后可在重启时恢复任务。

本期只改造“发现源文件到生成候选 Markdown”的阶段。候选 Markdown 的预览、编辑、人工确认、正式 Markdown 保存、分块、Embedding、索引和 RAG 检索保持现有流程。

## 2. 已确认约束

- 使用 FastAPI 进程内持久化任务执行器，不引入 Redis 或 Celery。
- 后端启动时自动扫描一次，前端提供“检查源文件”按钮。
- 默认同时识别 2 个文件，通过环境变量配置；本期不提供配置页面。
- 任务不依赖请求或页面生命周期；后端重启后恢复未完成任务。
- 递归扫描子目录，并在状态目录迁移时保留相对目录结构。
- 第一阶段支持 PDF、Markdown、纯文本；其他格式进入失败状态并记录原因。
- 所有进入 `pending/` 的文件执行相同的格式校验和内容哈希去重逻辑。
- 重复文件直接进入 `failed/`，不复用已有识别结果，也不继续后续处理。
- Markdown 跳过识别和人工确认，直接进入现有正式 Markdown 与索引流程。
- PDF 和 TXT 识别成功后生成候选 Markdown，保持现有人工确认门禁。
- 本期不增加批量确认，确认及其后续阶段保持不变。

## 3. 总体架构

```text
前端上传 ───────────┐
                    ├→ pending 目录
启动时自动扫描 ─────┤
                    └→ 统一扫描服务
前端“检查源文件” ───┘
                         ↓
                文件登记、格式校验、哈希去重
                         ↓
                 数据库持久化识别任务
                         ↓
             识别执行器，默认并发 2
                         ↓
        PDF/TXT → 候选 Markdown → 待确认
        Markdown → 正式 Markdown → 原索引流程
```

前端上传、启动扫描和手动扫描仅负责将文件送入统一管道或触发扫描。格式校验、内容哈希、去重、文件登记和任务创建必须复用同一套应用服务。

## 4. 源文件目录

### 4.1 独立根目录

新增独立于现有内部源文件存储的目录：

```text
output/knowledge/source-files/
├── pending/
├── processing/
├── recognized/
├── archived/
└── failed/
```

现有 `output/knowledge/sources/` 是按知识文档 UUID 保存上传源文件的内部目录，不复用为用户投放目录。

新增环境变量：

```text
KNOWLEDGE_SOURCE_FILES_DIR=output/knowledge/source-files
```

### 4.2 状态目录职责

- `pending/`：前端上传或用户直接投放的待检查文件；扫描服务只从这里发现新任务。
- `processing/`：已经通过登记和去重、正在排队或识别的文件。
- `recognized/`：PDF/TXT 已生成候选 Markdown，知识文档处于 `awaiting_confirmation`。
- `archived/`：Markdown 快速通道接收完成，或 PDF/TXT 候选 Markdown 已由用户确认。该状态只表示源文件摄取阶段结束，不保证索引成功。
- `failed/`：格式不支持、内容重复、文件损坏或识别失败；数据库保存结构化失败原因。

### 4.3 相对目录与迁移

系统递归扫描 `pending/`，并在迁移时保留相对目录：

```text
pending/技术资料/算法.pdf
→ processing/技术资料/算法.pdf
→ recognized/技术资料/算法.pdf
→ archived/技术资料/算法.pdf
```

原始相对路径持久化到数据库，可作为资料分类元数据。所有状态目录位于同一根目录，优先通过原子重命名完成状态迁移。

目标目录已有同名文件时不得覆盖。系统为实际文件名附加源文件记录的短 ID，同时保留原始文件名和原始相对路径，例如：

```text
failed/技术资料/算法--a31f92.pdf
```

### 4.4 上传完整性与扫描安全

前端上传先写入不可扫描的临时文件，完整写入并校验大小后，再原子重命名到 `pending/`。扫描器忽略隐藏文件、临时后缀文件、符号链接和状态目录之外的文件。

用户直接复制到 `pending/` 的文件必须通过稳定性检查：连续两次观察到文件大小和修改时间不变后才登记，避免读取尚未复制完成的大文件。

### 4.5 统一入口

- 上传接口：安全写入 `pending/`，然后调用统一扫描服务，不同步执行识别。
- 服务启动：先恢复和对账，再调用统一扫描服务。
- 前端按钮：调用统一扫描服务。
- 多个入口并发触发时，必须通过数据库原子操作保证同一文件只登记一次。

## 5. 文件类型分流

### 5.1 PDF 与 TXT

```text
pending → processing → recognized / awaiting_confirmation
```

识别成功后生成候选 Markdown，等待现有前端逐份预览、编辑和确认。确认成功后，源文件从 `recognized/` 移至 `archived/`，后续索引流程不变。

### 5.2 Markdown

```text
pending → processing → archived → indexing → available
```

`.md` 和 `.markdown` 文件跳过 OCR、文本识别、候选 Markdown 和人工确认，直接保存为正式 Markdown，并进入现有异步索引流程。

### 5.3 不支持的格式

不支持的格式也必须被登记，随后移动到 `failed/`。任务记录失败阶段为格式校验，并保存稳定错误码和用户可读原因。不自动重复扫描；只有文件再次进入 `pending/` 时才重新执行相同流程。

## 6. 内容去重规则

所有进入 `pending/` 的文件均计算 SHA-256，并在当前 workspace 内查询尚未删除的相同 `source_content_hash`。

发现重复时：

- 源文件移动到 `failed/`；
- 文件记录和任务记录均标记为 `failed`；
- 失败阶段为 `deduplication`；
- 错误码为 `duplicate_source`；
- 错误原因包含已有资料标题，并关联已有知识文档 ID；
- 不生成候选 Markdown；
- 不执行 OCR、分块或索引。

文件来自 `failed/`、`recognized/` 或 `archived/` 并被再次放入 `pending/` 时，不享有特殊重试语义，仍执行完全相同的内容去重规则。改名或改变目录不影响去重结果。

现有应用层查询式去重需要补充数据库级原子约束或等价的冲突处理，避免两个相同文件并发登记时创建重复资料。

## 7. 配置

```text
KNOWLEDGE_SOURCE_FILES_DIR=output/knowledge/source-files
KNOWLEDGE_INGEST_CONCURRENCY=2
```

`KNOWLEDGE_INGEST_CONCURRENCY` 必须为正整数，默认值为 2。本期不提供前端配置页面。

## 8. 持久化数据模型

### 8.1 `knowledge_source_files`

一条记录表示一个被系统发现或上传的物理源文件，保存 workspace、owner、入口类型、原始文件名、原始/当前相对路径、扩展名、大小、SHA-256、文件状态、关联知识文档、失败代码和失败原因。

文件状态为 `pending / processing / recognized / archived / failed`。数据库是状态权威来源，目录位置是物理投影；启动时执行对账。

### 8.2 `knowledge_ingestion_jobs`

一条记录表示一次可恢复的摄取任务，保存源文件 ID、任务状态、阶段、实际进度、checkpoint、重试次数、执行器租约、心跳、错误以及开始/完成时间。

任务状态为 `queued / running / succeeded / failed`。任务阶段至少覆盖 `discovered / recovering / preparing / parsing / saving_candidate / saving_markdown / dispatching_index / completed / failed`。

源文件、识别任务和知识文档状态彼此独立。例如 PDF 已完成识别、等待确认时分别是：

```text
source file = recognized
ingestion job = succeeded
knowledge document = awaiting_confirmation
```

## 9. 执行器、租约与恢复

- FastAPI lifespan 启动进程内执行器，worker 数由 `KNOWLEDGE_INGEST_CONCURRENCY` 决定。
- worker 使用 `FOR UPDATE SKIP LOCKED` 原子领取最早的 queued 任务。
- running 任务保存 `lease_owner`、`lease_expires_at` 和 `heartbeat_at`；长时间解析期间独立续租。
- 服务启动和空闲轮询时，将租约过期的 running 任务恢复为 queued，并增加 retry count。
- 当前阶段无法断点续做时允许幂等重做该阶段，但已持久化进度不因页面刷新清零。
- 启动时检查 `processing/` 中没有数据库记录的孤儿文件，将其退回 `pending/` 再扫描。
- 单个文件失败只终止自己的任务，不终止其他 worker。

## 10. API 与前端

- `POST /api/knowledge/documents`：完整写入 pending、登记持久化任务并立即返回源文件 ID，不等待解析。
- `POST /api/knowledge/source-files/scan`：递归检查 pending，返回发现、入队、重复和失败数量。
- `GET /api/knowledge/source-files`：返回源文件及最新任务状态和进度。
- `GET /api/knowledge/documents`：现有文档响应附带对应源文件和最新摄取任务。
- `POST /api/knowledge/documents/{id}/confirm`：保持原确认逻辑，同时将受管源文件从 recognized 移至 archived。

前端资料库提供“检查源文件”按钮，活动任务每 2 秒轮询数据库状态。文档列表展示阶段、真实进度和失败原因；没有创建知识文档的重复/不支持文件也必须出现在失败列表中。

## 11. 错误规则

- `unsupported_file_type`：格式不支持。
- `file_too_large`：超过配置上限。
- `duplicate_source`：同 workspace 已存在相同内容的未删除知识文档。
- `recognition_failed`：读取、PDF 转换或候选保存失败。

失败记录不得包含密钥、Cookie 或完整内部异常堆栈。详细堆栈只进入后端日志。

## 12. 验收标准

1. 前端上传和目录投放使用相同摄取服务和状态机。
2. 后端启动自动扫描，前端按钮可主动扫描。
3. 递归扫描并在目录迁移时保留相对层级。
4. 默认最多并行识别 2 个文件，环境变量可调整。
5. 页面刷新和服务重启后从数据库恢复状态、阶段和进度。
6. 重复与不支持文件进入 failed 并显示明确原因，不执行后续识别。
7. PDF/TXT 成功生成候选 Markdown 并进入 awaiting_confirmation。
8. Markdown 跳过识别和确认，保存正式 Markdown 后触发现有索引流程。
9. PDF/TXT 确认后源文件进入 archived，现有确认和索引行为保持不变。
10. 单个任务失败不影响其他任务继续执行。
