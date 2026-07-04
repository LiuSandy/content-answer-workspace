# Plan: Reliable SSE Generation 实施方案

> 对应 Feature：`docs/specs/feature-reliable-sse-generation.md`

## 目标

把当前“POST 请求直接返回流”的生成链路升级为可靠任务模型：

```
POST 创建生成任务
    ↓
返回 jobId
    ↓
EventSource 订阅任务流
    ↓
服务端按事件 id 推送 chunk / done / error
    ↓
断线后根据 Last-Event-ID 补发缺失事件
```

最终要求：

- 网络短暂断开后可以自动重连并继续接收。
- 页面刷新后可以根据 `jobId` 恢复任务。
- 生成任务不依赖某个浏览器连接是否还活着。
- 收到 `done` 前不能标记为“已生成”。
- 富文本编辑器不参与 token 级流式渲染。

---

## 设计原则

| 原则 | 体现 |
|---|---|
| 任务与连接解耦 | 后端 job 独立运行，SSE 连接只负责订阅事件 |
| 协议使用标准 SSE | 使用 `id:` / `event:` / `data:`，让浏览器原生 `EventSource` 处理解析和重连 |
| 最终结果可信 | `done` 事件中的完整 `item.answer` 是最终来源 |
| 状态职责分离 | `streamingAnswer`、`finalAnswer`、`draftAnswer` 分开 |
| 渐进迁移 | 保留现有 `/stream` 接口，新增 job 接口后先迁移单条生成 |
| 可测试 | Job service、事件补发、前端状态机都可单独测试 |

---

## 一、后端任务模型

### 1. 新增 Job 类型

**建议文件：**

- 新建：`app/services/generation_job_service.py`
- 新建：`app/models_streaming.py` 或放入 `app/models.py` 中独立区域

### 数据结构

```python
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field

GenerationJobStatus = Literal["pending", "running", "done", "error", "canceled"]
GenerationJobKind = Literal["generate_one", "generate_many", "polish_one"]
SseJobEventType = Literal["chunk", "item_start", "item_done", "done", "error", "heartbeat"]


class SseJobEvent(BaseModel):
    id: int
    event: SseJobEventType
    data: dict
    created_at: datetime = Field(default_factory=datetime.utcnow)


class GenerationJob(BaseModel):
    id: str
    kind: GenerationJobKind
    status: GenerationJobStatus = "pending"
    events: list[SseJobEvent] = Field(default_factory=list)
    payload: dict
    final_item: dict | None = None
    final_items: list[dict] | None = None
    error: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
```

### 2. 新增 GenerationJobService

**职责：**

- 创建 job。
- 启动后台生成任务。
- 追加事件并分配递增 event id。
- 查询 job。
- 根据 `Last-Event-ID` 获取缺失事件。
- 取消 job。
- 清理过期 job。

### 接口草图

```python
class GenerationJobService:
    def create_generate_one_job(self, payload: RegeneratePayload) -> GenerationJob: ...
    def get_job(self, job_id: str) -> GenerationJob | None: ...
    def append_event(self, job_id: str, event: str, data: dict) -> SseJobEvent: ...
    def events_after(self, job_id: str, last_event_id: int | None) -> list[SseJobEvent]: ...
    def mark_done(self, job_id: str, final_item: dict) -> None: ...
    def mark_error(self, job_id: str, message: str) -> None: ...
    def cancel_job(self, job_id: str) -> bool: ...
    async def wait_for_next_event(self, job_id: str, after_event_id: int, timeout: float) -> SseJobEvent | None: ...
```

### 3. 第一阶段缓存策略

第一阶段使用进程内内存缓存：

```python
jobs: dict[str, GenerationJob]
conditions: dict[str, asyncio.Condition]
tasks: dict[str, asyncio.Task]
```

要求：

