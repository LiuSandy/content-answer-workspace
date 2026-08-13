# RAG 源文件异步识别 Implementation Plan

> 对应规格：[feature-knowledge-source-ingestion.md](../specs/feature-knowledge-source-ingestion.md)

## Goal

将现有“前端上传并在请求内同步解析”的知识文件入口改造成统一、持久化、可恢复的源文件摄取管道。支持后端启动扫描和前端主动扫描；默认并发识别 2 个文件；刷新页面或后端重启后状态和进度不丢失。

## Scope

本计划只改造源文件发现、格式校验、内容去重、异步识别和候选 Markdown 生成。PDF/TXT 之后仍进入现有候选确认流程；Markdown 仍跳过确认并进入现有索引流程。既有编辑、确认、分块、Embedding、索引和检索逻辑不重写。

## Architecture

- `output/knowledge/source-files/{pending,processing,recognized,archived,failed}` 保存摄取阶段的物理文件。
- PostgreSQL 新增源文件与识别任务表，数据库为状态权威来源。
- `SourceIngestionService` 负责递归扫描、稳定性判断、登记、格式校验、哈希去重和目录迁移。
- `IngestionExecutor` 在 FastAPI lifespan 内运行，使用数据库租约领取任务，默认并发 2；启动时恢复租约过期任务。
- 上传接口只原子写入 `pending/` 并触发扫描，不等待识别。
- 前端轮询持久化任务状态，提供“检查源文件”按钮。

## Tasks

### Task 1：配置、模型和迁移

- 扩展 `KnowledgeSettings`：源文件根目录、并发数、租约和扫描稳定时间。
- 新增 `KnowledgeSourceFileModel`、`KnowledgeIngestionJobModel`。
- 新增 Alembic 迁移、索引和活动任务唯一约束。
- 更新模型导出与模型测试。

### Task 2：目录存储、扫描与去重

- 新增状态目录存储类，禁止符号链接和路径逃逸。
- 支持递归扫描并保留相对目录。
- 上传使用临时文件加原子重命名。
- 所有文件统一执行格式校验和 SHA-256 去重。
- 重复、不支持和损坏文件移动至 `failed/` 并记录结构化原因。

### Task 3：持久化执行器与恢复

- 数据库原子领取 queued 任务。
- 默认两个 worker，配置可覆盖。
- 保存 stage、current、total、percent、heartbeat、lease 和 checkpoint。
- 服务启动时回收租约过期的 running 任务。
- PDF/TXT 成功后保存候选 Markdown并移至 `recognized/`。
- Markdown 成功后保存正式 Markdown、移至 `archived/` 并调用现有索引服务。
- 单个任务失败不得中止其他 worker。

### Task 4：API 与确认衔接

- 上传 API 改为写入 `pending/` 并异步返回。
- 新增手动扫描、源文件/任务列表和任务详情 API。
- 文档列表响应附带源文件和摄取进度。
- PDF/TXT 现有确认成功后将源文件从 `recognized/` 移至 `archived/`。
- 保持统一 `{"ok": true, "data": ...}` 响应。

### Task 5：前端

- 扩展知识文档与摄取任务类型。
- 增加“检查源文件”按钮和扫描结果提示。
- 列表展示阶段、真实进度、失败原因。
- `queued/running` 时轮询；刷新后从 API 恢复。
- 保持现有候选预览、编辑、确认和索引交互不变。

### Task 6：验证

- 后端单元测试：目录迁移、递归扫描、去重、不支持类型、状态机、租约恢复、并发上限。
- API 测试：上传快速返回、手动扫描、进度读取、确认归档。
- 回归现有知识库 API、解析、确认和索引测试。
- 前端运行 `bun run typecheck` 和 `bun run build`。
- 运行 `git diff --check`。

## Acceptance Criteria

1. 前端上传和目录投放进入完全相同的摄取流程。
2. 启动时自动扫描，前端可主动触发扫描。
3. 递归处理 `pending/`，跨状态目录保留相对目录。
4. 默认最多两个识别任务并行，环境变量可调整。
5. 页面刷新和后端重启后状态、阶段和进度可恢复。
6. 重复文件进入 `failed/duplicate_source`，不生成文档或候选 Markdown。
7. 不支持格式进入 `failed/unsupported_file_type`。
8. PDF/TXT 成功后进入 `recognized/awaiting_confirmation`。
9. Markdown 跳过识别和确认，进入 `archived` 并触发现有索引。
10. 本期不改变候选确认、编辑、索引和检索的既有行为。
