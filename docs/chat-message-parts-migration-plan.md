# Chat 消息多 Part 数据模型与历史迁移方案

> 状态：设计方案，尚未实施
> 目标：一次用户提问对应一个 assistant 回答气泡；一个回答气泡可以同时展示思考摘要、工具状态、RAG 来源、帖子结果、正文、选择请求和错误信息。

## 1. 背景与当前问题

当前消息模型定义在：

- `frontend/src/features/chat/conversation/model/chat-message-tree.ts`
- `app/infrastructure/database/models/chats.py`

核心结构为：

```ts
type ChatMessage = {
  messageId: string;
  role: "user" | "assistant" | "tool";
  messageType:
    | "text"
    | "source_card"
    | "source_list"
    | "tool_status"
    | "error"
    | "choice_request";
  content: string | null;
  parentMessageId?: string | null;
  payload: any;
  createdAt: string;
};
```

该模型存在以下问题：

1. 一条消息只能拥有一个 `messageType`，无法自然表达“一次回答包含多种内容”。
2. `payload: any` 没有编译期约束，不同消息类型的字段依赖运行时约定。
3. 工具结果作为顶层消息保存时，前端容易把一次回答渲染成多个平级 Card。
4. RAG 引用、帖子搜索结果、工具调用和正文之间没有稳定的 ID 关联。
5. 历史消息和流式消息使用两套不同的渲染状态，容易出现行为不一致。
6. 前端存在重复的 `ChatMessage` 定义，需要统一。

当前普通 Chat 流已经把 `ragSources` 和 `sourceList` 聚合进最终文本消息的 `payload`，避免产生平级分支；这说明“一次回答一个气泡”已经是当前产品实际需要，但现有数据结构仍停留在单 `messageType` 模型。

## 2. 外部方案调研结论

### 2.1 OpenAI Responses API

OpenAI Responses API 使用 `response.output` 表示一次响应产生的多个 typed Item。`reasoning`、`message`、`function_call` 和 `function_call_output` 是不同 Item；工具调用与结果通过 `call_id` 关联，正文引用通过 `annotations` 关联。

参考：<https://developers.openai.com/api/docs/guides/migrate-to-responses>

### 2.2 Claude Messages API

Claude 的一条 assistant Message 包含多个有序 Content Block，例如 `thinking`、`tool_use` 和 `text`，而不是把每个块都作为独立聊天消息。

参考：<https://platform.claude.com/docs/en/api/messages>

### 2.3 Google Gemini Content/Part

Gemini 使用 `Content` 表示一个消息回合，`Content.parts` 保存有序的多段内容。Part 可以包含文本、思考标记、函数调用和函数结果。

参考：<https://ai.google.dev/api/generate-content>

### 2.4 Vercel AI SDK UIMessage

Vercel AI SDK 的 UI 数据模型最适合直接参考：一条 `UIMessage` 包含多个 `parts`，Part 支持文本、reasoning、工具生命周期、URL 来源、文档来源、文件和自定义数据，并具有流式状态。

参考：<https://ai-sdk.dev/docs/reference/ai-sdk-core/ui-message>

### 2.5 本项目采用的结论

本项目采用以下组合：

- UI 消息结构主要参考 Vercel `UIMessage.parts`、Claude Content Block 和 Gemini Part。
- 工具生命周期和关联方式参考 OpenAI typed Item 与 `call_id`。
- 一条顶层 `ChatMessage` 对应一个聊天气泡。
- 一条消息内部包含多个有序、强类型的 Part。
- 工具不再作为新数据的顶层 `role: "tool"` 消息，而是 assistant 消息中的 Tool Part。
- 文本引用通过 `sourceId` 和 annotation 关联。
- 每个 Part 拥有自己的流式状态。

## 3. 目标消息结构

```ts
type ChatMessage = {
  schemaVersion: 2;
  messageId: string;
  role: "user" | "assistant";
  parentMessageId: string | null;
  runId: string | null;
  status: "streaming" | "completed" | "failed" | "awaiting_input";
  parts: ChatMessagePart[];
  metadata?: {
    traceId?: string;
    model?: string;
    legacyMessageIds?: string[];
  };
  createdAt: string;
};
```

Part 使用判别联合类型：

```ts
type ChatMessagePart =
  | TextPart
  | ReasoningPart
  | ToolPart
  | SourcePart
  | PostResultsPart
  | ChoicePart
  | ErrorPart
  | TaskPlanPart
  | MultiAgentPart
  | LegacyPart;
```

### 3.1 TextPart

