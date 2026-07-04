# Feature: Reliable SSE Generation — 可靠的流式生成任务

## 背景（Background）

当前工作台的单条 AI 回答生成通过 `POST /api/workflow/generate-one/stream` 发起，并由前端使用 `fetch + ReadableStream` 手写解析 SSE 数据。这个方案把“生成任务”和“当前 HTTP 连接”绑定在一起：连接正常时可以收到 token；连接中断、页面刷新或浏览器重新加载后，前端无法继续接收已经开始的生成结果。

现有问题集中在三个方面：

- 生成任务生命周期依赖单次 HTTP 连接，网络抖动会让前端失去后续事件。
- 旧流式协议只在 `data` 中放 `type`，没有标准 SSE `id` 和 `event` 字段，无法基于 `Last-Event-ID` 补发缺失事件。
- 工作台曾把生成中的文本、最终回答和编辑器草稿混用同一个 `answer` 字段，高频流式更新可能被富文本编辑器内部状态覆盖。

本功能要把单条回答生成升级为“创建任务 + EventSource 订阅”的可靠任务模型，让生成过程不再依赖某一条浏览器连接。

## 目标（Goal）

本次功能为工作台单条回答生成建立可靠的 SSE 任务订阅模型。前端先创建生成 job，再用 `EventSource` 订阅 job 事件；服务端为每个业务事件分配递增 id、缓存事件，并在重连或页面恢复时补发缺失事件。生成完成前只展示只读预览，收到 `done` 后才把最终回答交给编辑器。

## 非目标（Non-Goals）

- 不改变 LLM 提示词、回答质量策略、图片提示词生成策略。
- 不改变 URL 导入、问题解析、采集流程或热榜逻辑。
- 不删除旧的 `POST /api/workflow/generate-one/stream`、`POST /api/workflow/generate/stream`、`POST /api/workflow/polish-one/stream` 接口。
- 不在本次迁移批量生成和润色流式接口；它们继续使用旧 `fetch + ReadableStream` 客户端。
- 不要求跨进程、跨服务重启恢复 job；第一阶段只要求单进程内存缓存。
- 不新增多 Agent 编排能力。

## 用户故事（User Stories）

- 作为工作台用户，我希望点击“AI 生成”后即使短暂断网也能继续看到生成结果，以便不用重新消耗 LLM token。
- 作为工作台用户，我希望生成中刷新页面后还能恢复任务状态，以便误操作不会直接丢失已经开始的生成。
- 作为工作台用户，我希望生成中看到只读预览，生成完成后再进入富文本编辑器，以便编辑器不会覆盖流式结果。
- 作为工作台用户，我希望快速重复点击生成时不会产生多个互相覆盖的任务，以便同一个问题的结果保持可预测。

## 功能需求（Requirements）

### 后端任务模型

- R1：新增单条生成 job 创建接口，接收现有 `GenerateOnePayload` 等价请求体，返回 `jobId`。
- R2：创建 job 后必须立即返回，实际生成在后台继续执行；SSE 连接断开不得取消后台生成任务。
- R3：每个 job 必须有状态：`pending`、`running`、`done`、`error`、`canceled`。已清理任务不再作为 job 状态存在，查询或订阅时通过“任务不存在或已过期”的错误语义表达。
- R4：每个 job 内的可恢复业务事件必须带递增整数 `id`，且同一个 job 内不得重复或倒退。
- R5：服务端必须缓存 job 事件和最终结果。第一阶段使用内存缓存；完成、失败或取消后的 job 至少保留 30 分钟。
- R6：缓存必须有最大 job 数限制。超过限制时，只能清理终态且已超过保留期的 job，不得清理 `pending` 或 `running` job。
- R7：同一个 item 同一时间只能有一个 active generation job。重复创建时，服务端必须返回现有 active job，或拒绝创建并给出可展示错误；具体行为在接口设计中固定为返回现有 active job。
- R8：job 生成成功后，`done` 事件必须携带完整 `item`，其中 `item.answer` 是服务端确认的最终回答。
- R9：job 生成失败后，必须写入 `job_error` 事件和 job `error` 字段；不得使用业务 `event: error`，避免与 `EventSource.onerror` 网络错误语义混淆。
- R10：取消 job 后必须进入 `canceled` 状态，并向订阅者发送 `canceled` 事件。若底层 LLM 调用无法真正中断，也不得再把该 job 标记为 `done`。

### SSE 订阅与恢复

