# Plan: Answer Refinement Chat 实施方案

## 设计原则

| 原则 | 体现 |
|------|------|
| 单一职责 | `RefinementChat` 只管输入交互；状态更新只通过 `workspace-store`；API 调用只在 `workflow-api.ts` |
| 开闭原则 | `AnswerPanel` 只做扩展（新增子组件），不修改现有结构 |
| 低耦合 | `RefinementChat` 不感知 `MarkdownEditor`；两者只通过 store 间接同步 |
| 单向数据流 | 用户输入 → API 调用 → 更新 store → 编辑区自动同步 |

---

## 前置依赖

`plan-agent-layer` 全部完成后方可实施本 Feature。

---

## 数据流

```
用户输入指令
    ↓
RefinementChat.handleSend()
    ↓
workflow-api.agentChat(payload)   ← 纯函数，无副作用
    ↓
POST /api/agent/chat              ← Agent Layer（RefinementGraph）
    ↓
response.answerUpdated === true?
    ├── YES → useWorkspaceStore.updateAnswer(questionId, updatedAnswer)
    │              ↓
    │         MarkdownEditor 监听 store，自动重新渲染
    └── NO  → 只显示 reply 文本（提示类回复）
```

---

## 前端组件设计

### 组件树

```
AnswerPanel（现有，只扩展）
├── QuestionBrief（现有，不改）
├── MarkdownEditor（现有，不改）
└── RefinementChat（新增）        ← 本 Feature 的全部新增代码
      ├── RefinementChatHeader   ← 折叠/展开控制
      └── RefinementChatInput    ← 输入框 + 发送按钮 + 上条回复
```

### RefinementChat 局部状态

```typescript
// 组件内 useState，不写入全局 store
// 原则：只有需要跨组件共享的数据才进 store，UI 交互状态保持局部

type RefinementLocalState = {
  isOpen: boolean;      // 面板展开/折叠
  input: string;        // 输入框内容
  isLoading: boolean;   // 等待 API 响应
  lastReply: string | null;  // 上一条 AI 回复（仅展示用）
};
```

### 组件实现

```typescript
// frontend/src/features/workspace/refinement-chat.tsx

import { useState } from "react";
import { useWorkspaceStore } from "@/store/workspace-store";
import { agentChat } from "./workflow-api";
import type { QuestionItem } from "@/types/workflow";

type Props = {
  sessionId: string;
  question: QuestionItem;
};

export function RefinementChat({ sessionId, question }: Props) {
  const [isOpen, setIsOpen] = useState(false);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [lastReply, setLastReply] = useState<string | null>(null);

  // 只从 store 取 updateAnswer，不读取其他字段（低耦合）
  const updateAnswer = useWorkspaceStore((s) => s.updateAnswer);

  async function handleSend() {
    const trimmed = input.trim();
    if (!trimmed || isLoading) return;

    setIsLoading(true);
    setInput("");

    try {
      const res = await agentChat({
        sessionId,
        questionId: question.id,
        message: trimmed,
      });

      setLastReply(res.reply);

      if (res.answerUpdated && res.updatedAnswer) {
        // 更新 store → MarkdownEditor 自动同步，无需直接通信
        updateAnswer(question.id, res.updatedAnswer);
      }
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <div className="border-t">
      {/* Header：折叠控制 */}
      <button
        className="w-full flex items-center gap-2 px-3 py-2 text-sm text-muted-foreground hover:bg-muted/50"
        onClick={() => setIsOpen((v) => !v)}
      >
        <span>{isOpen ? "▼" : "▶"}</span>
        <span>AI 精修</span>
      </button>

      {/* Body：展开后显示 */}
      {isOpen && (
        <div className="px-3 pb-3 space-y-2">
          {lastReply && (
            <p className="text-xs text-muted-foreground">{lastReply}</p>
          )}
          <div className="flex gap-2">
            <input
              className="flex-1 text-sm border rounded px-2 py-1"
              placeholder="输入指令，如：第二段改短一些…"
              value={input}
              disabled={isLoading}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSend()}
            />
            <button
              className="text-sm px-3 py-1 bg-primary text-primary-foreground rounded disabled:opacity-50"
              disabled={!input.trim() || isLoading}
              onClick={handleSend}
            >
              {isLoading ? "…" : "发送"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
```