```ts
type TextPart = {
  id: string;
  type: "text";
  text: string;
  state: "streaming" | "done";
  annotations?: CitationAnnotation[];
};

type CitationAnnotation = {
  type: "citation";
  sourceId: string;
  startIndex?: number;
  endIndex?: number;
};
```

### 3.2 ReasoningPart

```ts
type ReasoningPart = {
  id: string;
  type: "reasoning";
  summary: string;
  state: "streaming" | "done";
};
```

只保存模型提供的 reasoning summary 或处理步骤，不保存和展示模型内部原始思维链。

### 3.3 ToolPart

```ts
type ToolPart = {
  id: string;
  type: "tool";
  toolCallId: string;
  toolName: string;
  state:
    | "input-streaming"
    | "input-available"
    | "output-available"
    | "output-error";
  input?: unknown;
  output?: unknown;
  errorText?: string;
};
```

### 3.4 SourcePart

```ts
type SourcePart = {
  id: string;
  type: "sources";
  sourceKind: "rag" | "web";
  sources: SourceItem[];
  traceId?: string;
  fallbackNotice?: string;
};
```

### 3.5 PostResultsPart

```ts
type PostResultsPart = {
  id: string;
  type: "post-results";
  toolName: string;
  items: SourceItem[];
};
```

### 3.6 ChoicePart 与 ErrorPart

```ts
type ChoicePart = {
  id: string;
  type: "choice";
  question: string;
  options: ChoiceOption[];
  requestMessageId?: string;
};

type ErrorPart = {
  id: string;
  type: "error";
  code?: string;
  message: string;
};
```

### 3.7 完整回答示例

```ts
const message: ChatMessage = {
  schemaVersion: 2,
  messageId: "assistant-1",
  role: "assistant",
  parentMessageId: "user-1",
  runId: "run-1",
  status: "completed",
  parts: [
    {
      id: "reasoning-1",
      type: "reasoning",
      summary: "先检索知识库，再搜索相关帖子。",
      state: "done",
    },
    {
      id: "tool-rag-1",
      type: "tool",
      toolCallId: "call-rag-1",
      toolName: "rag_search",
      state: "output-available",
      input: { query: "同余定理" },
      output: { sourceIds: ["source-1"] },
    },
    {
      id: "sources-1",
      type: "sources",
      sourceKind: "rag",
      sources: [],
      traceId: "trace-1",
    },
    {
      id: "posts-1",
      type: "post-results",
      toolName: "post_search",
      items: [],
    },
    {
      id: "text-1",
      type: "text",
      text: "同余是指两个整数除以同一个正整数后余数相同……",
      state: "done",
      annotations: [{ type: "citation", sourceId: "source-1" }],
    },
  ],
  metadata: {
    traceId: "trace-1",
    model: "deepseek",
  },
  createdAt: "2026-08-28T10:00:00Z",
};
```

## 4. 数据库扩展方案

保留 `messages` 表的旧字段：

- `role`
- `message_type`
- `content`
- `payload`

新增字段：

| 字段 | 类型 | 初始约束 | 用途 |
|---|---|---|---|
| `schema_version` | `SMALLINT` | `NOT NULL DEFAULT 1` | 区分旧消息和 Part 消息 |
| `parts` | `JSONB` | 可空 | 有序消息 Part |
| `status` | `VARCHAR(20)` | `NOT NULL DEFAULT 'completed'` | 消息生命周期 |
| `message_metadata` | `JSONB` | 可空 | trace、model、历史 ID 等元数据 |

`parts` 增加约束：

```sql
parts IS NULL OR jsonb_typeof(parts) = 'array'
```

第一阶段不删除旧字段，也不增加只允许 `user | assistant` 的数据库约束，因为历史记录中仍可能存在 `role = 'tool'`。

当前没有按 Part 内容查询的需求，因此暂时不为 `parts` 创建 GIN 索引。

## 5. 历史数据转换规则

| 旧 message_type / payload | 新 Part |
|---|---|
| `text` | `text` |
| `text + ragSources` | `text` + `sources` |
| `text + sourceList` | `text` + `post-results` |
| `text + taskPlanResult` | `text` + `data-task-plan` |
| `text + multiAgentResult` | `text` + `data-multi-agent` |
| `source_card` | `post-results` 或 `sources` |
| `source_list` | `post-results` |
| `tool_status` | `tool` |
| `error` | `error` |
| `choice_request` | `choice` |
| `hitl_selection` | `data-choice-selection` |
| 未知类型 | `legacy` |

未知类型必须无损保留：

