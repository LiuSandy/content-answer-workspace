# Feature: Agent Chat Page — 对话页面与多 Session 管理（第一阶段）

## 背景与问题

当前 Agent 能力局限在两个写死的固定流程（`RefinementGraph` 精修回答、`AnalysisGraph` 热榜分析），都是嵌在已有页面里的"发一条消息→等一个结果"单轮交互，没有真正的多轮对话记忆，也没有独立的对话入口。

项目要往"以 Agent 为核心"的方向重构，第一步是：

1. 新增一个独立的对话页面，支持真正的多轮聊天。
2. 升级 Session 模型，支持创建/列出/切换多个会话，对话和工作区数据（采集结果、回答）绑定在同一个 session 上。
3. **不在本阶段接入工具调用**——Agent 暂时只靠多轮对话本身的推理/创作能力工作，不会去调用采集、生成、润色等现有后端动作。等对话能力稳定后，是否把这些功能交给 Agent 调用，留作后续独立的 Feature 来评估。

## 现有代码（不得破坏）

| 文件/接口 | 现有功能 | 本次是否改动 |
|---|---|---|
| `POST /api/agent/chat` | 精修对话 / 热榜分析，按 `questionId` 是否存在路由 | **不改**，新对话能力走独立新接口 |
| `app/application/agent/graphs/refinement.py`、`analysis.py` | 现有两个固定流程图 | **不改** |
| `frontend/.../refinement-chat.tsx`、`hotlist-analysis-panel.tsx` | 现有两处嵌入式对话 UI | **不改**，继续用 `/api/agent/chat` |
| `app/api/routes/session.py` | `GET /api/session/latest`、`POST /api/session/save` | **扩展**：加按 ID 读取、列表、创建接口；`save` 增加 `sessionId` |
| `app/services/session_service.py` | 文件名为时间戳的会话存取 | **改造**：文件名改为 `sessionId`，新增列表/读取/创建函数 |
| `app/models.py` `SessionPayload` | 无 `sessionId`/`title` 字段 | **扩展**：新增两个字段 |
| `frontend/src/app/App.tsx` 路由 | `/import` `/collect` `/hotlist` | **新增** `/chat` 路由 |

---

## 范围与非目标

**本阶段要做的：**
- 新对话页面（`/chat`），支持多轮对话、消息历史持久化。
- Session 升级为可创建、可列出、可按 ID 切换的实体，工作区数据（采集结果/回答）和对话历史共用同一个 `sessionId`。
- `WorkspaceTopbar` 加一个 Session 切换器，Import/Collect/Hotlist 页面也能切换查看不同 session 的数据。

**本阶段明确不做的：**
- Agent 不会调用采集（collect）、生成（generate）、润色（polish）等现有业务能力——对话节点只调用 LLM 做纯文本对话，没有工具/函数调用。
- 不做"参数确认""执行前二次确认"之类的工具调用安全机制——因为本阶段没有会产生真实副作用的工具。
- 不改动 `/api/agent/chat` 及其两个现有 Graph 的任何行为。

这两点是本阶段和"让 Agent 调用采集工具"之间的边界，后续若要做，应作为独立 Feature，建立在本阶段的多轮对话基础设施之上。

---

## 架构设计

### 整体结构

```
用户进入 /chat 页面
        │
        ▼
ChatPage：左侧 Session 列表 + 右侧消息流 + 输入框
        │  POST /api/agent/conversation { sessionId, message }
        ▼
ConversationGraph（新增，独立于现有两个 Graph）
    State：消息列表（MessagesState 模式）
    单节点 chat_node：把完整历史交给 LLM，取回复，追加进消息列表
    Checkpointer：SQLite 持久化，按 thread_id = sessionId 存取
        │
        ▼
LLM（DeepSeek/GLM，复用现有 OpenAI 兼容客户端）
```

### Session 数据模型

Session 是贯穿对话历史和工作区数据的唯一标识，但两者物理存储分开：

| 内容 | 存储方式 | 由谁管理 |
|---|---|---|
| 工作区数据（主题、采集到的问题、回答、配置） | `output/sessions/<sessionId>.json`（文件名从时间戳改为 sessionId） | `session_service.py` |
| 对话历史（消息列表） | SQLite 文件 `output/agent_checkpoints.sqlite`，按 `thread_id=sessionId` 分区 | LangGraph `Checkpointer` |

`output/sessions/<sessionId>.json` 内容在现有 `SessionPayload` 基础上新增两个字段：

