# 统一结构化文件日志设计

**日期：** 2026-08-13
**状态：** 已实施
**范围：** 后端应用日志、HTTP 访问日志、后台任务日志

## 1. 背景

当前后端主要依赖 Python `logging` 和 Uvicorn 默认配置向控制台输出日志。日志不会持久化，格式不统一，缺少请求和任务关联标识，也没有统一的敏感信息脱敏机制。终端关闭后，历史日志无法继续查询。

本设计建立统一的后端日志基础设施，在保留现有业务 `logger.info()`、`logger.error()` 等调用方式的前提下，实现日志落盘、轮转、JSON 结构化、上下文关联、敏感信息脱敏和简单的全局日志等级配置。

## 2. 目标

1. 后端日志同时输出到控制台和本地文件。
2. 每条日志使用单行 JSON 格式，便于程序查询和人工排查。
3. 日志文件按照日期目录和日志级别分别存放，单个级别文件过大时继续按大小轮转。
4. HTTP 请求、对话运行、PDF 识别和其他后台任务具有可关联的上下文字段。
5. 写入控制台和文件之前统一清除密钥、Token、Cookie 和密码等敏感信息。
6. 通过 `.env` 中的单一 `LOG_LEVEL` 参数控制是否输出 DEBUG 日志。
7. 统一接管应用、Uvicorn 和常用第三方库日志，避免重复输出。

## 3. 非目标

本阶段不实现：

- 前端日志查看页面。
- 日志写入 PostgreSQL。
- ELK、Loki、Sentry 等远程日志平台接入。
- 不同 Python 模块分别配置日志等级。
- 记录完整 HTTP 请求体、响应体、LLM Prompt 或外部平台原始响应。
- 在运行期间动态修改日志等级。

## 4. 日志等级

系统只使用以下五种日志等级：

- `DEBUG`
- `INFO`
- `WARNING`
- `ERROR`
- `CRITICAL`

### 4.1 默认行为

`.env` 未配置 `LOG_LEVEL` 时，等价于：

```dotenv
LOG_LEVEL=INFO
```

输出：

```text
INFO
WARNING
ERROR
CRITICAL
```

不输出 `DEBUG`。

### 4.2 Debug 行为

设置：

```dotenv
LOG_LEVEL=DEBUG
```

输出：

```text
DEBUG
INFO
WARNING
ERROR
CRITICAL
```

### 4.3 参数校验

`LOG_LEVEL` 大小写不敏感，但只接受 `INFO` 和 `DEBUG` 两个配置值。其他值统一回退到 `INFO`，并在启动时输出一条 `WARNING`。

不提供模块级日志等级配置。

## 5. 日志输出

### 5.1 输出位置

日志同时写入：

1. 当前后端进程控制台。
2. 项目根目录下的 `logs/YYYY-MM-DD/<level>.log`。

`logs/` 必须被 Git 忽略。日志文件使用 UTF-8 编码。`logs/` 是项目根目录下的相对路径，不是操作系统根目录 `/logs`。

日志目录按照日期和级别组织：

```text
logs/
├── 2026-08-13/
│   ├── info.log
│   ├── warning.log
│   ├── error.log
│   └── critical.log
└── 2026-08-14/
    ├── info.log
    ├── warning.log
    ├── error.log
    └── critical.log
```

设置 `LOG_LEVEL=DEBUG` 后，该日期目录可以额外包含：

```text
logs/2026-08-13/debug.log
```

文件按实际日志写入按需创建。某个日期没有产生对应级别日志时，不要求创建空文件。

每个日志级别只写入对应文件：

- `DEBUG` 只写入 `debug.log`。
- `INFO` 只写入 `info.log`。
- `WARNING` 只写入 `warning.log`。
- `ERROR` 只写入 `error.log`。
- `CRITICAL` 只写入 `critical.log`。

不创建包含所有级别日志的汇总文件。

### 5.2 JSON 格式

每条日志占一行，不允许跨行写入非 JSON 内容。基础结构如下：

```json
{
  "timestamp": "2026-08-13T22:10:36.518+08:00",
  "level": "ERROR",
  "logger": "app.api.routes.chats",
  "message": "Chat agent stream execution failed",
  "request_id": "req_42f4c5",
  "run_id": "run_97a812",
  "job_id": null,
  "task_id": null,
  "trace_id": null,
  "chat_id": "810641c9-d2d9-4424-a644-61715a0e37bb",
  "document_id": null,
  "source_file_id": null,
  "module": "chats",
  "function": "_event_generator",
  "line": 758,
  "exception": null
}
```

`timestamp` 使用带时区的 ISO 8601 格式。无值的标准上下文字段输出 `null`，保证字段结构稳定。

异常日志的 `exception` 包含：

```json
{
  "type": "RuntimeError",
  "message": "处理失败",
  "stacktrace": "..."
}
```

## 6. 日志目录切换与大小轮转

日期目录是固定组织方式，不再通过配置选择。服务跨过本地时间零点后，新的日志自动写入新的 `YYYY-MM-DD` 目录。

相关配置：

```dotenv
LOG_DIR=logs
LOG_RETENTION_DAYS=14
LOG_MAX_BYTES=104857600
LOG_BACKUP_COUNT=10
```

规则：

- 日志根目录默认为项目根目录下的 `logs/`。
- 日期目录使用本地日期，格式固定为 `YYYY-MM-DD`。
- 默认保留最近 14 个日期目录，超过保留期后按日期目录整体删除。
- 单个级别文件默认最大 100MB。
- 某个级别文件达到上限后，只轮转该级别文件，不影响同日期下的其他级别文件。
- 同一日期、同一级别默认保留 10 个大小轮转文件。
- 大小轮转文件命名如下：

