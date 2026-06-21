# Agent Chat Page — Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增一个独立的对话页面（`/chat`），支持多轮聊天、多会话创建与切换，并让 Import/Collect/Hotlist 页面能跟随同一个"当前活跃 session"读写数据。

**Architecture:** 新页面和组件放在 `frontend/src/features/workspace/` 下（沿用现有 colocate 惯例，前缀 `chat-`），通过 `@tanstack/react-query` 调用 [plan-agent-chat-page-backend.md](plan-agent-chat-page-backend.md) 实现的接口；`activeSessionId` 存在 Zustand store 里，`WorkspaceTopbar` 新增一个 Session 切换器，`use-workspace.ts` 的会话 hydration 逻辑改为跟随 `activeSessionId` 变化重新拉取。

> **与设计文档的偏差说明**：[feature-agent-chat-page.md](../specs/feature-agent-chat-page.md) 的文件结构示意图里把新组件放在 `frontend/src/features/chat/` 这个新目录下。写计划时实际查看代码发现，现有的 `hotlist-analysis-panel.tsx`、`refinement-chat.tsx` 等同类"嵌入式 AI 交互组件"都直接放在 `frontend/src/features/workspace/` 里和页面组件挨在一起，并没有按能力单独开目录。为了和现有代码保持一致，本计划改为把新组件也放进 `features/workspace/`（用 `chat-` 前缀区分），不新开 `features/chat/` 目录。

**Tech Stack:** React 19、TypeScript、`@tanstack/react-query`、Zustand、shadcn/ui（已有 `Button`/`Textarea`/`Select`）、新增 `react-markdown` + `remark-gfm`。

**前置依赖：** [plan-agent-chat-page-backend.md](plan-agent-chat-page-backend.md) 必须先完成并可用，本计划所有接口调用都假设后端路由已存在。

## Global Constraints

- 前端目前没有安装任何单元测试框架（`package.json` 里没有 vitest/jest/@testing-library），项目现状的验证手段是 `bun run typecheck`（类型检查）+ 手动在 dev server 里验证（CLAUDE.md 明确写着"修改 .ts/.tsx 后必须通过"typecheck）。本计划遵循这个现状，每个代码任务以 `bun run typecheck` 收尾，不引入新的测试框架；最终用 Task 9 做手动端到端验证。
- 不渲染原始 HTML（不装 `rehype-raw`）；不实现 Mermaid 自定义渲染组件——这两项在调研阶段已经明确排除出本次范围（见 [feature-agent-chat-page.md](../specs/feature-agent-chat-page.md) 和与用户的确认）。
- 不修改 `refinement-chat.tsx`、`hotlist-analysis-panel.tsx` 的任何现有行为。
- 所有新增 API 调用必须走 `frontend/src/lib/api.ts` 现有的 `apiGet`/`apiPost`，不引入新的 HTTP 客户端。

---

### Task 1: 安装 `react-markdown` 和 `remark-gfm`

**Files:**
- Modify: `frontend/package.json`

- [ ] **Step 1: 安装依赖**

```bash
cd frontend && bun add react-markdown remark-gfm
```

Expected: `package.json` 的 `dependencies` 里新增 `"react-markdown"` 和 `"remark-gfm"` 两行。

- [ ] **Step 2: 验证类型检查仍然通过**

```bash
cd frontend && bun run typecheck
```

Expected: 无报错退出。

- [ ] **Step 3: Commit**

```bash
git add frontend/package.json frontend/bun.lock
git commit -m "chore: add react-markdown and remark-gfm for chat message rendering"
```

---

### Task 2: 新增 TypeScript 类型

**Files:**
- Modify: `frontend/src/types/workflow.ts`

**Interfaces:**
- Produces: `SessionSummary`、`ChatMessage`、`ConversationPayload`、`ConversationResponse`、`ConversationHistoryResponse` 类型；`SessionResponse.session` 和 `SaveSessionPayload` 新增 `sessionId`/`title`/`createdAt` 字段。Task 3（API 函数）、Task 5（store/hook）、Task 6（组件）都依赖这些类型。

- [ ] **Step 1: 修改 `SessionResponse` 类型**