- R11：新增 job 订阅接口，使用标准 SSE 字段输出：`id`、`event`、`data`。
- R12：业务事件包括 `chunk`、`done`、`job_error`、`canceled`。`heartbeat` 可用于保活，但不参与恢复缓存，不带递增业务 id。
- R13：浏览器自动重连时，服务端必须读取 `Last-Event-ID` 请求头，并补发所有 `id > Last-Event-ID` 的缓存业务事件。
- R14：页面刷新后新建 `EventSource` 时，前端必须带上本地保存的 `lastEventId` 查询参数；服务端必须支持 `?lastEventId=<number>`，其优先级低于 `Last-Event-ID` 请求头。
- R15：订阅已完成 job 时，服务端必须补发从指定 id 之后到 `done` 的事件，然后关闭连接。
- R16：订阅运行中 job 时，服务端必须先补发缺失事件，再继续推送新事件。
- R17：订阅不存在或已过期 job 时，服务端必须返回明确错误，前端展示“任务不存在或已过期，可重新生成”。

### 前端工作台行为

- R18：工作台单条生成入口迁移到两阶段流程：先创建 job，再订阅 job SSE。
- R19：前端必须把流式预览、最终回答、编辑器草稿拆开管理，不再用同一个字段同时承担三种职责。
- R20：生成中只渲染只读 Markdown/纯文本预览，不挂载 `MarkdownEditor` 或 MDXEditor。
- R21：收到 `done` 前不得把 item 标记为已生成；收到 `done` 后必须以后端 `done.item.answer` 作为 `finalAnswer` 和初始 `draftAnswer`。
- R22：用户在编辑器中修改的是 `draftAnswer`。编辑器变更不得回写生成中的 `streamingAnswer`。
- R23：前端必须记录当前 job 的 `jobId`、`itemId`、`lastEventId` 和阶段状态到同一浏览器会话可恢复的位置，例如 `sessionStorage`。刷新页面后如果后端 job 仍存在，必须恢复订阅或读取最终结果。
- R24：`EventSource.onerror` 只表示连接异常或浏览器准备重连，不得立即把任务标记为失败。只有收到 `job_error`、`canceled`、明确的 job 查询错误，或超过 60 秒无恢复进展时，才进入错误、中断或取消状态。
- R25：收到重复事件或乱序事件时，前端必须根据事件 id 去重；`id <= lastEventId` 的业务事件不得重复追加到预览。

## 验收标准（Acceptance Criteria）

- AC1：用户点击“AI 生成”后，前端先收到 `jobId`，随后通过 `EventSource` 收到 `chunk` 事件并显示只读预览。
- AC2：每个 `chunk`、`done`、`job_error`、`canceled` 业务事件都有递增 `id`；`heartbeat` 不改变 `lastEventId`。
- AC3：断网后浏览器自动重连时，服务端根据 `Last-Event-ID` 补发缺失事件，预览文本不重复、不缺失。
- AC4：生成中刷新页面后，前端用本地保存的 `jobId` 和 `lastEventId` 恢复订阅；如果 job 已完成，页面直接显示完整回答并挂载编辑器。
- AC5：收到 `done` 前，问题列表和回答面板不得显示“已生成”；收到 `done` 后，最终显示的回答必须等于 `done.item.answer`。
- AC6：生成中 DOM 中不挂载 `MarkdownEditor`；生成完成后才挂载，并以最终回答初始化编辑内容。
- AC7：服务端发送 `job_error` 后，前端显示错误信息，任务不进入已生成状态。
- AC8：用户快速重复点击同一 item 的生成按钮时，不会出现两个 active job 互相覆盖同一 item 的回答。
- AC9：job 完成后 30 分钟内再次订阅，可以补发到 `done`；超过保留期后查询返回已过期语义，前端允许重新生成。
- AC10：旧流式接口仍可被旧客户端调用，`frontend/src/lib/sse.ts` 保持兼容旧接口和 Agent 流式接口。

## 边界情况（Edge Cases）

- 创建 job 请求体无效：返回统一错误 envelope，前端停留在可重试状态。
- job 不存在：查询或订阅返回明确错误，前端提示任务不存在并允许重新生成。
- job 已过期：查询或订阅返回明确过期语义，前端清理本地 job 记录并允许重新生成。
- 浏览器重连但没有 `Last-Event-ID`：如果 URL 有 `lastEventId` 查询参数，按该值补发；否则从缓存开头补发。
- 前端收到重复事件：忽略 `id <= lastEventId` 的业务事件。
- 前端收到跳号事件：继续应用事件，但保留日志或状态提示，方便调试服务端缓存问题。
- 后端生成完成后图片生成失败且属于缺少图片环境变量：沿用现有行为，回答生成成功，图片列表为空。
- 后端生成过程中发生非图片配置错误：job 进入 `error`，发送 `job_error`。
- 用户取消 job：前端关闭 EventSource，job 状态变为 `canceled`，该 job 的后续 LLM token 不再更新 UI。
- 服务端重启：内存 job 丢失；前端查询时提示任务不存在或已过期，用户可以重新生成。