```ts
type LegacyPart = {
  id: string;
  type: "legacy";
  legacyType: string;
  content: string | null;
  payload: unknown;
};
```

## 6. 历史多消息组合策略

不能直接删除或物理合并历史消息，原因包括：

- `parent_message_id` 可能引用旧消息。
- HITL 接口依赖 `choice_request` 的原始消息 ID。
- 对话分支可能使用旧消息作为叶子或父节点。
- 物理合并会增加不可逆迁移和回滚风险。

因此历史组合放在读取兼容层中完成，不修改原始关系。

只有满足以下条件的历史消息才自动组合：

1. `chat_id` 相同。
2. `run_id` 相同且不为空。
3. 属于同一次 assistant 执行。
4. 不跨越 `choice_request` 或 `hitl_selection` 边界。

组合规则：

1. 优先选择最终 `text` 消息作为气泡 `messageId`。
2. 没有文本时选择最后一条终态消息。
3. 其他记录转换为 Part，并按 `created_at` 排序。
4. 所有旧 ID 写入 `metadata.legacyMessageIds`。
5. API DTO 中通过 `旧 ID → 主消息 ID` 别名表重写 `parentMessageId`。
6. `choice` Part 保留真实 `requestMessageId`，确保选择提交接口继续可用。
7. `run_id` 为空或归属不明确的数据不做推测性组合。

当前 `get_messages()` 在数据库行级别限制为 100 条。引入组合后，分页或 limit 必须作用于组合后的消息回合，而不是在组合前截断数据库行，否则可能截断同一次回答。

## 7. 双读双写兼容方案

### 7.1 新写入入口

新增统一服务入口：

```py
save_chat_message(
    role,
    parts,
    status,
    parent_message_id,
    run_id,
)
```

新消息写入：

- `schema_version = 2`
- `parts`
- `status`
- `message_metadata`

同时从 Part 投影生成旧字段：

- `message_type`
- `content`
- `payload`

这样新客户端读取 `parts`，旧服务和旧客户端仍能读取旧字段。

现有 `save_user_message()` 和 `save_assistant_message()` 暂时保留，但内部逐步委托给新保存入口。

### 7.2 API 读取

兼容期响应同时包含新旧字段：

```json
{
  "schemaVersion": 2,
  "messageId": "...",
  "role": "assistant",
  "status": "completed",
  "parts": [],
  "messageType": "text",
  "content": "...",
  "payload": {},
  "parentMessageId": "...",
  "runId": "...",
  "createdAt": "..."
}
```

新前端优先使用 `parts`。如果 `parts` 不存在，则调用 `convertLegacyMessageToParts()`。

## 8. SSE 协议调整

当前事件包括：

- `agent.status`
- `tool.started`
- `message.delta`
- `source.list.completed`
- `run.completed`

新增通用 Part 事件：

- `message.started`
- `message.part.started`
- `message.part.delta`
- `message.part.completed`
- `message.completed`
- `message.failed`

文本增量示例：

```json
{
  "messageId": "assistant-1",
  "partId": "text-1",
  "type": "text",
  "delta": "同余是指……"
}
```

工具完成示例：

```json
{
  "messageId": "assistant-1",
  "partId": "tool-1",
  "toolCallId": "call-1",
  "type": "tool",
  "state": "output-available"
}
```

兼容期同时发送旧事件和新事件。前端完全切换后再停止旧事件。

## 9. 前端改造方案

### 9.1 类型统一

当前以下位置存在不同的 `ChatMessage`：

- `frontend/src/features/chat/conversation/model/chat-message-tree.ts`
- `frontend/src/types/workflow.ts`

统一到：

```text
frontend/src/features/chat/conversation/types/chat-message.ts
```

该文件定义：

- `LegacyChatMessageDTO`
- `ChatMessage`
- `ChatMessagePart`
- 各具体 Part
- 历史转换函数的输入输出类型

### 9.2 统一渲染器

```tsx
<MessageBubble>
  <MessageParts parts={message.parts} />
</MessageBubble>
```

`MessageParts` 根据 Part 类型选择独立组件：

```tsx
parts.map((part) => {
  switch (part.type) {
    case "text":
      return <TextPartView />;
    case "reasoning":
      return <ReasoningPartView />;
    case "tool":
      return <ToolPartView />;
    case "sources":
      return <SourcesPartView />;
    case "post-results":
      return <PostResultsPartView />;
  }
});
```

公共 Card 只在 `MessageBubble` 中渲染一次。

历史消息和流式消息必须复用同一个 `MessageParts` 渲染器，避免 `StreamingMessageCard` 与历史消息形成两套展示逻辑。

