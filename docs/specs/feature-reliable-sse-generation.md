# Feature: Reliable SSE Generation — 可靠的流式生成任务

## 背景与问题

当前工作台的 AI 回答生成使用 `fetch + ReadableStream` 直接请求流式接口：

```
POST /api/workflow/generate-one/stream
```

这个方案可以工作，但它把“生成任务”和“当前 HTTP 连接”绑定在一起：

```
一次 HTTP 连接 = 一次生成任务
连接断开 = 前端失去后续数据
```

在实际使用中，这会带来几个稳定性问题：

- 网络抖动或页面刷新后，前端无法继续接收已经开始生成的内容。
- 当前流式协议由前端手写解析，边界情况需要自己维护。
- 没有 `Last-Event-ID`，无法做断点续传。
- 生成中的文本、最终文本、编辑器草稿曾混用同一个 `answer` 状态，容易让富文本编辑器内部状态覆盖流式结果。
- 如果没有收到 `done`，只能判断为中断，不能从上次事件继续恢复。

目标不是给错误兜底，而是把流式生成升级成可靠的任务订阅模型。

## 目标

将 AI 生成从“单连接流式返回”升级为“两阶段任务 + EventSource 订阅 + 事件 ID + 服务端事件缓存”的可靠流式架构。

最终效果：

1. 前端先创建生成任务，拿到 `jobId`。
2. 前端用 `EventSource` 订阅该任务的 SSE 流。
3. 服务端每个事件带递增 `id`。
4. 网络断开后，浏览器自动重连。
5. 重连时浏览器带上 `Last-Event-ID`。
6. 服务端根据事件缓存补发缺失事件。
7. 收到 `done` 后，前端用最终完整 `answer` 确认结果。
8. 生成中只渲染只读预览，生成完成后再进入编辑器。

---

## 现有代码（不得破坏）

| 文件/接口 | 现有功能 | 约束 |
|---|---|---|
| `POST /api/workflow/generate-one/stream` | 单条回答流式生成 | 保留兼容，新增可靠任务接口后再逐步迁移 |
| `POST /api/workflow/generate/stream` | 批量回答流式生成 | 保留兼容，后续可复用同一任务模型 |
| `POST /api/workflow/polish-one/stream` | 单条润色流式生成 | 保留兼容，后续可复用同一任务模型 |
| `app/api/routes/stream.py` | 现有流式路由 | 不直接删除旧路由 |
| `frontend/src/lib/sse.ts` | 当前 `fetch + ReadableStream` SSE 解析器 | 保留给旧接口和非 EventSource 场景 |
| `WorkbenchAnswerPanel` | 工作台回答生成入口 | 迁移时保持现有按钮和交互语义 |
| `MarkdownEditor` | 最终回答编辑器 | 不参与 token 级流式渲染 |

---

## 推荐架构

### 两阶段任务模型

```
用户点击 AI 生成
        │
        ▼
POST /api/workflow/generate-one/jobs
        │
        ▼
返回 { jobId }
        │
        ▼
new EventSource("/api/workflow/generate-one/jobs/{jobId}/stream")
        │
        ▼
chunk / done / error 事件持续到达
```

### 新增接口

| 接口 | 方法 | 作用 |
|---|---|---|
| `/api/workflow/generate-one/jobs` | POST | 创建单条回答生成任务，返回 `jobId` |
| `/api/workflow/generate-one/jobs/{jobId}` | GET | 查询任务当前状态和最终结果 |
| `/api/workflow/generate-one/jobs/{jobId}/stream` | GET | 使用 `EventSource` 订阅任务事件流 |
| `/api/workflow/generate-one/jobs/{jobId}` | DELETE | 取消任务（可选，但建议实现） |

后续批量生成和润色可复用同一模式：

```
POST /api/workflow/generate/jobs
GET  /api/workflow/generate/jobs/{jobId}/stream

POST /api/workflow/polish-one/jobs
GET  /api/workflow/polish-one/jobs/{jobId}/stream
```

---

## 服务端设计

### Job 数据模型

```python
class GenerationJob:
    id: str
    kind: Literal["generate_one", "generate_many", "polish_one"]
    status: Literal["pending", "running", "done", "error", "canceled"]
    events: list[SseJobEvent]
    payload: dict
    final_item: dict | None
    final_items: list[dict] | None
    error: str | None
    created_at: datetime
    updated_at: datetime
```

### Event 数据模型

```python
class SseJobEvent:
    id: int
    event: Literal["chunk", "item_start", "item_done", "done", "error", "heartbeat"]
    data: dict
    created_at: datetime
```

事件 `id` 必须在同一个 job 内单调递增。