## 交互与界面行为（UX / UI Behavior）

- 创建 job 中：生成按钮显示 loading，避免重复点击；内容区显示等待生成开始的轻量状态。
- 生成中：内容区显示只读预览；复制按钮可以隐藏或禁用；编辑器不挂载。
- 自动重连中：保留当前预览内容，显示“正在恢复连接”一类的非阻塞提示；不得清空已收到内容。
- 超过 60 秒无恢复进展：任务进入 `interrupted`，保留已收到预览，提供“继续恢复”和“重新生成”操作。
- 生成完成：把 `done.item.answer` 写入最终回答和编辑器草稿，状态变为 `done`，按钮文案恢复为“重新生成”。
- 生成失败：展示 `job_error.message`，状态变为 `error`，保留错误前已收到的只读预览，但不得把预览当成最终回答。
- 取消生成：状态变为 `canceled`，关闭当前订阅，保留取消前预览但不进入编辑器。
- 页面刷新恢复：如果本地存在 job 记录，先查询 job；运行中则继续订阅，已完成则直接显示最终回答，已过期则清理本地记录并提示可重新生成。

## 数据模型（Data Model）

### GenerationJob

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | string | job 唯一标识，对外暴露为 `jobId` |
| `kind` | `"generate_one"` | 本次只实现单条生成 |
| `status` | `"pending" \| "running" \| "done" \| "error" \| "canceled"` | job 生命周期状态 |
| `item_id` | string | 对应工作台 item id，对外使用 camelCase `itemId` |
| `payload` | object | 创建 job 时的生成请求快照 |
| `events` | `SseJobEvent[]` | 可恢复业务事件缓存 |
| `final_item` | object 或 null | 生成成功后的完整 item，对外使用 `finalItem` |
| `error` | string 或 null | 失败原因 |
| `created_at` | datetime | 创建时间，对外使用 `createdAt` |
| `updated_at` | datetime | 最近更新时间，对外使用 `updatedAt` |
| `expires_at` | datetime 或 null | 终态 job 的过期时间，对外使用 `expiresAt` |

### SseJobEvent

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | number | job 内递增业务事件 id |
| `event` | `"chunk" \| "done" \| "job_error" \| "canceled"` | 标准 SSE event 名称 |
| `data` | object | 事件负载 |
| `created_at` | datetime | 事件创建时间，对外使用 `createdAt` |

### 前端生成状态

| 字段 | 类型 | 说明 |
|---|---|---|
| `jobId` | string 或 null | 当前订阅的 job |
| `itemId` | string 或 null | 当前 job 对应 item |
| `status` | `"idle" \| "creating" \| "generating" \| "done" \| "error" \| "interrupted" \| "canceled"` | UI 阶段状态 |
| `lastEventId` | number | 已应用的最后业务事件 id |
| `streamingAnswer` | string | 生成中的只读预览 |
| `finalAnswer` | string | `done.item.answer` |
| `draftAnswer` | string | 用户可编辑草稿 |
| `error` | string 或 null | 可展示错误 |

## 接口设计（API / Interface Design）

所有非 SSE JSON 接口必须使用项目统一响应 envelope：成功为 `{"ok": true, "data": ...}`，失败为 `{"ok": false, "error": {"message": "..."}}`。字段对前端使用 camelCase。

| 接口 | 方法 | 请求/响应 | 说明 |
|---|---|---|---|
| `/api/workflow/generate-one/jobs` | POST | 请求体等价 `GenerateOnePayload`；响应 data 为 `{ "jobId": "...", "status": "pending" 或 "running" }` | 创建或返回同 item 的 active job |
| `/api/workflow/generate-one/jobs/{jobId}` | GET | 响应 data 为 job 快照，包含 `status`、`finalItem`、`error`、`lastEventId`、`expiresAt` | 页面恢复和完成后查询 |
| `/api/workflow/generate-one/jobs/{jobId}/stream` | GET | 标准 `text/event-stream` | EventSource 订阅；支持 `Last-Event-ID` 和 `?lastEventId=` |
| `/api/workflow/generate-one/jobs/{jobId}` | DELETE | 响应 data 为 `{ "jobId": "...", "status": "canceled" }` | 取消未完成 job |

SSE 事件契约：