```text
logs/2026-08-13/error.log
logs/2026-08-13/error.log.1
logs/2026-08-13/error.log.2
```

- `error.log` 是当前写入文件，数字越大表示内容越旧。
- 配置非法时使用上述默认值，并输出 `WARNING`。
- 当前服务按单进程运行。未来启用多个 Uvicorn worker 时，必须重新评估多进程文件写入和大小轮转。

## 7. 请求上下文

使用 `ContextVar` 保存日志上下文，禁止使用进程级普通全局变量，避免异步请求之间串值。

HTTP 中间件执行以下操作：

1. 读取 `X-Request-ID` 请求头。
2. 请求头不存在或格式非法时生成新的 request ID。
3. 将 request ID 写入日志上下文。
4. 在响应头返回相同的 `X-Request-ID`。
5. 记录请求方法、路径、状态码和耗时。
6. 请求结束后清理上下文。

中间件必须兼容 SSE 流式响应，在流结束前保持上下文有效。

不记录完整查询参数、请求体、响应体和认证请求头。

## 8. 任务上下文

在业务任务入口显式绑定已有标识：

| 场景 | 上下文字段 |
|---|---|
| 对话执行 | `request_id`、`run_id`、`chat_id` |
| 内容生成 | `request_id`、`run_id`、`operation_id`、`document_id` |
| PDF 文件识别 | `job_id`、`source_file_id`、`document_id` |
| PDF 单页识别 | `job_id`、`page_number` |
| RAG 检索 | `request_id`、`run_id`、`trace_id` |
| Task Plan | `run_id`、`plan_id`、`task_id` |
| 定时任务 | `scheduler_job_id` |

后台任务不得依赖请求上下文自动存在。启动 worker、恢复任务和定时任务时必须显式绑定自己的任务 ID。

## 9. 敏感信息脱敏

所有日志在进入控制台和文件 handler 前统一脱敏。

### 9.1 敏感字段名

至少覆盖：

```text
authorization
proxy-authorization
cookie
set-cookie
api_key
apikey
access_token
refresh_token
password
secret
signature
credential
```

字段值统一替换为：

```text
[REDACTED]
```

### 9.2 字符串内容

至少识别并脱敏：

- `Bearer` 和 `Basic` 认证内容。
- 常见 API Key 格式。
- URL 查询参数中的 token、key、signature 和 password。
- 数据库连接 URL 中的密码。
- Cookie 请求头内容。

脱敏范围必须包括：

- 日志消息。
- 日志格式化参数。
- 结构化额外字段。
- 异常消息。
- traceback 文本。
- Uvicorn、HTTPX 和其他第三方库日志。

正则脱敏不能替代源头控制。业务代码默认禁止在 INFO 日志中记录完整 Prompt、HTTP Header、Cookie、请求体和第三方原始响应。

## 10. 日志初始化

日志配置必须在应用启动早期完成，并且整个进程只初始化一次。

实现要求：

1. 移除被导入脚本中的 `logging.basicConfig()` 副作用。
2. 统一配置 root logger、应用 logger、Uvicorn 和第三方 logger。
3. 避免 Uvicorn 再次覆盖应用日志配置。
4. 避免 logger 传播造成同一条日志重复输出。
5. 使用日志队列将格式化和文件写入移出异步业务执行路径，减少磁盘写入对 SSE、对话和 PDF 识别的阻塞。
6. 服务正常关闭时停止日志监听器并刷新待写日志。

Uvicorn 默认访问日志由统一 HTTP 中间件替代，避免产生一条无 request ID 的重复访问记录。

## 11. 错误记录约定

- 可预期业务拒绝使用 `WARNING` 或 `INFO`。
- 任务失败使用 `ERROR`。
- 影响服务继续运行的严重错误使用 `CRITICAL`。
- 需要堆栈时必须在 `except` 中使用 `logger.exception()`。
- `DEBUG` 只记录诊断过程，不得包含敏感原文。
- 禁止使用 `print()` 输出运行日志。

## 12. 验收标准

1. 默认配置只输出 `INFO`、`WARNING`、`ERROR`、`CRITICAL`。
2. `LOG_LEVEL=DEBUG` 时额外输出 `DEBUG`。
3. 非法 `LOG_LEVEL` 回退为 `INFO` 并产生警告。
4. 控制台和所有 `.log` 文件中的每一行都能被 JSON 解析。
5. 日志按照 `logs/YYYY-MM-DD/<level>.log` 正确分类，不产生汇总日志文件。
6. 跨天后自动写入新的日期目录，超过大小上限后只轮转对应级别文件。
7. 超过保留期的历史日期目录可以按配置整体清理。
8. HTTP 响应包含 `X-Request-ID`，同一请求日志中的 request ID 一致。
9. 并发请求之间的上下文不会串线。
10. SSE 流结束前保留正确的 request ID 和 run ID。
11. PDF 识别日志包含 job ID，单页日志包含 page number。
12. 对话和生成日志包含对应的 run ID。
13. Token、Cookie、密码、API Key 和签名不会以明文出现在控制台或日志文件中。
14. 应用日志、Uvicorn 日志和第三方日志不会重复输出。
15. 日志写入不会明显阻塞对话、SSE 或 PDF 后台识别任务。