### SSE 输出格式

使用标准 SSE 字段，而不是只在 `data` 中塞 `type`：

```text
id: 1
event: chunk
data: {"text":"第一段"}

id: 2
event: chunk
data: {"text":"第二段"}

id: 3
event: done
data: {"item":{"answer":"完整答案"}}
```

错误事件：

```text
id: 4
event: error
data: {"message":"生成失败"}
```

心跳事件：

```text
event: heartbeat
data: {"ts":"2026-07-03T12:00:00Z"}
```

### 断点续传

`EventSource` 重连时，浏览器会自动带上：

```http
Last-Event-ID: 12
```

服务端逻辑：

1. 读取 `Last-Event-ID`。
2. 从 job 的 `events` 中找到 `id > Last-Event-ID` 的事件。
3. 先补发缺失事件。
4. 如果 job 仍在运行，继续等待并推送新事件。
5. 如果 job 已完成，补发到 `done` 后关闭连接。

### 任务生命周期

```
pending → running → done
                 ↘ error
                 ↘ canceled
```

要求：

- 创建 job 后立即返回 `jobId`，生成任务在后台执行。
- 生成任务不依赖某个 SSE 连接是否仍然存在。
- SSE 连接只是订阅 job 事件，不负责驱动 job 生命周期。
- 任务完成后事件至少保留一段时间，供页面刷新或短线重连恢复。

### 事件缓存策略

第一阶段可使用内存缓存：

```text
jobId -> GenerationJob
```

要求：

- 支持按 `jobId` 读取事件。
- 支持 TTL 清理，例如完成后保留 30 分钟。
- 支持最大 job 数限制，避免本地长期运行导致内存增长。

后续如需要跨进程或服务重启恢复，可升级为 SQLite 或文件持久化。

---

## 前端设计

### 状态拆分

回答相关状态必须拆开，不再让同一个字段同时承担所有职责：

```typescript
type GenerationUiState = {
  jobId: string | null;
  status: "idle" | "creating" | "streaming" | "done" | "error" | "canceled";
  streamingAnswer: string;
  finalAnswer: string;
  draftAnswer: string;
  error: string | null;
};
```

语义：

| 字段 | 用途 |
|---|---|
| `streamingAnswer` | 生成中的只读预览，来自 chunk 事件累加 |
| `finalAnswer` | 收到 `done` 后确认的完整回答 |
| `draftAnswer` | 用户进入编辑器后修改的草稿 |

### 渲染规则

```
生成中：
  渲染只读 Markdown/纯文本预览
  不挂载 MarkdownEditor / MDXEditor

生成完成：
  finalAnswer 初始化 draftAnswer
  挂载 MarkdownEditor
  用户编辑 draftAnswer
```

核心约束：

**富文本编辑器不得参与 token 级流式更新。**

原因：

- 编辑器通常维护内部文档模型，不适合高频外部 `setMarkdown`。
- `onChange` 回写可能把旧的内部状态写回 store。
- 流式预览和富文本编辑是两个不同阶段，应明确分离。

### EventSource 客户端流程

```typescript
async function startGeneration(payload: GenerateOnePayload) {
  setStatus("creating");

  const { jobId } = await createGenerationJob(payload);

  setStatus("streaming");
  setJobId(jobId);
  setStreamingAnswer("");

  const source = new EventSource(`/api/workflow/generate-one/jobs/${jobId}/stream`);

  source.addEventListener("chunk", (event) => {
    const data = JSON.parse(event.data);
    appendStreamingAnswer(data.text);
  });

  source.addEventListener("done", (event) => {
    const data = JSON.parse(event.data);
    setFinalAnswer(data.item.answer);
    setDraftAnswer(data.item.answer);
    setItem(data.item);
    setStatus("done");
    source.close();
  });

  source.addEventListener("error", (event) => {
    const data = JSON.parse((event as MessageEvent).data || "{}");
    setError(data.message || "生成失败");
    setStatus("error");
    source.close();
  });
}
```

注意：

- `EventSource.onerror` 不应立即标记失败，因为它也会在浏览器准备重连时触发。
- 只有收到服务端业务 `event: error`，或超出自定义重连超时后，才进入失败状态。
- 用户离开页面时需要 `source.close()`。

### 页面刷新恢复

如果用户刷新页面或切换页面后回来：

1. 如果本地仍保存 `jobId` 且 job 未完成，调用 `GET /api/workflow/generate-one/jobs/{jobId}`。
2. 如果 job 仍在运行，重新创建 `EventSource`。
3. 如果 job 已完成，直接读取 `finalItem` 并进入完成状态。
4. 如果 job 已过期，提示任务已过期，可重新生成。

