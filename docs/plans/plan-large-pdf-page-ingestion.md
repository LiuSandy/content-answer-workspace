# 大型 PDF 逐页识别与断点恢复 Implementation Plan

> 对应规格：[feature-large-pdf-page-ingestion.md](../specs/feature-large-pdf-page-ingestion.md)

## Goal

让 70MB 以上、300 页以上的 PDF 能够通过流式接收和逐页转换稳定生成候选 Markdown，并在页面刷新或后端重启后从未完成页面继续处理。

## Scope

只改造 PDF 从源文件进入候选 Markdown 的摄取阶段。现有候选预览、人工确认、正式 Markdown、分块、Embedding、索引和 RAG 检索保持不变。

## Architecture

- 上传与目录扫描通过固定缓冲区写文件和计算 SHA-256，不读取完整文件到内存。
- PDF 通过文件路径打开，只创建单页临时 PDF。
- PostgreSQL 的 `knowledge_ingestion_pages` 保存每页状态、租约、结果、置信度和错误。
- 文件任务保存总页数、成功/失败/完成页数和当前页，供前端直接展示。
- 页面 Markdown 原子写入 `output/knowledge/ingestion-work/<job-id>/pages/`。
- 服务重启时跳过 succeeded 页面，只回收租约过期的 running 页面。
- 全部页面结束后按页码幂等合并，进入现有候选确认流程。

## Tasks

### Task 1：配置、模型与迁移

- 新增 2GB 源文件上限、上传缓冲区、页面并发、页面重试和工作目录配置。
- 扩展文件任务的页数汇总字段。
- 新增 `KnowledgeIngestionPageModel` 和数据库迁移。
- 增加模型、配置与迁移测试。

### Task 2：流式接收与哈希

- 上传接口按固定块写入 `.uploading` 临时文件并同步计算 SHA-256。
- 完成后刷新并原子移动到 pending。
- pending 扫描使用固定块流式计算 SHA-256。
- 文件超过 2GB 时进入 `failed/file_too_large`。
- 去重行为保持不变。

### Task 3：逐页执行与持久化

- 按路径打开 PDF，初始化唯一的页任务记录。
- 每次只提取一页并创建临时单页 PDF。
- 单页最多尝试 3 次；成功结果立即原子落盘。
- 每页完成后原子更新页面状态和文件任务汇总。
- 单页最终失败后继续下一页。

### Task 4：恢复与合并

- 启动时回收租约过期的页面任务。
- 验证源文件哈希，变化时终止任务。
- 跳过已成功页面，只处理 pending/过期 running 页面。
- 按页码合并成功结果，失败页写占位。
- 至少一页成功时生成候选 Markdown；全部失败时文件任务失败。
- 确认或删除后清理页面中间产物。

### Task 5：API 与前端

- 源文件和文档响应增加总页数、完成、成功、失败和当前页。
- 前端显示真实页级进度与成功/失败统计。
- `completed_with_errors` 明确显示为“识别完成，部分页面失败”。

### Task 6：验证

- 流式哈希、单页提取、顺序合并和失败占位单元测试。
- 页面初始化幂等、成功页跳过、过期页面恢复测试。
- 现有知识库完整回归测试。
- 前端 typecheck 与 build。
- 使用用户准备的 70MB+、300 多页 PDF 做真实验证；不调用外部识别服务时至少验证流式登记、页任务初始化与内存边界。

## Acceptance Criteria

1. 70MB+ PDF 不再因 50MB 限制失败。
2. 上传和哈希没有整文件 `read()`/`read_bytes()`。
3. 每个转换单元只包含一页。
4. 已成功页面在服务重启后不重做。
5. 单页失败不阻断后续页面。
6. 前端显示总页数、完成、成功、失败和真实进度。
7. 合并顺序严格按页码，失败页有占位。
8. 最终仍停留在现有人工确认门禁之前。