- 每个 job 有自己的 `asyncio.Condition`，SSE 订阅端等待新事件时使用。
- append event 后通知所有订阅者。
- 完成后的 job 保留 30 分钟。
- 达到最大 job 数时清理最旧的已完成/失败 job。
- 运行中的 job 不允许被 TTL 清理。

---

## 二、后端 API

### 1. 新增路由文件

**建议文件：**

- 新建：`app/api/routes/generation_jobs.py`
- 修改：`app/server.py` 注册 router

### 2. 单条生成 Job 接口

#### `POST /api/workflow/generate-one/jobs`

输入：沿用当前 `RegeneratePayload`

输出：

```json
{
  "jobId": "gen_...",
  "status": "pending"
}
```

处理：

1. 校验 payload。
2. 创建 job。
3. 用 `asyncio.create_task()` 启动后台生成。
4. 立即返回 `jobId`。

#### `GET /api/workflow/generate-one/jobs/{jobId}`

输出：

```json
{
  "jobId": "gen_...",
  "status": "running",
  "lastEventId": 12,
  "finalItem": null,
  "error": null
}
```

完成后：

```json
{
  "jobId": "gen_...",
  "status": "done",
  "lastEventId": 34,
  "finalItem": { "...": "..." },
  "error": null
}
```

#### `GET /api/workflow/generate-one/jobs/{jobId}/stream`

返回 `text/event-stream`。

处理：

1. 从 header 读取 `Last-Event-ID`。
2. 补发所有 `id > Last-Event-ID` 的事件。
3. 如果 job 已经结束，补发完毕后关闭连接。
4. 如果 job 仍在运行，等待新事件并持续推送。
5. 定期发送 heartbeat。

#### `DELETE /api/workflow/generate-one/jobs/{jobId}`

取消任务。

第一阶段可只标记 `canceled`，若 LLM SDK 不支持中断底层请求，也要保证后续事件不再写入前端当前 item。

---

## 三、SSE 格式工具

### 1. 扩展 SSE 输出工具

**文件：**

- 修改：`app/api/sse_utils.py`

新增标准事件格式函数：

```python
def sse_named_event(event: SseJobEvent) -> str:
    return (
        f"id: {event.id}\n"
        f"event: {event.event}\n"
        f"data: {json.dumps(event.data, ensure_ascii=False)}\n\n"
    )
```

心跳事件：

```python
def sse_heartbeat() -> str:
    return f"event: heartbeat\ndata: {json.dumps({'ts': datetime.utcnow().isoformat()})}\n\n"
```

### 2. 保留旧函数

现有 `sse_event(payload)` 保留，继续服务旧 `/stream` 接口。

---

## 四、后台生成任务

### 单条生成执行流程

建议在 `GenerationJobService` 或独立 runner 中实现：

```python
async def run_generate_one_job(job_id: str) -> None:
    job = get_job(job_id)
    mark_running(job_id)

    full_text = ""
    try:
        async for chunk in answer_generator.generate_answer_stream(...):
            if is_canceled(job_id):
                return
            full_text += chunk
            append_event(job_id, "chunk", {"text": chunk})

        images = await image_service.generate_images_for_answer(item, full_text)
        final_item = item.model_copy(update={"answer": full_text.strip(), ...})

        mark_done(job_id, final_item.model_dump(by_alias=True))
        append_event(job_id, "done", {"item": final_item.model_dump(by_alias=True)})
    except Exception as e:
        mark_error(job_id, str(e))
        append_event(job_id, "error", {"message": str(e)})
```

关键约束：

- `chunk` 事件只包含增量文本。
- `done` 事件必须包含完整 item。
- `full_text.strip()` 的结果必须与最终 `done.item.answer` 一致。
- 如果图片生成缺少环境变量，沿用现有逻辑：不让图片错误影响回答完成。

---

## 五、前端 API

### 1. 新增类型

**文件：**

- 修改：`frontend/src/types/workflow.ts`