把现有的：

```typescript
export type SessionResponse = {
  session: {
    platform?: Platform;
    topics?: Topic[];
    answerStyle?: string;
    systemPrompt?: string;
    generationPrompt?: string;
    maxPushCount?: number;
    items?: QuestionItem[];
  } | null;
};
```

改成：

```typescript
export type SessionResponse = {
  session: {
    sessionId?: string;
    title?: string;
    createdAt?: string;
    platform?: Platform;
    topics?: Topic[];
    answerStyle?: string;
    systemPrompt?: string;
    generationPrompt?: string;
    maxPushCount?: number;
    items?: QuestionItem[];
  } | null;
};
```

- [ ] **Step 2: 修改 `SaveSessionPayload` 类型**

把现有的：

```typescript
export type SaveSessionPayload = {
  platform: Platform;
  topics: Topic[];
  items: QuestionItem[];
  answerStyle: string;
  systemPrompt: string;
  generationPrompt: string;
  maxPushCount: number;
  savedAt: string;
};
```

改成：

```typescript
export type SaveSessionPayload = {
  sessionId?: string;
  platform: Platform;
  topics: Topic[];
  items: QuestionItem[];
  answerStyle: string;
  systemPrompt: string;
  generationPrompt: string;
  maxPushCount: number;
  savedAt: string;
};
```

- [ ] **Step 3: 在文件末尾追加对话相关类型**

```typescript
export type SessionSummary = {
  sessionId: string;
  title: string;
  createdAt: string;
};

export type ChatMessage = {
  role: "user" | "assistant";
  content: string;
};

export type ConversationPayload = {
  sessionId: string;
  message: string;
};

export type ConversationResponse = {
  reply: string;
};

export type ConversationHistoryResponse = {
  messages: ChatMessage[];
};
```

- [ ] **Step 4: 运行类型检查**

```bash
cd frontend && bun run typecheck
```

Expected: 无报错（这一步只新增类型，还没有代码引用它们，理应直接通过）。

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types/workflow.ts
git commit -m "feat: add SessionSummary/ChatMessage/Conversation* types"
```

---

### Task 3: 新增 Session 与对话相关 API 函数

**Files:**
- Modify: `frontend/src/features/workspace/workflow-api.ts`

**Interfaces:**
- Consumes: `SessionSummary`、`SessionResponse`、`ConversationPayload`、`ConversationResponse`、`ConversationHistoryResponse`（Task 2）
- Produces: `listSessions()`、`createSession()`、`getSession(sessionId)`、`sendConversationMessage(payload)`、`getConversationHistory(sessionId)`。Task 5（`use-workspace.ts`）、Task 6（chat 组件）、Task 8（Session 切换器）都依赖这些函数。

- [ ] **Step 1: 修改 import 并追加函数**

把文件顶部的 import 列表：

```typescript
import { apiGet, apiPost } from "@/lib/api";
import type {
  AgentChatPayload,
  AgentChatResponse,
  CollectPayload,
  CollectResponse,
  ConfigResponse,
  GenerateAllPayload,
  GenerateAllResponse,
  GenerateOnePayload,
  GenerateOneResponse,
  HotlistResponse,
  ParseQuestionUrlPayload,
  ParseQuestionUrlResponse,
  PolishOnePayload,
  PolishOneResponse,
  SaveSessionPayload,
  SessionResponse,
} from "@/types/workflow";
```

改成：

```typescript
import { apiGet, apiPost } from "@/lib/api";
import type {
  AgentChatPayload,
  AgentChatResponse,
  CollectPayload,
  CollectResponse,
  ConfigResponse,
  ConversationHistoryResponse,
  ConversationPayload,
  ConversationResponse,
  GenerateAllPayload,
  GenerateAllResponse,
  GenerateOnePayload,
  GenerateOneResponse,
  HotlistResponse,
  ParseQuestionUrlPayload,
  ParseQuestionUrlResponse,
  PolishOnePayload,
  PolishOneResponse,
  SaveSessionPayload,
  SessionResponse,
  SessionSummary,
} from "@/types/workflow";
```

然后在文件末尾（`agentChat` 函数之后）追加：

```typescript
export function listSessions() {
  return apiGet<SessionSummary[]>("/api/session/list");
}