### AnswerPanel 修改方式

只在底部增加 `<RefinementChat />`，**不改动任何现有代码**：

```typescript
// workspace-shell.tsx 中 AnswerPanel 的 return 末尾新增

<RefinementChat
  sessionId={sessionId}        // 从上层 props 传入
  question={selectedQuestion}  // 当前选中问题
/>
```

---

## 前端类型定义

```typescript
// frontend/src/types/workflow.ts 追加

export type AgentChatPayload = {
  sessionId: string;
  questionId?: string;
  message: string;
};

export type AgentChatResponse = {
  reply: string;
  answerUpdated: boolean;
  updatedAnswer?: string;
  operationSummary: string;
};
```

```typescript
// frontend/src/features/workspace/workflow-api.ts 追加

export function agentChat(payload: AgentChatPayload) {
  return apiPost<AgentChatResponse>("/api/agent/chat", payload);
}
```

---

## workspace-store 新增方法

`workspace-store` 已有 items 数组，需新增 `updateAnswer` 方法（若尚未存在）：

```typescript
// frontend/src/store/workspace-store.ts 新增 action

updateAnswer: (questionId: string, answer: string) => void;

// 实现（Zustand immer 风格）：
updateAnswer: (questionId, answer) =>
  set((state) => ({
    items: state.items.map((item) =>
      item.id === questionId ? { ...item, answer } : item
    ),
  })),
```

**不可变原则**：使用 `map` 返回新数组，不直接修改 `item.answer`。

---

## 实施阶段

### Phase 1：类型与 API 函数
- [ ] `types/workflow.ts` 追加 `AgentChatPayload`、`AgentChatResponse`
- [ ] `workflow-api.ts` 追加 `agentChat()`
- [ ] 确认 `workspace-store` 已有 `updateAnswer` action（无则新增）

### Phase 2：组件实现
- [ ] 实现 `RefinementChat` 组件
- [ ] 单组件开发调试（Storybook 或临时页面）

### Phase 3：集成
- [ ] 将 `RefinementChat` 嵌入 `AnswerPanel`
- [ ] 确认 `MarkdownEditor` 能响应 store 变化自动更新

### Phase 4：测试
- [ ] `RefinementChat` 单元测试（Mock `agentChat`，验证 store 更新）
- [ ] 集成测试：输入指令 → API 调用 → 编辑区更新的完整链路

---

## 测试策略

```typescript
// 单元测试：Mock agentChat，验证 store 更新
vi.mock("./workflow-api", () => ({
  agentChat: vi.fn().mockResolvedValue({
    reply: "已完成修改",
    answerUpdated: true,
    updatedAnswer: "新的回答内容",
    operationSummary: "修改：第二段",
  }),
}));

test("发送指令后更新编辑区内容", async () => {
  render(<RefinementChat sessionId="s1" question={mockQuestion} />);
  // 展开面板
  fireEvent.click(screen.getByText("AI 精修"));
  // 输入指令
  fireEvent.change(screen.getByPlaceholderText(/输入指令/), {
    target: { value: "第二段改短一些" },
  });
  fireEvent.click(screen.getByText("发送"));
  // 等待 store 更新
  await waitFor(() => {
    expect(useWorkspaceStore.getState().items[0].answer).toBe("新的回答内容");
  });
});
```

---

## 与现有功能的共存关系

```
AnswerPanel
├── 「重新生成」按钮  → POST /api/workflow/generate-one  （完整重写，保留）
├── 「润色」按钮      → POST /api/workflow/polish-one    （全文润色，保留）
└── 「AI 精修」面板   → POST /api/agent/chat             （定向修改，新增）
```

三个 AI 功能独立触发，互不干扰，用户根据场景自选。