```typescript
export type GenerationJobStatus =
  | "pending"
  | "running"
  | "done"
  | "error"
  | "canceled";

export type CreateGenerationJobResponse = {
  jobId: string;
  status: GenerationJobStatus;
};

export type GenerationJobResponse = {
  jobId: string;
  status: GenerationJobStatus;
  lastEventId: number;
  finalItem?: QuestionItem | null;
  error?: string | null;
};
```

### 2. 新增 workflow-api 函数

**文件：**

- 修改：`frontend/src/features/workspace/workflow-api.ts`

```typescript
export function createGenerateOneJob(payload: GenerateOnePayload) {
  return apiPost<CreateGenerationJobResponse>("/api/workflow/generate-one/jobs", payload);
}

export function getGenerateOneJob(jobId: string) {
  return apiGet<GenerationJobResponse>(`/api/workflow/generate-one/jobs/${jobId}`);
}

export function cancelGenerateOneJob(jobId: string) {
  return apiDelete<void>(`/api/workflow/generate-one/jobs/${jobId}`);
}
```

### 3. 新增 EventSource client

**建议文件：**

- 新建：`frontend/src/lib/generation-event-source.ts`

接口：

```typescript
type GenerationEventSourceCallbacks = {
  onChunk: (text: string) => void;
  onDone: (item: QuestionItem) => void;
  onErrorEvent: (message: string) => void;
  onConnectionError?: () => void;
  onOpen?: () => void;
};

export function subscribeGenerateOneJob(
  jobId: string,
  callbacks: GenerationEventSourceCallbacks,
): EventSource;
```

注意：

- `source.addEventListener("chunk", ...)` 处理业务 chunk。
- `source.addEventListener("done", ...)` 处理完成并 `source.close()`。
- `source.addEventListener("error", ...)` 处理服务端业务错误事件。
- `source.onerror` 只表示连接异常/重连，不应立即标记生成失败。

---

## 六、前端状态设计

### 1. WorkbenchItem 增加生成任务字段

**文件：**

- 修改：`frontend/src/types/workflow.ts`

```typescript
export type WorkbenchItem = QuestionItem & {
  addedAt: string;
  sourcePlatform: Platform;
  sourceTopic: string;
  promptConfig: {
    answerStyle: string;
    systemPrompt: string;
    generationPrompt: string;
  };
  generationStatus?: GenerationStatus;
  generationError?: string;
  activeGenerationJobId?: string | null;
  streamingAnswer?: string;
  finalAnswer?: string;
  draftAnswer?: string;
};
```

### 2. Store action

**文件：**

- 修改：`frontend/src/store/workbench-store.ts`

新增 actions：

```typescript
setItemGenerationJob: (id: string, jobId: string | null) => void;
appendItemStreamingAnswer: (id: string, text: string) => void;
setItemStreamingAnswer: (id: string, answer: string) => void;
setItemFinalAnswer: (id: string, answer: string) => void;
setItemDraftAnswer: (id: string, answer: string) => void;
completeItemGeneration: (id: string, item: QuestionItem) => void;
```

语义：

- `streamingAnswer`：生成中预览。
- `finalAnswer`：`done` 的最终文本。
- `draftAnswer`：编辑器里的草稿。
- `answer`：兼容现有保存逻辑，完成后与 `draftAnswer` 同步。

---

## 七、WorkbenchAnswerPanel 迁移

**文件：**

- 修改：`frontend/src/features/workbench/workbench-answer-panel.tsx`

### 新流程

```
点击 AI 生成
    ↓
createGenerateOneJob(payload)
    ↓
store 写入 activeGenerationJobId + streaming 状态
    ↓
subscribeGenerateOneJob(jobId)
    ↓
chunk: append streamingAnswer
    ↓
done: completeItemGeneration + 挂载编辑器
```

### 渲染规则

```text
idle/error/interrupted:
  如果有 draftAnswer/answer，则显示 MarkdownEditor
  否则显示空编辑器或提示

streaming/running:
  显示只读预览
  不挂载 MarkdownEditor

done:
  显示 MarkdownEditor
  value 使用 draftAnswer ?? answer
```