| event | 是否带 id | data | 说明 |
|---|---|---|---|
| `chunk` | 是 | `{ "text": "..." }` | 追加到只读预览 |
| `done` | 是 | `{ "item": QuestionItem }` | 最终成功结果 |
| `job_error` | 是 | `{ "message": "..." }` | 业务失败 |
| `canceled` | 是 | `{ "message": "..." }` | 用户或系统取消 |
| `heartbeat` | 否 | `{ "ts": "ISO-8601 string" }` | 保活，不写入恢复缓存 |

示例事件格式只用于说明协议形状：

```text
id: 1
event: chunk
data: {"text":"第一段"}

id: 2
event: done
data: {"item":{"answer":"完整答案"}}
```

## 架构说明（Architecture Notes）

- 新 job 能力应放在后端应用/服务层，路由只负责参数校验、调用服务和包装响应，保持现有“薄路由”约定。
- 旧 `app/api/sse_utils.py` 的 `data: {type: ...}` 工具继续服务旧接口；可靠 job SSE 需要支持标准 `id`、`event`、`data` 字段，不能破坏旧解析器。
- 事件缓存的并发访问必须可预测：后台生成追加事件，多个 SSE 订阅者读取事件。实现计划中应明确同步机制，避免订阅者漏事件或重复等待。
- 图片生成仍发生在文本生成完成之后；只有最终 `done.item` 才能包含完整回答和图片字段。
- 前端新增 EventSource job 客户端应与 `frontend/src/lib/sse.ts` 并存。旧 `streamPost` 不改为 EventSource，以免影响批量生成、润色、Agent 对话等旧流式入口。
- 工作台状态应保持和现有 `WorkbenchItem.generationStatus` 兼容，同时新增必要的 job 恢复状态。`answer` 字段只代表最终可编辑回答，不再承载 token 级流式预览。
- 本次 feature 的 spec 只定义需求和边界；具体文件拆分、测试代码和提交步骤放到用户确认后的 plan 中。

## 测试策略（Testing Strategy）

后端单元测试：

- 覆盖 AC2：创建 job 后连续追加业务事件，断言事件 id 单调递增且 heartbeat 不占用 id。
- 覆盖 AC7：模拟生成异常，断言 job 状态为 `error`，缓存中包含 `job_error`，且没有 `done`。
- 覆盖 AC8：同一 item 重复创建 job，断言返回同一个 active `jobId` 或统一的 active job 语义。
- 覆盖 AC9：终态 job 在保留期内可查询，过期清理不删除 `pending` 或 `running` job。

后端接口/集成测试：

- 覆盖 AC1：`POST /api/workflow/generate-one/jobs` 返回统一 envelope 和 `jobId`。
- 覆盖 AC3：带 `Last-Event-ID` 订阅时，只返回缺失业务事件。
- 覆盖 AC4：带 `?lastEventId=` 订阅时，能在页面刷新语义下补发缺失事件。
- 覆盖 AC10：旧 `POST /api/workflow/generate-one/stream` 仍返回旧格式事件，旧解析器不受影响。

前端验证：

- 覆盖 AC5、AC6：生成中只显示只读预览且不挂载 `MarkdownEditor`；`done` 后才挂载编辑器并使用最终回答初始化。
- 覆盖 AC3、AC4：通过浏览器 DevTools 断网和刷新页面验证自动恢复，不重复追加文本。
- 覆盖 AC7：服务端返回 `job_error` 时显示错误，问题不进入已生成状态。
- 覆盖 AC8：快速重复点击生成按钮，确认同一 item 不出现多个互相覆盖的 active job。
- 每次前端改动后必须运行 `cd frontend && bun run typecheck`。如果实现阶段引入前端测试框架，再把上述前端验证补成自动化测试。

手工端到端验证：

1. 正常生成：流式预览出现，完成后编辑器显示完整答案。
2. 生成中断网：恢复网络后继续接收缺失内容。
3. 生成中刷新：页面恢复后继续订阅或直接显示最终结果。
4. 生成完成后刷新：页面直接显示完整答案。
5. 生成失败：显示错误，不把部分预览保存为最终回答。

## 风险（Risks）

- 内存缓存只适合本地单进程运行；服务重启或多 worker 部署会丢失 job，需要未来再升级持久化缓存。
- EventSource 不能自定义请求头；页面刷新恢复必须依赖本地保存的 `lastEventId` 查询参数，而不是假设浏览器自动发送旧的 `Last-Event-ID`。
- `EventSource.onerror` 和业务失败容易混淆；必须使用 `job_error` 作为业务失败事件名。
- 富文本编辑器如果在生成中挂载，仍可能通过内部状态覆盖流式结果；UI 必须严格区分预览阶段和编辑阶段。
- 图片生成发生在文本完成后，可能让 `done` 延迟；用户会看到文本预览已完整但任务尚未完成的短暂状态。

## 待确认问题（Open Questions）

无。
