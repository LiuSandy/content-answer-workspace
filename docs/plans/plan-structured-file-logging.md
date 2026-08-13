# 统一结构化文件日志 Implementation Plan

> 对应规格：[feature-structured-file-logging.md](../specs/feature-structured-file-logging.md)

## Goal

在不改变现有业务流程的前提下，统一接管后端应用、HTTP 访问、后台任务、Uvicorn 和第三方库日志，实现 JSON 控制台输出、按日期和级别分类落盘、单文件大小轮转、请求与任务上下文关联、敏感信息脱敏，以及 `LOG_LEVEL=INFO/DEBUG` 全局等级控制。

## Scope

本计划只改造后端日志基础设施和日志上下文绑定。前端页面、数据库结构、业务 API 响应结构、远程日志平台和模块级日志等级配置保持不变。

日志文件固定组织为：

```text
logs/YYYY-MM-DD/debug.log
logs/YYYY-MM-DD/info.log
logs/YYYY-MM-DD/warning.log
logs/YYYY-MM-DD/error.log
logs/YYYY-MM-DD/critical.log
```

每条日志只写入与自身等级对应的文件，不创建汇总日志。

## Architecture

- `app/observability/logging.py` 负责读取环境变量、初始化 root logger、日志队列、控制台和文件 handler，并统一接管 Uvicorn 与第三方 logger。
- `app/observability/formatter.py` 将 `LogRecord` 格式化为单行 JSON，并规范异常结构。
- `app/observability/context.py` 使用 `ContextVar` 保存 request、run、job、task、trace 和业务实体 ID。
- `app/observability/redaction.py` 在日志进入队列前完成字段和字符串脱敏。
- `app/observability/middleware.py` 使用纯 ASGI middleware 管理 HTTP 请求上下文和访问日志，兼容 SSE。
- 日志队列在异步业务线程之外完成 JSON 格式化和磁盘写入，避免日志 I/O 阻塞对话和 PDF 识别。
- 每个日志级别使用精确等级过滤器和独立文件 handler。handler 根据当前本地日期写入对应目录，并在单文件达到大小限制时生成 `.log.1`、`.log.2`。
- 日期保留清理由日志基础设施执行，以完整的 `YYYY-MM-DD` 目录为删除单位。

## Tasks

### Task 1：日志配置模型与目录约定

涉及文件：

- `app/observability/__init__.py`
- `app/observability/logging.py`
- `app/core/config.py`
- `.env.example`
- `.gitignore`

工作内容：

- 新增日志配置对象，读取并校验：

```dotenv
LOG_LEVEL=INFO
LOG_DIR=logs
LOG_RETENTION_DAYS=14
LOG_MAX_BYTES=104857600
LOG_BACKUP_COUNT=10
```

- `LOG_LEVEL` 只接受大小写不敏感的 `INFO` 和 `DEBUG`。
- 未设置或非法时使用 `INFO`；非法值在日志系统初始化后输出 `WARNING`。
- 其他数值配置必须为正整数，非法时使用 Spec 默认值并输出 `WARNING`。
- 相对 `LOG_DIR` 必须相对于项目根目录解析。
- 创建日志目录时禁止解析到项目外部的危险路径。
- 将项目根目录下的 `logs/` 加入 `.gitignore`。

测试：

- 默认配置解析。
- DEBUG 配置解析。
- 大小写兼容。
- 非法等级和非法数值回退。
- 相对路径解析。

### Task 2：JSON Formatter 与精确等级过滤

涉及文件：

- `app/observability/formatter.py`
- `app/observability/logging.py`
- `tests/observability/test_json_formatter.py`

工作内容：

- 实现稳定的单行 JSON formatter。
- 固定输出 Spec 约定的时间、等级、logger、message、上下文、调用位置和 exception 字段。
- 时间使用本地时区 ISO 8601 格式并包含毫秒。
- `logger.exception()` 生成结构化异常类型、消息和堆栈。
- 实现精确等级过滤器，保证 `ERROR` 不会同时写入 `info.log` 或 `warning.log`。
- 不支持的自定义日志等级不得产生额外级别文件。

测试：

- 每行可以被 `json.loads()` 解析。
- 中文和换行内容被正确编码为单行 JSON。
- 无上下文时标准字段为 `null`。
- exception 结构正确。
- 五种日志等级精确分类。

### Task 3：敏感信息脱敏

涉及文件：

- `app/observability/redaction.py`
- `app/observability/logging.py`
- `tests/observability/test_log_redaction.py`

工作内容：

