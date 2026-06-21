# 技术方案：Agent 对话页面所需技术栈

配套 [feature-agent-chat-page.md](specs/feature-agent-chat-page.md) 设计文档，调研实现该 Feature 实际需要新增哪些依赖包。结论：**新增量很小**，绝大部分能力（UI 组件库、状态管理、数据请求）项目里已经具备，只需要补两类东西：① 后端的持久化 Checkpointer，② 前端渲染对话消息的轻量 Markdown 渲染器。

---

## 后端新增依赖

| 包名 | 版本 | 用途 | 是否必须 |
|---|---|---|---|
| `langgraph-checkpoint-sqlite` | `>=3.0` | 提供 `AsyncSqliteSaver`，把对话历史持久化到 SQLite，重启服务不丢 | 是 |

**版本兼容性核实**（已查 PyPI 元数据，非估算）：

- `langgraph-checkpoint-sqlite` 最新版 `3.1.0`，依赖约束为 `langgraph-checkpoint<5.0.0,>=4.1.0`。
- 项目当前锁定的 `langgraph-checkpoint` 版本是 `4.1.1`（[uv.lock:543](../uv.lock:543)，由 `langgraph 1.2.6` 引入），落在这个区间内，**兼容，不会触发依赖冲突**。
- 它会带入两个间接依赖：`aiosqlite>=0.20`（异步 SQLite 驱动，纯 Python，无额外系统依赖）、`sqlite-vec>=0.1.6`（向量检索扩展，本 Feature 不会用到，但作为依赖会被装上，体积很小，不影响）。

**不需要新增的**：
- `MessagesState` / `add_messages`（消息历史的数据结构）是 `langgraph` 核心包自带的，当前锁定的 `langgraph 1.2.6` 已经包含，不需要单独装。
- 工具调用（Function Calling）相关能力是 `openai` SDK 自带的 `tools` 参数，当前 `openai>=1.93.0` 已经支持——但按设计文档约定，**这一阶段不接工具调用**，所以现在不会用到，只是确认"以后要做也不用加新包"。

**添加方式**（实现阶段执行，本次只记录方案不动手）：
```bash
uv add langgraph-checkpoint-sqlite
```

---

## 前端新增依赖

| 包名 | 版本 | 用途 | 是否必须 |
|---|---|---|---|
| `react-markdown` | `^10.1.0` | 把助手回复（含 Markdown 格式）渲染成只读富文本气泡 | 是 |
| `remark-gfm` | `^4.0.1` | 配合 `react-markdown` 支持表格、删除线等 GFM 语法 | 建议加（内容场景常用表格） |
| `@radix-ui/react-avatar` | `^1.2.0`（随 shadcn CLI 自动加入） | 消息气泡的用户/助手头像 | 可选，视 UI 细节决定 |

**为什么不直接复用现有的 `@mdxeditor/editor`？**

项目里已经有 `@mdxeditor/editor` 用在 [markdown-editor.tsx](../frontend/src/components/ui/markdown-editor.tsx) 做"可编辑回答"的富文本编辑器，自带工具栏、`contentEditable` 编辑层。聊天消息气泡是**只读展示**，用它需要额外隐藏工具栏、压制可编辑行为，体积和复杂度都对不上场景。`react-markdown` 是专门做"把 Markdown 字符串渲染成只读 DOM"的轻量库（无编辑能力、无工具栏依赖），更贴合气泡展示的需求，且已确认兼容 React 19（`peerDependencies: react >= 18`）。

**`@radix-ui/react-avatar` 如何加入**：项目约定走 `shadcn` CLI（见 [CLAUDE.md](../CLAUDE.md) "添加 shadcn/ui 组件"一节），执行 `bunx --bun shadcn@latest add avatar` 会自动把这个包写进 `package.json` 并生成 `frontend/src/components/ui/avatar.tsx`，不需要手动 `bun add`。已确认该包 `peerDependencies` 明确支持 `react: ^19.0`，无兼容问题。

**已确认不需要新增的**（现有依赖已经覆盖）：

| 需求 | 现有方案 |
|---|---|
| 路由（新增 `/chat`） | `react-router-dom`（已装，7.x） |
| 全局状态（当前活跃 session） | `zustand`（已装，workspace-store 已在用） |
| 请求 Session 列表/对话历史 | `@tanstack/react-query`（已装，已是项目标准数据请求方式） |
| 输入框、按钮、滚动容器、分隔线 | 已有 shadcn 组件：`textarea.tsx`、`button.tsx`、`scroll-area.tsx`、`separator.tsx` |
| 弹层（如需"新建对话"确认） | `dialog.tsx`（已有，复用 `PromptExpandDialog` 同款基建） |

---

## 明确不引入的技术（避免过度设计）

| 候选技术 | 为什么不需要 |
|---|---|
| SSE / WebSocket（流式打字机效果） | 当前设计是"发一条消息→等一次完整回复"（同步 HTTP POST），不是逐字流式输出；引入流式协议是体验优化，不是本阶段功能要求，等对话能力稳定后再评估 |
| 新的全局状态库（如 Redux、Jotai） | `zustand` 已经是项目标准，没有理由引入第二套状态管理 |
| 消息列表虚拟滚动库（如 `react-virtuoso`） | 单个对话的消息量级在本地工具场景下不大，普通 `overflow-y-auto` 足够，项目里其他面板（如热榜分析面板）也是这么做的 |
| 新的 HTTP 客户端库 | 项目已经有统一的 `workflow-api.ts` 封装（基于 `fetch`），新增的 session/conversation 接口直接照现有模式加函数即可 |

---

## 依赖变更汇总

```diff
# pyproject.toml
  dependencies = [
    ...
    "langgraph>=0.2",
+   "langgraph-checkpoint-sqlite>=3.0",
    "openai>=1.93.0",
    ...
  ]
```

```diff
# frontend/package.json
  "dependencies": {
+   "react-markdown": "^10.1.0",
+   "remark-gfm": "^4.0.1",
+   "@radix-ui/react-avatar": "^1.2.0",  // 经 shadcn CLI 自动写入
    ...
  }
```

新增依赖总数：后端 1 个（直接依赖，带 2 个间接依赖），前端 2-3 个，均为体积小、维护活跃、版本已与项目现有依赖核实兼容的成熟库，没有引入新的技术范式（不上新状态管理框架、不上新网络协议）。