### 取消和清理

- 组件 unmount 时 `EventSource.close()`。
- 用户重新生成时：
  - 如果有旧 `activeGenerationJobId`，先调用 cancel。
  - 清空 `streamingAnswer`。
  - 创建新 job。
- 用户切换问题时：
  - 不应误把 A 问题的 chunk 写入 B 问题。
  - 回调中必须使用生成开始时捕获的 `target.id`。

---

## 八、恢复机制

### 页面刷新恢复

第一阶段可把 active job 信息持久化到 `localStorage`：

```typescript
type ActiveGenerationJobSnapshot = {
  itemId: string;
  jobId: string;
  createdAt: string;
};
```

恢复流程：

1. 工作台加载时读取 `localStorage` active jobs。
2. 调用 `getGenerateOneJob(jobId)`。
3. 如果 `status === "running"`，重新订阅 EventSource。
4. 如果 `status === "done"`，用 `finalItem` 更新 item。
5. 如果 `status === "error"`，更新错误状态。
6. 如果 job 不存在或过期，清理 localStorage 并提示可重新生成。

如果当前工作台数据本身没有持久化，恢复可以作为后续增强；但 job 查询接口和订阅能力必须先具备。

---

## 九、测试计划

### 后端单元测试

**建议文件：**

- 新建：`tests/test_generation_job_service.py`
- 新建：`tests/test_generation_job_routes.py`

测试项：

- [ ] 创建 job 后返回唯一 `jobId`。
- [ ] append event 后 event id 从 1 开始递增。
- [ ] `events_after(job_id, 2)` 只返回 id 大于 2 的事件。
- [ ] job 完成后状态为 `done`，并保存 `final_item`。
- [ ] job error 后状态为 `error`，并保存错误信息。
- [ ] canceled job 不再追加新的 chunk。
- [ ] TTL 清理不会删除 running job。
- [ ] `Last-Event-ID` 补发逻辑正确。
- [ ] chunk 累加文本与 done.item.answer 一致。

### 前端测试

**建议文件：**

- 新建：`frontend/src/lib/generation-event-source.test.ts`
- 新建：`frontend/src/features/workbench/workbench-answer-panel.test.tsx`

测试项：

- [ ] `subscribeGenerateOneJob` 正确监听 `chunk` / `done` / `error`。
- [ ] `source.onerror` 不会直接触发业务失败。
- [ ] chunk 只更新 `streamingAnswer`。
- [ ] done 更新 `finalAnswer`、`draftAnswer` 和 `answer`。
- [ ] streaming 状态下不渲染 `MarkdownEditor`。
- [ ] done 状态下渲染 `MarkdownEditor`。
- [ ] 重复 event id 不重复追加。
- [ ] 切换 item 后旧 job 事件不会写入当前 item。

### 手工验证

- [ ] 正常生成：预览完整滚动，完成后编辑器显示完整答案。
- [ ] Chrome DevTools 断网：恢复网络后继续接收。
- [ ] 生成中刷新页面：重新进入后恢复订阅或显示最终结果。
- [ ] 生成完成后刷新页面：最终 answer 不丢失。
- [ ] 快速点击重新生成：只有最新 job 写入当前 item。
- [ ] 服务端返回 error：前端显示失败，不标记为已生成。

---

## 十、实施任务清单

### Task 1: 后端 Job 模型和服务

- [ ] 新增 `SseJobEvent` / `GenerationJob` 类型。
- [ ] 新增 `GenerationJobService`。
- [ ] 实现 job 创建、查询、状态更新。
- [ ] 实现 append event 和 event id 递增。
- [ ] 实现 `events_after()`。
- [ ] 实现 condition 通知机制。
- [ ] 实现 TTL 清理。

### Task 2: 后端标准 SSE 工具

- [ ] 在 `app/api/sse_utils.py` 新增标准 SSE named event 输出。
- [ ] 保留旧 `sse_event()`。
- [ ] 增加 heartbeat 输出函数。

