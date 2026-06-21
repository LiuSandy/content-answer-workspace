# Feature: Hotlist Analysis — 热榜 AI 分析

## 背景与问题

当前热榜功能只是展示列表，用户需要逐条阅读才能判断：
- 哪些话题值得写？
- 热点集中在哪些领域？
- 哪个方向适合切入？

人工判断费时且容易遗漏规律。

## 目标

用户点击「AI 分析」，系统返回结构化的内容策略结论：话题分布、内容机会、创作建议。用户可一键将推荐选题导入采集流程。

---

## 现有代码（不得破坏）

| 文件 | 现有功能 |
|------|---------|
| `app/services/hotlist_service.py` `fetch_hotlist()` | 热榜拉取，AnalysisGraph 内复用 |
| `GET /api/hotlist` | 热榜接口，保留不变 |
| `workspace-shell.tsx` `HotlistPage` | 热榜展示页，扩展不重写 |
| `workflow-api.ts` `getHotlist()` | 热榜 API 调用，保留不变 |

---

## 设计

### 后端：复用 AnalysisGraph

本 Feature **不新增后端接口**，调用 `feature-agent-layer` 提供的 `POST /api/agent/chat`。

**AnalysisGraph 的执行流程**（参见 feature-agent-layer）：

```
用户触发 → fetch_hotlist（调用现有 fetch_hotlist()，取 30 条数据）
         → analyze（LLM 分析，返回结构化 JSON）
         → 返回 reply（JSON 字符串）
```

前端省略 `questionId`，Router 自动选择 AnalysisGraph。

**LLM 输出的 JSON 结构**（在 `analyze_hotlist` 节点中定义）：

```json
{
  "topicDistribution": [
    {"field": "职场/职业", "count": 12, "examples": ["为什么年轻人不想上班了"]}
  ],
  "contentOpportunities": [
    {"direction": "AI 对普通人的影响", "reason": "热度高，个人视角内容少"}
  ],
  "audienceMood": "焦虑与好奇并存",
  "recommendations": [
    {
      "topic": "AI 会取代哪些工作",
      "reason": "热榜前 5 中有 3 条相关，切入点多",
      "keywords": ["AI 失业", "人工智能替代", "职业转型"]
    }
  ]
}
```

---

### 前端

**扩展 `HotlistPage`：左右两栏布局**

```
┌──────────────────────────────────────────────────────────┐
│  知乎热榜                            [刷新]  [AI 分析]   │
├─────────────────────┬────────────────────────────────────┤
│  热榜列表（现有）    │  分析结论（新增，点击按钮后展开）    │
│                     │                                    │
│  1. 标题...         │  话题分布                          │
│  2. 标题...         │  ▓▓▓▓▓▓ 职场/职业  12 条          │
│  3. 标题...         │  ▓▓▓▓   科技/AI    8 条           │
│  ...                │                                    │
│                     │  内容机会                          │
│                     │  → AI 对普通人的影响               │
│                     │    热度高，个人视角内容少            │
│                     │                                    │
│                     │  创作建议                          │
│                     │  ① AI 会取代哪些工作               │
│                     │     [采用此选题 →]                 │
│                     │  ② ...                            │
└─────────────────────┴────────────────────────────────────┘
```

**新增组件：`HotlistAnalysisPanel`**

路径：`frontend/src/features/workspace/hotlist-analysis-panel.tsx`

**组件局部状态**

```typescript
type AnalysisPanelState = {
  isLoading: boolean;
  result: HotlistAnalysisResult | null;
  error: string | null;
};
```

**交互流程**

1. 用户点击「AI 分析」按钮
2. 前端调用 `/api/agent/chat`（省略 `questionId`，`message` 固定为触发语）：
   ```json
   {
     "sessionId": "hotlist_analysis",
     "message": "请分析当前热榜，给出内容策略建议"
   }
   ```
3. 按钮进入 loading 状态
4. 收到响应，`JSON.parse(response.reply)` → `HotlistAnalysisResult`
5. 右侧面板显示结构化分析结论

**「采用此选题」联动**

用户点击某条 recommendation 的「采用」按钮：
1. 跳转到 `/collect` 页面
2. 将 `recommendation.topic` 写入 `workspace-store` 的主题名称
3. 将 `recommendation.keywords` 写入关键词列表
4. 界面聚焦到主题输入区，等待用户确认后手动触发采集

---

## 前端新增类型

```typescript
// frontend/src/types/workflow.ts 追加

export type HotlistAnalysisResult = {
  topicDistribution: {
    field: string;
    count: number;
    examples: string[];
  }[];
  contentOpportunities: {
    direction: string;
    reason: string;
  }[];
  audienceMood: string;
  recommendations: {
    topic: string;
    reason: string;
    keywords: string[];
  }[];
};
```

`AgentChatPayload` 和 `AgentChatResponse` 类型由 `feature-answer-refinement-chat` 统一定义，本 Feature 直接复用。

---

## 布局变更说明

`HotlistPage` 改为左右两栏：
- 左栏（现有热榜列表）：`flex-1 min-w-0`
- 右栏（分析面板）：`w-96 border-l`，分析结果出现前显示空状态占位

现有热榜列表的所有交互（导入单条问题、刷新）**保持不变**。

---

## 不受影响的现有功能

- 热榜列表展示、刷新：不变
- 「导入」按钮（从热榜导入单条问题到工作区）：不变
- `GET /api/hotlist` 接口：不变

---

## 实现顺序

1. 完成 `feature-agent-layer`（含 `fetch_hotlist` + `analyze_hotlist` 节点）
2. 前端新增 `HotlistAnalysisResult` 类型
3. 实现 `HotlistAnalysisPanel` 组件
4. 修改 `HotlistPage` 为两栏布局，嵌入分析面板
5. 实现「采用选题」→ 跳转采集页联动

---

## 依赖

**前置依赖：`feature-agent-layer`（必须先完成）**
**同级依赖：`feature-answer-refinement-chat` 的前端类型定义（`AgentChatPayload/Response`）**