```python
# app/models.py SessionPayload 新增字段
session_id: str = Field(alias="sessionId")
title: str = Field(default="新对话", alias="title")
created_at: str = Field(default="", alias="createdAt")
```

`title` 默认是"新对话"，对话页面发出第一条消息后，后端用消息前 20 字自动回填。

### ConversationGraph

```python
# app/application/agent/state.py 新增
from typing import Annotated
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages

class ConversationState(TypedDict):
    messages: Annotated[list, add_messages]
```

```python
# app/application/agent/nodes/chat.py
from ..state import ConversationState
from ....infrastructure.llm.deepseek_client import DeepSeekAnswerGenerator

_generator = DeepSeekAnswerGenerator()

async def chat_node(state: ConversationState) -> dict:
    """把完整对话历史交给 LLM，返回新的一条助手消息。"""
    reply = await _generator.chat(state["messages"])  # 新增方法，见下
    return {"messages": [{"role": "assistant", "content": reply}]}
```

```python
# app/application/agent/graphs/conversation.py
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from ..state import ConversationState
from ..nodes.chat import chat_node

async def build_conversation_graph(db_path: str):
    graph = StateGraph(ConversationState)
    graph.add_node("chat", chat_node)
    graph.add_edge(START, "chat")
    graph.add_edge("chat", END)

    checkpointer = await AsyncSqliteSaver.from_conn_string(db_path).__aenter__()
    return graph.compile(checkpointer=checkpointer)
```

> 这个图现在只有一个节点。未来若要加工具调用，只需要在 `chat` 节点后加一条条件边（判断 LLM 是否返回 `tool_calls`），回环到一个新的 `execute_tool` 节点——不需要重新设计 State 或重写现有节点。

`DeepSeekAnswerGenerator` 需要新增一个通用的多轮对话方法（区别于已有的 `call_raw` 单轮裸调用）：

```python
# app/infrastructure/llm/deepseek_client.py 新增方法
async def chat(self, messages: list[dict]) -> str:
    """多轮对话调用，messages 是完整历史（含 system/user/assistant）。"""
    client = self.get_client()
    model = get_required_env("DEEPSEEK_MODEL")
    completion = client.chat.completions.create(model=model, messages=messages)
    content = completion.choices[0].message.content
    if isinstance(content, str):
        return content.strip()
    raise ValueError("LLM returned empty chat content")
```

### API 接口

| 接口 | 方法 | 作用 |
|---|---|---|
| `/api/session/new` | POST | 创建新 session，返回 `{ sessionId, title, createdAt }` |
| `/api/session/list` | GET | 列出所有 session（按 `createdAt` 倒序），每项含 `sessionId/title/createdAt` |
| `/api/session/{sessionId}` | GET | 按 ID 读取该 session 的工作区数据 |
| `/api/session/save` | POST | 沿用现有，payload 加 `sessionId`，保存到对应文件而非新建时间戳文件 |
| `/api/agent/conversation` | POST | 新增，payload `{ sessionId, message }`，返回 `{ reply }`，内部调用 `ConversationGraph` |
| `/api/agent/conversation/{sessionId}/history` | GET | 新增，从 Checkpointer 读取该 session 的完整消息历史，返回 `ChatMessage[]`，供前端进入对话页面时首次渲染 |

`/api/session/latest` 保留作为兼容（内部实现改为"返回最近创建的一个 session"，避免破坏任何还在用它的旧路径)。

### 前端设计

**路由**：`App.tsx` 新增 `<Route path="chat" element={<ChatPage />} />`，导航栏加第 4 项"对话"。

**`ChatPage` 布局**：
```
┌──────────────┬───────────────────────────────┐
│ 会话列表       │  消息流（用户/助手气泡，时间倒序滚动） │
│ [+ 新建对话]   │                               │
│ ─────────    │                               │
│ 对话标题 A     │                               │
│ 对话标题 B（选中）│                               │
│ ...          ├───────────────────────────────┤
│              │  [输入框..................][发送] │
└──────────────┴───────────────────────────────┘
```

**新增类型**（`frontend/src/types/workflow.ts`）：
```typescript
export type ChatMessage = { role: "user" | "assistant"; content: string };
export type ChatSession = { sessionId: string; title: string; createdAt: string };
export type ConversationResponse = { reply: string };
```