- 实现大小写不敏感的敏感字段名脱敏。
- 实现 Bearer、Basic、常见 API Key、Cookie、数据库 URL 密码和敏感查询参数脱敏。
- 覆盖 message、args、extra、异常消息和堆栈。
- 脱敏在日志进入异步队列前执行，避免原始敏感数据进入队列或其他 handler。
- 审查现有记录完整第三方响应、Header、Prompt 或 Cookie 的 INFO 日志，将其删除、降为安全摘要或改为不含原文的 DEBUG 日志。

测试：

- 字典、列表、嵌套字段脱敏。
- 格式化字符串参数脱敏。
- URL 与数据库连接字符串脱敏。
- 异常消息和堆栈脱敏。
- 非敏感业务 ID 和普通中文内容保持不变。

### Task 4：按日期和级别落盘及大小轮转

涉及文件：

- `app/observability/logging.py`
- `tests/observability/test_log_file_routing.py`

工作内容：

- 为 DEBUG、INFO、WARNING、ERROR、CRITICAL 建立独立的精确等级 handler。
- 根据每条日志的本地日期写入 `logs/YYYY-MM-DD/<level>.log`。
- 文件按实际写入按需创建，不创建无日志的空文件。
- 跨过零点后关闭旧日期文件并切换到新日期目录。
- 单文件达到 `LOG_MAX_BYTES` 后在当前日期目录内轮转为 `.log.1`、`.log.2`。
- 每个日期、每个级别最多保留 `LOG_BACKUP_COUNT` 个大小轮转文件。
- 清理超过 `LOG_RETENTION_DAYS` 的合法日期目录。
- 清理逻辑只允许删除 `LOG_DIR` 下名称严格匹配 `YYYY-MM-DD` 的目录，不处理其他文件或目录。
- 文件使用 UTF-8，并尽可能设置为仅当前用户可读写。

测试：

- INFO、WARNING、ERROR 分别写入正确文件。
- DEBUG 在 INFO 模式下不产生文件，在 DEBUG 模式下写入 `debug.log`。
- 跨日期切换目录。
- 单级别文件大小轮转不影响其他级别。
- 超期日期目录清理不会误删非日期目录。

### Task 5：日志队列与统一初始化

涉及文件：

- `app/observability/logging.py`
- `app/server.py`
- `scripts/auto_migrate_db.py`
- 现有使用 `logging.getLogger("uvicorn")` 的业务模块
- `tests/observability/test_logging_setup.py`

工作内容：

- 使用 `QueueHandler` 和 `QueueListener` 将控制台及文件写入移出异步业务路径。
- 初始化 root logger，并确保重复调用初始化函数不会重复添加 handler 或监听器。
- 服务正常关闭时停止 listener 并刷新队列。
- 删除 `auto_migrate_db.py` 被导入时调用 `logging.basicConfig()` 的全局副作用。
- 将业务模块中的 `logging.getLogger("uvicorn")` 逐步改为 `logging.getLogger(__name__)`。
- Uvicorn 启动时不得覆盖统一日志配置。
- 禁用 Uvicorn 默认 access log，后续由统一请求中间件记录。
- `httpx`、APScheduler、SQLAlchemy 等第三方日志通过 root logger 输出相同 JSON，但仍受全局 INFO/DEBUG 等级控制。
- 避免 propagate 和重复 handler 造成同一条日志输出两次。

测试：

- 初始化一次和多次的 handler 数量一致。
- 同一条业务日志只输出一次。
- Uvicorn 和 HTTPX 日志可格式化为相同 JSON。
- listener 停止前能够刷新待写日志。

### Task 6：HTTP 请求 ID 与访问日志

涉及文件：

- `app/observability/context.py`
- `app/observability/middleware.py`
- `app/server.py`
- `tests/observability/test_request_logging.py`

工作内容：

- 使用 `ContextVar` 保存当前请求上下文。
- 读取并校验 `X-Request-ID`；缺失或非法时生成新 ID。
- 响应头返回最终使用的 `X-Request-ID`。
- 记录 `request.started` 和 `request.completed`，包含 method、path、status code 和 duration。
- 发生未捕获异常时记录 `request.failed`，同时保留现有 API 错误响应行为。
- 不记录请求体、响应体、认证头和完整查询参数。
- 使用纯 ASGI middleware，确保 SSE 流结束前 request ID 不被清理。
- 请求结束时可靠 reset ContextVar，防止并发请求串值。

测试：

- 服务生成 request ID。
- 合法调用方 request ID 被沿用，非法值被替换。
- 响应头和日志中的 request ID 一致。
- 并发请求上下文隔离。
- SSE 生成期间上下文保持，结束后清理。

### Task 7：业务任务上下文绑定

涉及文件：