### Task 3: 单条生成后台任务

- [ ] 实现 `run_generate_one_job()`。
- [ ] 复用现有 `DeepSeekAnswerGenerator.generate_answer_stream()`。
- [ ] 复用现有图片生成逻辑。
- [ ] 保证 `done` 事件携带完整 item。
- [ ] error 时写入 `event: error`。

### Task 4: 后端 Job API

- [ ] 新增 `POST /api/workflow/generate-one/jobs`。
- [ ] 新增 `GET /api/workflow/generate-one/jobs/{jobId}`。
- [ ] 新增 `GET /api/workflow/generate-one/jobs/{jobId}/stream`。
- [ ] 新增 `DELETE /api/workflow/generate-one/jobs/{jobId}`。
- [ ] 在 `app/server.py` 注册路由。

### Task 5: 后端测试

- [ ] 覆盖 job service。
- [ ] 覆盖 Last-Event-ID 补发。
- [ ] 覆盖 route 基本行为。
- [ ] 覆盖 chunk 与 done 最终文本一致性。

### Task 6: 前端类型和 API

- [ ] 增加 `GenerationJobStatus` 等类型。
- [ ] 增加 create/get/cancel job API 函数。
- [ ] 新增 `generation-event-source.ts`。
- [ ] 明确区分业务 `event: error` 和连接 `source.onerror`。

### Task 7: Workbench store 状态拆分

- [ ] 增加 `activeGenerationJobId`。
- [ ] 增加 `streamingAnswer`。
- [ ] 增加 `finalAnswer`。
- [ ] 增加 `draftAnswer`。
- [ ] 增加对应 actions。
- [ ] 保持 `answer` 字段兼容现有保存逻辑。

### Task 8: WorkbenchAnswerPanel 迁移

- [ ] 将单条生成从 `streamGenerateOneAnswer()` 切到 job API。
- [ ] 生成中只显示只读预览。
- [ ] 生成完成后才挂载 `MarkdownEditor`。
- [ ] 重新生成前取消旧 job。
- [ ] 切换问题时避免旧回调写错 item。
- [ ] done 后同步 `answer` / `finalAnswer` / `draftAnswer`。

### Task 9: 恢复和清理

- [ ] 记录 active job 到 localStorage。
- [ ] 页面加载时查询 job 状态。
- [ ] running job 重新订阅。
- [ ] done job 直接恢复最终结果。
- [ ] error/expired job 清理本地记录。

### Task 10: 前端测试与回归

- [ ] 增加 EventSource client 测试。
- [ ] 增加 WorkbenchAnswerPanel 状态测试。
- [ ] 运行 `cd frontend && bun run typecheck`。
- [ ] 运行后端相关测试。
- [ ] 手工验证断网、刷新、重复生成。

---

## 十一、迁移顺序建议

第一阶段只迁移工作台单条生成：

```
WorkbenchAnswerPanel
  old: streamGenerateOneAnswer()
  new: createGenerateOneJob() + EventSource
```

旧接口继续保留：

```
POST /api/workflow/generate-one/stream
POST /api/workflow/generate/stream
POST /api/workflow/polish-one/stream
```

单条生成稳定后，再评估迁移：

1. 批量生成 `generate/stream`
2. 单条润色 `polish-one/stream`
3. Agent chat stream

---

## 十二、验收标准

- [ ] 正常生成时，前端最终显示内容与 `done.item.answer` 完全一致。
- [ ] 收到 `done` 前，问题状态不会显示“已生成”。
- [ ] DevTools 模拟断网后恢复，EventSource 自动重连并继续接收。
- [ ] 重连后不会重复追加已收到 chunk。
- [ ] 页面刷新后可恢复 running/done job。
- [ ] 生成中页面不挂载 `MarkdownEditor`。
- [ ] 完成后编辑器可正常编辑最终答案。
- [ ] 后端测试和前端 typecheck 通过。