**新增 API 函数**（`workflow-api.ts`）：
```typescript
export function listSessions() { return apiGet<ChatSession[]>("/api/session/list"); }
export function createSession() { return apiPost<ChatSession>("/api/session/new", {}); }
export function getSession(sessionId: string) { return apiGet(`/api/session/${sessionId}`); }
export function sendConversationMessage(sessionId: string, message: string) {
  return apiPost<ConversationResponse>("/api/agent/conversation", { sessionId, message });
}
```

**Session 切换器位置**：放在 `WorkspaceTopbar`（所有页面顶部可见），下拉选择当前活跃 session；Import/Collect/Hotlist 页面读取数据时改成"读当前活跃 session"而不是隐式的"最新一份"。`ChatPage` 左侧的会话列表点击切换时，同步更新这个全局活跃 session。

**对话页面消息历史从哪来**：进入某个 session 的对话页面时，调用 `GET /api/session/{sessionId}` 拿到的是工作区数据，不含消息历史；消息历史通过上面的 `GET /api/agent/conversation/{sessionId}/history` 单独获取，用于首次渲染消息流。

---

## 错误处理

- LLM 调用失败（网络错误/超时）：`chat_node` 抛出异常，`/api/agent/conversation` 捕获后返回 `{ ok: false, error }`，前端在消息流里显示一条"发送失败，请重试"的系统提示，不写入消息历史。
- Session 不存在（`GET /api/session/{id}` 查无文件）：返回 404，前端提示"会话不存在"并引导回到会话列表。
- SQLite checkpointer 初始化失败（文件锁/权限问题）：启动时记录日志并阻止 `/api/agent/conversation` 路由可用，但不影响现有 `/api/agent/chat`、采集、生成等功能——失败隔离在新功能范围内。

## 测试策略

- 后端：`ConversationGraph` 单元测试（mock LLM，验证消息按顺序追加、checkpointer 能跨调用恢复历史）；`session_service` 新函数测试（创建/列表/按 ID 读取）。
- 前端：`ChatPage` 组件测试（发消息后消息流追加、切换 session 后消息流替换为对应历史）。
- 不需要端到端测试覆盖真实 LLM 调用（按现有项目测试风格，LLM 调用统一 mock）。

## 文件结构

```
app/
├── application/agent/
│   ├── state.py                 # 新增 ConversationState
│   ├── graphs/conversation.py   # 新增
│   └── nodes/chat.py            # 新增
├── api/routes/
│   ├── agent.py                 # 新增 /api/agent/conversation 路由
│   └── session.py               # 扩展 new/list/{id} 路由
├── services/session_service.py  # 改造为按 sessionId 存取 + 列表
└── infrastructure/llm/deepseek_client.py  # 新增 chat() 方法

frontend/src/
├── app/App.tsx                  # 新增 /chat 路由
├── features/chat/
│   ├── chat-page.tsx            # 新增
│   ├── session-list.tsx         # 新增
│   └── message-thread.tsx       # 新增
├── features/workspace/
│   ├── workspace-shell.tsx      # WorkspaceTopbar 加 Session 切换器
│   └── workflow-api.ts          # 新增 session/conversation 相关函数
└── types/workflow.ts            # 新增 ChatMessage/ChatSession 类型
```

## 依赖

- 新增 Python 包：`langgraph-checkpoint-sqlite`（持久化 Checkpointer）
- 无前置 Feature 依赖；复用 `feature-agent-layer` 已经引入的 `langgraph`

## 未来扩展点

- 给 `ConversationGraph` 的 `chat` 节点后加条件边 + `execute_tool` 节点，实现工具调用（采集/生成/润色），是否做、何时做留给后续 Feature 评估。
- 工具调用一旦引入，需要补充"执行前参数确认"机制（在本设计的"非目标"中已说明原因）。
- Session 列表目前用扫描目录实现，若 session 数量变大，可以再引入索引文件或 SQLite 表来加速列表查询。

## 实现顺序

1. 后端：`SessionPayload`/`session_service.py` 改造（按 ID 存取 + 列表 + 创建）。
2. 后端：`ConversationState`/`chat_node`/`ConversationGraph`/`/api/agent/conversation` 路由。
3. 后端：`DeepSeekAnswerGenerator.chat()` 新方法。
4. 前端：`/chat` 路由 + `ChatPage`/`session-list`/`message-thread` 组件。
5. 前端：`WorkspaceTopbar` 加 Session 切换器，Import/Collect/Hotlist 改为读取"当前活跃 session"。