### 9.3 Streaming Controller

快照由：

```ts
{
  streamingText,
  streamingSourceList,
  streamingError,
}
```

改为：

```ts
{
  messageId,
  status,
  parts,
}
```

文本 Buffer 仍然只负责对应 Text Part 的批量提交，保持当前流式状态完全下沉的性能特性，不让 SSE chunk 触发 `ChatPanel` 和历史消息列表高频渲染。

## 10. 历史数据迁移流程

### 10.1 Schema Migration

Alembic 只负责新增字段和约束，不在单个迁移事务中批量重写所有历史消息。

### 10.2 幂等回填命令

新增命令：

```bash
uv run python -m app.cli migrate-chat-message-parts
```

支持：

```text
--dry-run
--batch-size
--chat-id
--resume-after
```

按主键游标分批处理，例如每批 500 条：

```sql
WHERE parts IS NULL
ORDER BY id
LIMIT 500
```

每条记录执行：

1. 读取旧字段。
2. 转换为 Part。
3. 写入 `parts`。
4. 设置 `schema_version = 2`。
5. 保留所有旧字段。
6. 未知类型写成 `legacy` Part 并记录日志。

### 10.3 迁移校验

必须验证：

- 迁移前后数据库消息总数不变。
- 旧 `content` 和 `payload` 可以在新 Part 或 Legacy Part 中找到。
- `parent_message_id`、`run_id` 和消息 ID 不变。
- `choice_request` 原始 ID 不变。
- 所有 `schema_version = 2` 的 `parts` 都是合法数组。
- 重复执行迁移不会产生重复 Part。

### 10.4 读取组合开关

完成单行回填并验证后，再开启基于 `run_id` 的读取时组合。组合只改变 API DTO，不修改数据库原始关系。

## 11. 灰度发布顺序

1. 增加 Part 类型、转换器和契约测试。
2. 增加数据库字段。
3. 后端上线双读双写，但默认保持旧展示行为。
4. 前端上线 Part 渲染器和历史转换器。
5. 开启新 SSE Part 事件。
6. 开启新消息写入。
7. 执行历史数据回填。
8. 开启历史 `run_id` 组合展示。
9. 观察至少一个稳定发布周期。
10. 最后再评估删除旧字段和旧 SSE 事件。

建议增加配置开关：

```text
CHAT_MESSAGE_PARTS_WRITE_ENABLED
CHAT_MESSAGE_PARTS_READ_ENABLED
CHAT_MESSAGE_LEGACY_GROUPING_ENABLED
```

## 12. 回滚方案

稳定期内必须满足：

- 不删除旧字段。
- 新消息始终同步生成旧字段。
- 不物理合并历史消息。
- 不修改历史 `messageId` 和 `parent_message_id`。

出现问题时关闭：

```text
CHAT_MESSAGE_PARTS_READ_ENABLED=false
```

即可恢复读取 `messageType + content + payload`，不需要回滚历史数据。

## 13. 测试计划

### 后端

- 每一种旧 `message_type` 到 Part 的映射测试。
- 未知类型无损转换测试。
- 双写投影测试。
- 相同 `run_id` 历史消息组合测试。
- parent ID 别名重写测试。
- 分支消息不被错误合并测试。
- HITL choice ID 保持测试。
- 回填命令幂等测试。
- 数据库迁移集成测试。
- 新旧 API 字段兼容测试。
- 新旧 SSE 事件兼容测试。

### 前端

- 一条 assistant 消息包含多个 Part 时只渲染一个 Card。
- 每一种 Part 使用对应组件。
- 历史消息转换测试。
- 流式 Part 增量、完成和错误状态测试。
- choice、RAG、帖子卡片交互测试。
- 对话分支切换测试。
- SSE 文本增量不触发 `ChatPanel` 高频渲染测试。

## 14. 验收标准

- 一次 assistant 回答只渲染一个 Card。
- 同一个 Card 可以同时显示思考摘要、工具状态、RAG 来源、帖子结果和正文。
- Part 具有强类型，不再依赖 `payload: any` 判断结构。
- 工具调用与结果通过 `toolCallId` 稳定关联。
- 引用与正文通过 `sourceId` 稳定关联。
- 新旧消息可以在同一会话中正常展示。
- 历史分支、编辑消息和 HITL 选择保持可用。
- 数据迁移可暂停、恢复、重复执行且不丢数据。
- SSE chunk 不触发父组件和历史消息列表高频渲染。
- 关闭功能开关后能够立即恢复旧读取路径。
