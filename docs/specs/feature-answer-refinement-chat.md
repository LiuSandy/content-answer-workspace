# Feature: Answer Refinement Chat — 对话式回答精修

## 背景与问题

当前精修回答的方式：
1. 修改 Prompt → 点「重新生成」→ AI 全量重写 → **丢失第一版的好内容**
2. 点「润色」→ AI 按固定 Prompt 改写 → **用户无法定向指导**

用户需要的是：输入「第三段太像 AI，改得自然一点」，AI 只改这一处，其余内容不动。

## 目标

在回答编辑区底部提供一个指令输入框，用户输入自然语言指令，AI 定向修改当前回答，结果直接更新到编辑区。

---

## 现有代码（不得破坏）

| 文件 | 现有功能 |
|------|---------|
| `POST /api/workflow/polish-one` | 一键润色，保留不变 |
| `app/services/answer_service.py` `polish_answer()` | 润色逻辑，保留不变 |
| `workspace-shell.tsx` `AnswerPanel` | 回答编辑区，扩展不重写 |
| `use-workspace.ts` `polishOneAnswer` | 润色 mutation，保留不变 |

---

## 设计

### 后端：复用 RefinementGraph

本 Feature **不新增后端接口**，直接调用 `feature-agent-layer` 提供的 `POST /api/agent/chat`。

**RefinementGraph 的执行流程**（参见 feature-agent-layer）：

```
用户指令 → fetch_answer（读取当前回答）
         → apply_instruction（LLM 定向修改）
         → save_answer（写回）
         → 返回 updatedAnswer
```

前端将 `questionId` 传入，Router 自动选择 RefinementGraph。

### 「一键润色」与「AI 精修」的区别

| | 一键润色（现有） | AI 精修（新增） |
|--|--|--|
| 触发 | 点按钮 | 输入自然语言指令 |
| 修改范围 | 全文润色 | 只改用户指定部分 |
| 用户控制 | 无 | 精确定向 |
| 底层 | `polish_answer()` | `RefinementGraph` |

两者并行存在，互不影响。

---

### 前端

**新增组件：`RefinementChat`**

路径：`frontend/src/features/workspace/refinement-chat.tsx`

**布局：嵌入 `AnswerPanel` 底部，可折叠**

```
┌─────────────────────────────────────┐
│  AnswerPanel（现有）                 │
│  ┌───────────────────────────────┐  │
│  │  MarkdownEditor（现有）        │  │
│  └───────────────────────────────┘  │
│  ┌───────────────────────────────┐  │
│  │  ▶ AI 精修（点击展开）         │  │
│  └───────────────────────────────┘  │
│  ┌───────────────────────────────┐  │  ← 展开后显示
│  │  [输入指令，如：第二段改短一些]  │  │
│  │                         [发送] │  │
│  │  上一条回复：已完成修改         │  │
│  └───────────────────────────────┘  │
└─────────────────────────────────────┘
```

**组件局部状态**（不写入 `workspace-store`）

```typescript
type RefinementState = {
  isOpen: boolean;
  input: string;
  isLoading: boolean;
  lastReply: string | null;
};
```

**交互流程**

1. 用户展开「AI 精修」面板
2. 输入指令，按回车或点「发送」
3. 调用 `/api/agent/chat`，传入 `sessionId` + `questionId` + `message`
4. 收到响应：
   - 若 `answerUpdated === true`：更新 `workspace-store` 中对应问题的 `answer`
   - 显示 `reply` 作为操作反馈
   - 清空输入框
5. 用户可继续输入下一条指令

**关键约束：`MarkdownEditor` 不感知 `RefinementChat`**，只监听 `workspace-store` 中的 `answer` 字段变化，`RefinementChat` 更新 store 后编辑区自动同步。

---

## 前端新增类型

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

## 不受影响的现有功能

- 「润色」按钮（`polish-one`）：保留，功能不变
- 「重新生成」按钮：保留，功能不变
- `MarkdownEditor`：仅读取 store，不感知 AI 精修的存在

---

## 实现顺序

1. 完成 `feature-agent-layer`
2. 前端新增类型和 `agentChat()` 函数
3. 实现 `RefinementChat` 组件
4. 将 `RefinementChat` 嵌入 `AnswerPanel`

---

## 依赖

**前置依赖：`feature-agent-layer`（必须先完成）**