export function createSession() {
  return apiPost<SessionSummary>("/api/session/new", {});
}

export function getSession(sessionId: string) {
  return apiGet<SessionResponse>(`/api/session/${sessionId}`);
}

export function sendConversationMessage(payload: ConversationPayload) {
  return apiPost<ConversationResponse>("/api/agent/conversation", payload);
}

export function getConversationHistory(sessionId: string) {
  return apiGet<ConversationHistoryResponse>(`/api/agent/conversation/${sessionId}/history`);
}
```

- [ ] **Step 2: 运行类型检查**

```bash
cd frontend && bun run typecheck
```

Expected: 无报错。

- [ ] **Step 3: Commit**

```bash
git add frontend/src/features/workspace/workflow-api.ts
git commit -m "feat: add session and conversation API functions"
```

---

### Task 4: Store 新增 `activeSessionId`

**Files:**
- Modify: `frontend/src/store/workspace-store.ts`

**Interfaces:**
- Produces: `useWorkspaceStore` 新增 `activeSessionId: string | null` 和 `setActiveSessionId: (id: string | null) => void`。Task 5、Task 6、Task 8 都依赖它。

- [ ] **Step 1: 在 `WorkspaceState` 类型里新增字段**

把：

```typescript
type WorkspaceState = {
  selectedPlatform: Platform;
  selectedSource: CollectSource;
  selectedContentMode: ContentMode;
```

改成：

```typescript
type WorkspaceState = {
  activeSessionId: string | null;
  selectedPlatform: Platform;
  selectedSource: CollectSource;
  selectedContentMode: ContentMode;
```

并在该类型定义末尾（`setTopicDraft: (draft: TopicDraft) => void;` 这一行后面）新增：

```typescript
  setActiveSessionId: (sessionId: string | null) => void;
```

- [ ] **Step 2: 在 store 实现里新增初始值和 setter**

把：

```typescript
export const useWorkspaceStore = create<WorkspaceState>((set) => ({
  selectedPlatform: DEFAULT_PLATFORM,
```

改成：

```typescript
export const useWorkspaceStore = create<WorkspaceState>((set) => ({
  activeSessionId: null,
  selectedPlatform: DEFAULT_PLATFORM,
```

并在该对象定义末尾（`setTopicDraft: (draft) => set({ topicDraft: draft }),` 这一行后面）新增：

```typescript
  setActiveSessionId: (sessionId) => set({ activeSessionId: sessionId }),
```

- [ ] **Step 3: 运行类型检查**

```bash
cd frontend && bun run typecheck
```

Expected: 无报错。

- [ ] **Step 4: Commit**

```bash
git add frontend/src/store/workspace-store.ts
git commit -m "feat: add activeSessionId to workspace store"
```

---

### Task 5: `use-workspace.ts` 跟随 `activeSessionId` 重新拉取并 hydrate

**Files:**
- Modify: `frontend/src/features/workspace/use-workspace.ts`

**Interfaces:**
- Consumes: `getSession`（Task 3）、`activeSessionId`/`setActiveSessionId`（Task 4）
- Produces: `sessionQuery` 的 `queryKey` 包含 `activeSessionId`；切换 `activeSessionId` 会触发重新 hydrate；首次用"最新 session"hydrate 后自动把该 session 的 `sessionId` 写回 store；`saveSession` 的 payload 携带 `sessionId`。

- [ ] **Step 1: 修改 import**

把：

```typescript
import { defaultPlatform } from "./defaults";
import {
  collectWorkflow,
  generateAllAnswers,
  generateOneAnswer,
  getLatestSession,
  getWorkspaceConfig,
  parseQuestionUrl,
  polishOneAnswer,
  saveWorkspaceSession,
} from "./workflow-api";
```

改成：

```typescript
import { defaultPlatform } from "./defaults";
import {
  collectWorkflow,
  generateAllAnswers,
  generateOneAnswer,
  getLatestSession,
  getSession,
  getWorkspaceConfig,
  parseQuestionUrl,
  polishOneAnswer,
  saveWorkspaceSession,
} from "./workflow-api";
```

- [ ] **Step 2: 把 `hasHydratedSession` 的 ref 改成按 key 比较**

把：

```typescript
export function useWorkspace() {
  const hasHydratedConfig = useRef(false);
  const hasHydratedSession = useRef(false);
```

改成：

```typescript
export function useWorkspace() {
  const hasHydratedConfig = useRef(false);
  const hydratedSessionKey = useRef<string | null>(null);
```

- [ ] **Step 3: 从 store 取出 `activeSessionId`/`setActiveSessionId`**

把：

```typescript
    setIsCollecting,
    setIsGeneratingAll,
    setSaveState,
    setStatusMessage,
  } = useWorkspaceStore();
```

改成：

```typescript
    setIsCollecting,
    setIsGeneratingAll,
    setSaveState,
    setStatusMessage,
    activeSessionId,
    setActiveSessionId,
  } = useWorkspaceStore();
```

- [ ] **Step 4: 让 `sessionQuery` 跟随 `activeSessionId`**

把：

```typescript
  const sessionQuery = useQuery({
    queryKey: ["workspace-session"],
    queryFn: getLatestSession,
  });
```

改成：

```typescript
  const sessionQuery = useQuery({
    queryKey: ["workspace-session", activeSessionId],
    queryFn: () => (activeSessionId ? getSession(activeSessionId) : getLatestSession()),
  });
```

- [ ] **Step 5: 修改 hydration effect，支持按 session 切换重新执行**

把：

```typescript
  useEffect(() => {
    const session = sessionQuery.data?.session;
    if (!session || hasHydratedSession.current) {
      return;
    }
    hasHydratedSession.current = true;
    const sessionPlatform = session.platform ?? selectedPlatform;
    const sessionTopics = session.topics ?? [];
    const sessionSelectedTopic = sessionTopics[0] ?? null;
    setSelectedPlatform(sessionPlatform);
    if (session.maxPushCount) {
      setMaxPushCount(session.maxPushCount);
    }
    if (session.generationPrompt) {
      setGenerationPrompt(session.generationPrompt);
    }
    if (sessionTopics.length) {
      setPresetTopics(sessionTopics);
      setSelectedTopic(sessionSelectedTopic);
      setAnswerStyle(getTopicAnswerStyle(sessionSelectedTopic, session.answerStyle ?? answerStyle));
      setSystemPrompt(getTopicSystemPrompt(sessionSelectedTopic, session.systemPrompt ?? systemPrompt));
    } else {
      if (session.answerStyle) {
        setAnswerStyle(session.answerStyle);
      }
      if (session.systemPrompt) {
        setSystemPrompt(session.systemPrompt);
      }
    }
    if (session.items?.length) {
      setQuestions(session.items.map((item) => withPlatform(item, sessionPlatform)));
      setStatusMessage("已恢复最近一次保存的会话。");
    }
  }, [
    sessionQuery.data,
    selectedPlatform,
    setAnswerStyle,
    setMaxPushCount,
    setPresetTopics,
    setQuestions,
    setSelectedPlatform,
    setSelectedTopic,
    setStatusMessage,
    setSystemPrompt,
    setGenerationPrompt,
  ]);
```

改成：

```typescript
  useEffect(() => {
    const session = sessionQuery.data?.session;
    const sessionKey = activeSessionId ?? "__latest__";
    if (!session || hydratedSessionKey.current === sessionKey) {
      return;
    }
    hydratedSessionKey.current = sessionKey;
    if (!activeSessionId && session.sessionId) {
      setActiveSessionId(session.sessionId);
    }
    const sessionPlatform = session.platform ?? selectedPlatform;
    const sessionTopics = session.topics ?? [];
    const sessionSelectedTopic = sessionTopics[0] ?? null;
    setSelectedPlatform(sessionPlatform);
    if (session.maxPushCount) {
      setMaxPushCount(session.maxPushCount);
    }
    if (session.generationPrompt) {
      setGenerationPrompt(session.generationPrompt);
    }
    if (sessionTopics.length) {
      setPresetTopics(sessionTopics);
      setSelectedTopic(sessionSelectedTopic);
      setAnswerStyle(getTopicAnswerStyle(sessionSelectedTopic, session.answerStyle ?? answerStyle));
      setSystemPrompt(getTopicSystemPrompt(sessionSelectedTopic, session.systemPrompt ?? systemPrompt));
    } else {
      if (session.answerStyle) {
        setAnswerStyle(session.answerStyle);
      }
      if (session.systemPrompt) {
        setSystemPrompt(session.systemPrompt);
      }
    }
    setQuestions(session.items?.length ? session.items.map((item) => withPlatform(item, sessionPlatform)) : []);
    setStatusMessage(session.items?.length ? "已恢复所选会话。" : "已切换到新的空会话。");
  }, [
    sessionQuery.data,
    activeSessionId,
    selectedPlatform,
    setActiveSessionId,
    setAnswerStyle,
    setMaxPushCount,
    setPresetTopics,
    setQuestions,
    setSelectedPlatform,
    setSelectedTopic,
    setStatusMessage,
    setSystemPrompt,
    setGenerationPrompt,
  ]);
```

> 行为变化说明：原来 `setQuestions`/`setStatusMessage` 只在 `session.items?.length` 为真时才执行，切换到一个"还没有采集任何问题"的新 session 时旧问题列表会一直留着不清空。现在改成"始终设置"——这是必要的修正，否则切换会话时 Collect 页面会显示上一个会话遗留的问题列表，和"切换会话查看对应数据"的设计目标矛盾。

- [ ] **Step 6: `saveSession` 携带 `sessionId`**

把 `saveMutation` 里的：

```typescript
      const payload: SaveSessionPayload = {
        platform: selectedPlatform,
        topics: presetTopics.map((topic) => ({
```

改成：

```typescript
      const payload: SaveSessionPayload = {
        sessionId: activeSessionId ?? undefined,
        platform: selectedPlatform,
        topics: presetTopics.map((topic) => ({
```

- [ ] **Step 7: 运行类型检查**

```bash
cd frontend && bun run typecheck
```

Expected: 无报错。

- [ ] **Step 8: Commit**

```bash
git add frontend/src/features/workspace/use-workspace.ts
git commit -m "feat: hydrate workspace from activeSessionId and persist it on save"
```

---

### Task 6: 新增对话页面组件

**Files:**
- Create: `frontend/src/features/workspace/chat-message-input.tsx`
- Create: `frontend/src/features/workspace/chat-message-thread.tsx`
- Create: `frontend/src/features/workspace/chat-session-list.tsx`
- Create: `frontend/src/features/workspace/chat-page.tsx`

**Interfaces:**
- Consumes: `listSessions`/`createSession`/`getConversationHistory`/`sendConversationMessage`（Task 3）、`activeSessionId`/`setActiveSessionId`（Task 4）、`ChatMessage`/`SessionSummary`（Task 2）
- Produces: `ChatPage` 组件，Task 7 的路由依赖它。

- [ ] **Step 1: 创建 `chat-message-input.tsx`**

```tsx
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

type Props = {
  disabled: boolean;
  onSend: (message: string) => void;
};

export function ChatMessageInput({ disabled, onSend }: Props) {
  const [value, setValue] = useState("");

  function handleSend() {
    const trimmed = value.trim();
    if (!trimmed || disabled) {
      return;
    }
    onSend(trimmed);
    setValue("");
  }

  return (
    <div className="flex items-end gap-2 border-t p-3">
      <Textarea
        className="min-h-[44px] flex-1 resize-none"
        placeholder="输入消息，Enter 发送，Shift+Enter 换行..."
        value={value}
        disabled={disabled}
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            handleSend();
          }
        }}
      />
      <Button disabled={!value.trim() || disabled} onClick={handleSend}>
        发送
      </Button>
    </div>
  );
}
```

- [ ] **Step 2: 创建 `chat-message-thread.tsx`**

```tsx
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { cn } from "@/lib/utils";
import type { ChatMessage } from "@/types/workflow";

type Props = {
  messages: ChatMessage[];
  isLoading: boolean;
};

export function ChatMessageThread({ messages, isLoading }: Props) {
  return (
    <div className="flex-1 min-h-0 space-y-3 overflow-y-auto p-4">
      {isLoading && <p className="text-sm text-muted-foreground">加载历史消息中...</p>}
      {!isLoading && messages.length === 0 && (
        <p className="text-sm text-muted-foreground">还没有消息，发一句话开始对话吧。</p>
      )}
      {messages.map((message, index) => (
        <div
          key={index}
          className={cn(
            "max-w-[75%] rounded-lg px-3 py-2 text-sm leading-relaxed",
            message.role === "user" ? "ml-auto bg-primary text-primary-foreground" : "bg-muted text-foreground",
          )}
        >
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 3: 创建 `chat-session-list.tsx`**

```tsx
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { SessionSummary } from "@/types/workflow";

type Props = {
  sessions: SessionSummary[];
  activeSessionId: string | null;
  onSelect: (sessionId: string) => void;
  onCreate: () => void;
};

export function ChatSessionList({ sessions, activeSessionId, onSelect, onCreate }: Props) {
  return (
    <div className="flex w-64 shrink-0 flex-col rounded-lg border bg-white">
      <div className="p-3">
        <Button className="w-full" onClick={onCreate}>
          + 新建对话
        </Button>
      </div>
      <div className="flex-1 min-h-0 space-y-1 overflow-y-auto px-2 pb-2">
        {sessions.map((session) => (
          <button
            key={session.sessionId}
            type="button"
            className={cn(
              "w-full rounded-md px-2 py-2 text-left text-sm transition-colors hover:bg-muted",
              session.sessionId === activeSessionId && "bg-muted font-medium",
            )}
            onClick={() => onSelect(session.sessionId)}
          >
            {session.title}
          </button>
        ))}
        {sessions.length === 0 && (
          <p className="px-2 py-2 text-xs text-muted-foreground">还没有会话，点上面的按钮新建一个。</p>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: 创建 `chat-page.tsx`**

```tsx
import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { useWorkspaceStore } from "@/store/workspace-store";
import type { ChatMessage } from "@/types/workflow";

import { ChatMessageInput } from "./chat-message-input";
import { ChatMessageThread } from "./chat-message-thread";
import { ChatSessionList } from "./chat-session-list";
import { createSession, getConversationHistory, listSessions, sendConversationMessage } from "./workflow-api";

const SESSION_LIST_QUERY_KEY = ["chat-session-list"];

export function ChatPage() {
  const activeSessionId = useWorkspaceStore((s) => s.activeSessionId);
  const setActiveSessionId = useWorkspaceStore((s) => s.setActiveSessionId);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isSending, setIsSending] = useState(false);
  const queryClient = useQueryClient();

  const sessionListQuery = useQuery({
    queryKey: SESSION_LIST_QUERY_KEY,
    queryFn: listSessions,
  });

  const historyQuery = useQuery({
    queryKey: ["chat-history", activeSessionId],
    queryFn: () => getConversationHistory(activeSessionId as string),
    enabled: Boolean(activeSessionId),
  });

  useEffect(() => {
    setMessages(historyQuery.data?.messages ?? []);
  }, [historyQuery.data]);

  async function handleCreateSession() {
    const session = await createSession();
    setActiveSessionId(session.sessionId);
    setMessages([]);
    queryClient.invalidateQueries({ queryKey: SESSION_LIST_QUERY_KEY });
  }

  async function handleSend(message: string) {
    if (!activeSessionId) {
      return;
    }
    setMessages((prev) => [...prev, { role: "user", content: message }]);
    setIsSending(true);
    try {
      const res = await sendConversationMessage({ sessionId: activeSessionId, message });
      setMessages((prev) => [...prev, { role: "assistant", content: res.reply }]);
    } catch {
      setMessages((prev) => [...prev, { role: "assistant", content: "发送失败，请重试" }]);
    } finally {
      setIsSending(false);
      queryClient.invalidateQueries({ queryKey: SESSION_LIST_QUERY_KEY });
    }
  }

  return (
    <section className="flex min-h-0 flex-1 gap-4">
      <ChatSessionList
        sessions={sessionListQuery.data ?? []}
        activeSessionId={activeSessionId}
        onSelect={setActiveSessionId}
        onCreate={handleCreateSession}
      />
      <div className="flex min-h-0 flex-1 flex-col rounded-lg border bg-white">
        <ChatMessageThread messages={messages} isLoading={historyQuery.isLoading} />
        <ChatMessageInput disabled={!activeSessionId || isSending} onSend={handleSend} />
      </div>
    </section>
  );
}
```

- [ ] **Step 5: 运行类型检查**

```bash
cd frontend && bun run typecheck
```

Expected: 无报错。

- [ ] **Step 6: Commit**

```bash
git add frontend/src/features/workspace/chat-message-input.tsx \
        frontend/src/features/workspace/chat-message-thread.tsx \
        frontend/src/features/workspace/chat-session-list.tsx \
        frontend/src/features/workspace/chat-page.tsx
git commit -m "feat: add ChatPage with session list, message thread and input"
```

---

### Task 7: 新增 `/chat` 路由和导航项

**Files:**
- Modify: `frontend/src/app/App.tsx`
- Modify: `frontend/src/features/workspace/workspace-shell.tsx`

**Interfaces:**
- Consumes: `ChatPage`（Task 6）

- [ ] **Step 1: 修改 `App.tsx`**

把：

```tsx
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { CollectPage, HotlistPage, ImportPage, WorkspaceLayout } from "@/features/workspace/workspace-shell";

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<WorkspaceLayout />}>
          <Route index element={<Navigate to="/import" replace />} />
          <Route path="import" element={<ImportPage />} />
          <Route path="collect" element={<CollectPage />} />
          <Route path="hotlist" element={<HotlistPage />} />
        </Route>
        <Route path="*" element={<Navigate to="/import" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
```

改成：

```tsx
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { ChatPage } from "@/features/workspace/chat-page";
import { CollectPage, HotlistPage, ImportPage, WorkspaceLayout } from "@/features/workspace/workspace-shell";

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<WorkspaceLayout />}>
          <Route index element={<Navigate to="/import" replace />} />
          <Route path="import" element={<ImportPage />} />
          <Route path="collect" element={<CollectPage />} />
          <Route path="hotlist" element={<HotlistPage />} />
          <Route path="chat" element={<ChatPage />} />
        </Route>
        <Route path="*" element={<Navigate to="/import" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
```

- [ ] **Step 2: 修改 `workspace-shell.tsx` 的 `EntryMode` 和导航项**

把：

```typescript
type EntryMode = "import" | "collect" | "hotlist";
```

改成：

```typescript
type EntryMode = "import" | "collect" | "hotlist" | "chat";
```

把：

```typescript
const topNavItems: Array<{ id: EntryMode; label: string }> = [
  { id: "import", label: "URL 导入回答" },
  { id: "collect", label: "主题采集" },
  { id: "hotlist", label: "知乎热榜" },
];
```

改成：

```typescript
const topNavItems: Array<{ id: EntryMode; label: string }> = [
  { id: "import", label: "URL 导入回答" },
  { id: "collect", label: "主题采集" },
  { id: "hotlist", label: "知乎热榜" },
  { id: "chat", label: "对话" },
];
```

- [ ] **Step 3: 运行类型检查**

```bash
cd frontend && bun run typecheck
```

Expected: 无报错。

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/App.tsx frontend/src/features/workspace/workspace-shell.tsx
git commit -m "feat: add /chat route and nav item"
```

---

### Task 8: WorkspaceTopbar 新增 Session 切换器

**Files:**
- Modify: `frontend/src/features/workspace/workspace-shell.tsx`

**Interfaces:**
- Consumes: `listSessions`（Task 3）、`activeSessionId`/`setActiveSessionId`（Task 4）

- [ ] **Step 1: 修改 `workflow-api` 的 import**

把：

```typescript
import { getHotlist } from "./workflow-api";
```

改成：

```typescript
import { getHotlist, listSessions } from "./workflow-api";
```

- [ ] **Step 2: 在 `WorkspaceTopbar` 之前新增 `SessionSwitcher` 组件**

在 `function WorkspaceTopbar() {` 这一行之前插入：

```tsx
function SessionSwitcher() {
  const activeSessionId = useWorkspaceStore((s) => s.activeSessionId);
  const setActiveSessionId = useWorkspaceStore((s) => s.setActiveSessionId);
  const { data: sessions } = useQuery({
    queryKey: ["chat-session-list"],
    queryFn: listSessions,
  });

  if (!sessions || sessions.length === 0) {
    return null;
  }

  return (
    <Select value={activeSessionId ?? undefined} onValueChange={setActiveSessionId}>
      <SelectTrigger className="w-44">
        <SelectValue placeholder="选择会话" />
      </SelectTrigger>
      <SelectContent>
        {sessions.map((session) => (
          <SelectItem key={session.sessionId} value={session.sessionId}>
            {session.title}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

```

- [ ] **Step 3: 在 `WorkspaceTopbar` 里渲染它**

把：

```tsx
        <Separator orientation="vertical" className="h-4" />

        <NavigationMenu>
```

改成：

```tsx
        <Separator orientation="vertical" className="h-4" />

        <SessionSwitcher />

        <NavigationMenu>
```

- [ ] **Step 4: 运行类型检查**

```bash
cd frontend && bun run typecheck
```

Expected: 无报错。

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/workspace/workspace-shell.tsx
git commit -m "feat: add session switcher to WorkspaceTopbar"
```

---

### Task 9: 端到端手动验证

**Files:** 无代码改动，仅验证。前置条件：[plan-agent-chat-page-backend.md](plan-agent-chat-page-backend.md) 已完成，后端服务正在运行。

- [ ] **Step 1: 启动前端 dev server**

```bash
cd frontend && bun run dev
```

Expected: 输出本地访问地址（通常 `http://127.0.0.1:5173`），无报错。

- [ ] **Step 2: 打开对话页面**

浏览器访问 `http://127.0.0.1:5173/chat`。

Expected: 顶部导航出现"对话"项且高亮；页面左侧是空的会话列表，提示"还没有会话"；右侧消息区提示"还没有消息"。

- [ ] **Step 3: 新建对话并发送消息**

点击"+ 新建对话"，在输入框输入"帮我想三个关于远程办公的选题方向"，按 Enter。

Expected: 消息区先出现一条蓝色用户气泡，随后出现一条灰色助手气泡，内容是模型给出的具体建议（不是报错文案）。

- [ ] **Step 4: 验证多轮记忆**

接着输入"把第二个方向展开讲讲"并发送。

Expected: 助手回复明显围绕"第二个方向"，证明前端正确传递了 `sessionId` 并让后端带上了历史上下文。

- [ ] **Step 5: 刷新页面验证历史恢复**

刷新浏览器页面，重新进入 `/chat`，点击左侧刚才创建的那个会话。

Expected: 消息区恢复出刚才的完整对话（2 轮用户/助手消息），不是空的。

- [ ] **Step 6: 验证顶部 Session 切换器**

切到 `/collect` 页面，查看顶部导航栏，应该能看到一个显示当前会话标题的下拉框。

Expected: 下拉框存在且可以选择刚才创建的会话；选择后页面左侧的"当前主题"区域应该刷新（具体表现为问题列表清空或变化，因为这个对话 session 还没有采集过问题）。

- [ ] **Step 7: 验证现有功能未受影响**

在 `/import` 页面正常粘贴一个知乎问题链接导入，确认导入功能仍然正常工作；检查浏览器开发者工具网络面板，确认没有出现意外的 404/500 请求。

Expected: 导入功能照常工作，没有新增的报错请求。

- [ ] **Step 8: 停止服务**

```bash
# Ctrl+C 终止 bun run dev 进程
```

---

## 完成标准

- `cd frontend && bun run typecheck` 全程保持通过。
- Task 9 的 8 个步骤全部按预期表现。
- `git log` 里能看到 Task 1-8 每个任务对应的独立 commit。