- `app/api/routes/chats.py`
- `app/api/routes/documents.py`
- `app/application/knowledge/ingestion_service.py`
- `app/application/generation_job_service.py`
- `app/api/routes/task_plans.py`
- `app/application/agent/nodes/retrieve_knowledge.py`
- `app/infrastructure/scheduler/__init__.py`
- 对应测试文件

工作内容：

- 提供同步与异步均可使用的 `log_context(...)` 上下文管理器。
- 对话执行绑定 `run_id`、`chat_id`。
- 内容生成绑定 `run_id`、`operation_id`、`document_id`。
- 文件摄取绑定 `job_id`、`source_file_id`、`document_id`。
- PDF 单页识别额外绑定 `page_number`。
- RAG 检索在 trace ID 产生后绑定 `trace_id`。
- Task Plan 绑定 `plan_id`、`task_id`。
- 定时任务绑定稳定的 `scheduler_job_id`。
- 后台 worker、恢复任务和定时任务显式绑定上下文，不依赖请求上下文隐式继承。
- 上下文退出后恢复先前值，嵌套任务不得污染父任务。

测试：

- 对话错误日志包含 run 和 chat ID。
- PDF 文件及单页日志包含对应任务信息。
- RAG 日志包含 trace ID。
- 嵌套和并发任务上下文不会串线。

### Task 8：现有日志调用规范化

涉及范围：

- `app/` 下现有日志调用

工作内容：

- 失败且需要定位堆栈的 `logger.error(..., e)` 改为 `logger.exception(...)`。
- 可预期降级继续使用 `INFO` 或 `WARNING`。
- 任务失败使用 `ERROR`，服务无法继续运行才使用 `CRITICAL`。
- 删除运行路径中的 `print()`。
- 日志消息使用参数化写法，避免提前拼接敏感数据。
- 不改变异常捕获、返回值或业务状态流转。

验证：

- 搜索并确认业务运行路径不再使用 `print()` 输出日志。
- 关键失败路径具有 traceback。
- 不记录完整敏感载荷。

### Task 9：文档与完整验证

涉及文件：

- `.env.example`
- `README.md`
- `docs/specs/feature-structured-file-logging.md`
- `tests/observability/`

工作内容：

- 记录 INFO 和 DEBUG 两种启动配置。
- 说明日志目录、文件分类、大小轮转和保留策略。
- 给出使用 request ID、run ID 和 job ID 定位日志的示例。
- 说明日志文件包含 JSON 行而不是普通文本格式。

验证命令：

```bash
uv run pytest tests/observability -q
uv run pytest tests/test_chat_sse_events.py tests/test_agent_timeout.py tests/knowledge -q
git diff --check
```

手工验证：

1. 使用默认 INFO 配置启动服务。
2. 发起普通 API、SSE 对话和 PDF 摄取任务。
3. 检查当天目录中的各级别文件。
4. 确认响应头、对话 run ID 和 PDF job ID 可以关联到日志。
5. 使用测试密钥触发错误，确认控制台和文件中均只出现 `[REDACTED]`。
6. 使用小的 `LOG_MAX_BYTES` 验证单级别大小轮转。
7. 使用 DEBUG 配置重启，确认 `debug.log` 开始产生记录。

## Implementation Order

1. 配置、formatter、脱敏和文件路由。
2. 队列、统一初始化和 Uvicorn 接管。
3. 请求中间件与 request ID。
4. 对话、生成、RAG、PDF 和定时任务上下文。
5. 现有日志安全审查与规范化。
6. 完整测试和文档更新。

每个阶段完成后先运行对应的定向测试，再进入下一阶段。文件路由和脱敏测试全部通过前，不接入生产运行路径。

## Acceptance Criteria

1. 默认只输出 INFO、WARNING、ERROR、CRITICAL，DEBUG 配置额外输出 DEBUG。
2. 控制台和文件中的每条日志都是可解析的单行 JSON。
3. 每条日志只进入 `logs/YYYY-MM-DD/<level>.log` 中对应的一个级别文件。
4. 跨天和单文件大小轮转均正确工作。
5. 历史日期目录按保留天数安全清理。
6. HTTP 响应携带 request ID，SSE 和并发请求上下文正确隔离。
7. 对话、生成、RAG、PDF 和定时任务日志包含对应业务 ID。
8. 密钥、Token、Cookie、密码和签名不会以明文进入控制台、队列或日志文件。
9. Uvicorn、应用和第三方日志使用相同格式且不重复。
10. 日志系统不会改变现有 API、任务状态或业务结果。
11. 日志写入不会明显阻塞 SSE、Agent 对话和 PDF 后台识别。