---

## 可靠性要求

### 必须保证

- 收到 `done` 前不得标记为“已生成”。
- 收到 `done` 后必须以后端 `done.item.answer` 作为最终结果。
- 网络断开后，浏览器自动重连，服务端补发缺失事件。
- 页面刷新后，未完成任务可以恢复订阅。
- 连接断开不应取消后端生成任务。
- 编辑器不得在生成中回写流式内容。

### 推荐保证

- SSE 流每隔固定时间发送 heartbeat，避免代理或浏览器长时间无数据断开。
- 前端维护最大重连等待时间，例如 60 秒；超过后提示用户。
- 后端 job 支持取消，避免用户重复点击造成无用 LLM 调用。
- 同一个 item 同一时间只允许一个 active generation job。

---

## 效率要求

虽然两阶段方案多一次 HTTP 请求，但整体效率更好：

- 网络抖动后无需重新生成，节省 LLM token。
- 页面刷新后可恢复任务，避免重复生成。
- 事件补发只传缺失片段，不重跑完整回答。
- 浏览器原生处理 SSE 解析和重连，减少前端手写协议风险。

前端渲染层建议对 chunk UI 更新做节流：

```text
chunk 到达：立即写入 buffer
UI 更新：每 50-100ms flush 一次
done 到达：立即 flush 并设置最终结果
```

这样可以降低 Zustand/React 高频重渲染压力。

---

## 错误处理

| 场景 | 处理 |
|---|---|
| 创建 job 失败 | 前端停留 idle/error，显示错误 |
| EventSource 网络断开 | 不立即失败，等待自动重连 |
| 重连超过超时时间 | 标记为 interrupted，可继续尝试恢复 |
| 服务端 `event: error` | 标记为 error，展示 message |
| job 不存在 | 提示任务不存在，可重新生成 |
| job 已过期 | 提示任务已过期，可重新生成 |
| 收到乱序事件 | 忽略小于等于当前 lastEventId 的事件 |
| 重复事件 | 根据 event id 去重 |

---

## 测试策略

### 后端测试

- 创建 job 返回 `jobId`。
- job 事件 id 单调递增。
- chunk 事件累加后等于 done 中的最终 answer。
- 带 `Last-Event-ID` 订阅时，只补发缺失事件。
- job 完成后再次订阅，可以补发到 `done`。
- job 运行中连接断开，后台任务继续执行。
- job error 时发送 `event: error`。
- TTL 清理不会删除仍在运行的 job。

### 前端测试

- 创建 job 后打开 EventSource。
- chunk 事件只更新 streaming preview。
- done 事件更新 final answer 和 draft answer。
- 生成中不渲染 `MarkdownEditor`。
- 生成完成后才挂载 `MarkdownEditor`。
- `EventSource.onerror` 不会立即把任务标记失败。
- 页面恢复时根据 job 状态重新订阅或读取最终结果。
- 重复事件不会重复追加文本。

### 手工验证

1. 正常生成：能看到流式预览，完成后编辑器显示完整答案。
2. DevTools 中断网络：恢复网络后继续接收缺失内容。
3. 生成中刷新页面：重新进入后继续显示任务进度。
4. 生成完成后刷新页面：直接显示完整答案。
5. 快速重复点击生成：不会产生多个互相覆盖的任务。

---

## 实现顺序

1. 新增后端 job service：负责创建 job、追加事件、查询状态、TTL 清理。
2. 新增 `POST /api/workflow/generate-one/jobs` 创建任务接口。
3. 新增 `GET /api/workflow/generate-one/jobs/{jobId}/stream` EventSource 订阅接口。
4. 为 SSE 事件增加标准 `id`、`event`、`data` 输出。
5. 实现 `Last-Event-ID` 补发逻辑。
6. 前端新增 EventSource job client。
7. 工作台单条生成迁移到两阶段任务。
8. 拆分 `streamingAnswer` / `finalAnswer` / `draftAnswer`。
9. 确保生成中只渲染只读预览，完成后再挂载编辑器。
10. 补充后端和前端测试。
11. 稳定后再评估批量生成、润色流式接口迁移。

---

## 非目标

本 Feature 不处理以下内容：

- 不改变 LLM 提示词和回答质量策略。
- 不改变 URL 导入和问题解析逻辑。
- 不新增多 Agent 编排能力。
- 不要求第一阶段实现跨进程持久化。
- 不删除旧的 `fetch + ReadableStream` 流式接口。

---

## 依赖

无强制前置 Feature。

建议在实现前先完成一次工作台生成链路回归测试，确保现有 URL 导入、单条生成、回答编辑功能的当前行为被记录下来，便于迁移后对比。
