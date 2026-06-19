# Plan: Hotlist Analysis 实施方案

## 设计原则

| 原则 | 体现 |
|------|------|
| 单一职责 | `HotlistAnalysisPanel` 只展示分析结果；解析 JSON 交给独立 parser 函数；导入选题交给 `useWorkspaceStore` |
| 开闭原则 | `HotlistPage` 只做布局扩展，不改现有列表组件 |
| 低耦合 | 分析面板不感知热榜列表；「采用选题」通过 store + 路由实现，不与列表耦合 |
| 防御性设计 | LLM 返回 JSON 可能格式错误，解析失败时降级展示原始文本 |

---

## 前置依赖

`plan-agent-layer` 全部完成后方可实施本 Feature。

---

## 数据流

```
用户点击「AI 分析」
    ↓
HotlistPage.handleAnalyze()
    ↓
agentChat({ sessionId: "hotlist", message: "分析热榜" })
    ↓
POST /api/agent/chat              ← Agent Layer（AnalysisGraph）
    ↓
response.reply（JSON 字符串）
    ↓
parseAnalysisResult(reply)
    ├── 成功 → HotlistAnalysisPanel 渲染结构化结论
    └── 失败 → HotlistAnalysisPanel 渲染原始文本（降级）

用户点击「采用选题」
    ↓
useWorkspaceStore.setTopicDraft(recommendation)
    ↓
navigate("/collect")
    ↓
CollectPage 读取 store 中的草稿，填入主题输入区
```

---

## 前端组件设计

### 组件树

```
HotlistPage（现有，改为两栏布局）
├── HotlistListPanel（现有内容提取为子组件，逻辑不变）
│   ├── HotlistItemCard（现有，不改）
│   └── ...
└── HotlistAnalysisPanel（新增）
      ├── AnalysisEmpty       ← 未分析时的占位状态
      ├── AnalysisLoading     ← 分析中的骨架屏
      ├── AnalysisError       ← 解析失败的降级展示
      └── AnalysisResult      ← 结构化结论展示
            ├── TopicDistributionSection
            ├── ContentOpportunitiesSection
            └── RecommendationsSection
                  └── RecommendationCard（含「采用」按钮）
```

### 类型定义

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

// 分析面板展示状态（组件局部，不进 store）
export type AnalysisStatus =
  | { type: "idle" }
  | { type: "loading" }
  | { type: "success"; data: HotlistAnalysisResult }
  | { type: "error"; raw: string };   // LLM 返回内容保留，用于降级展示
```

### JSON 解析函数（纯函数，独立可测）

```typescript
// frontend/src/features/workspace/hotlist-analysis-parser.ts

import type { HotlistAnalysisResult } from "@/types/workflow";

export function parseAnalysisResult(
  raw: string
): HotlistAnalysisResult | null {
  try {
    const parsed = JSON.parse(raw);
    // 基础结构校验（防御 LLM 幻觉）
    if (
      !Array.isArray(parsed.topicDistribution) ||
      !Array.isArray(parsed.contentOpportunities) ||
      !Array.isArray(parsed.recommendations) ||
      typeof parsed.audienceMood !== "string"
    ) {
      return null;
    }
    return parsed as HotlistAnalysisResult;
  } catch {
    return null;
  }
}
```

**设计决策**：解析逻辑独立为纯函数，不放在组件内，便于单元测试和复用。

### HotlistAnalysisPanel 组件

```typescript
// frontend/src/features/workspace/hotlist-analysis-panel.tsx

import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { agentChat } from "./workflow-api";
import { parseAnalysisResult } from "./hotlist-analysis-parser";
import { useWorkspaceStore } from "@/store/workspace-store";
import type { AnalysisStatus, HotlistAnalysisResult } from "@/types/workflow";

export function HotlistAnalysisPanel() {
  const [status, setStatus] = useState<AnalysisStatus>({ type: "idle" });
  const navigate = useNavigate();
  const setTopicDraft = useWorkspaceStore((s) => s.setTopicDraft);

  async function handleAnalyze() {
    setStatus({ type: "loading" });
    try {
      const res = await agentChat({
        sessionId: "hotlist_analysis",
        message: "请分析当前热榜，给出内容策略建议",
      });
      const parsed = parseAnalysisResult(res.reply);
      if (parsed) {
        setStatus({ type: "success", data: parsed });
      } else {
        setStatus({ type: "error", raw: res.reply });
      }
    } catch {
      setStatus({ type: "error", raw: "请求失败，请重试" });
    }
  }

  function handleAdopt(rec: HotlistAnalysisResult["recommendations"][0]) {
    // 写入 store，CollectPage 读取后自动填入输入区
    setTopicDraft({ name: rec.topic, keywords: rec.keywords });
    navigate("/collect");
  }

  return (
    <div className="w-96 border-l flex flex-col">
      <div className="p-3 border-b flex items-center justify-between">
        <span className="text-sm font-medium">AI 分析</span>
        <button
          className="text-sm px-3 py-1 bg-primary text-primary-foreground rounded disabled:opacity-50"
          disabled={status.type === "loading"}
          onClick={handleAnalyze}
        >
          {status.type === "loading" ? "分析中…" : "开始分析"}
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-3">
        {status.type === "idle" && <AnalysisEmpty />}
        {status.type === "loading" && <AnalysisLoading />}
        {status.type === "error" && <AnalysisError raw={status.raw} />}
        {status.type === "success" && (
          <AnalysisResult data={status.data} onAdopt={handleAdopt} />
        )}
      </div>
    </div>
  );
}
```

### RecommendationCard（含采用按钮）

```typescript
function RecommendationCard({
  rec,
  index,
  onAdopt,
}: {
  rec: HotlistAnalysisResult["recommendations"][0];
  index: number;
  onAdopt: (rec: HotlistAnalysisResult["recommendations"][0]) => void;
}) {
  return (
    <div className="border rounded p-3 space-y-1">
      <div className="flex items-start justify-between gap-2">
        <span className="text-sm font-medium">
          {index + 1}. {rec.topic}
        </span>
        <button
          className="text-xs px-2 py-1 border rounded hover:bg-muted shrink-0"
          onClick={() => onAdopt(rec)}
        >
          采用 →
        </button>
      </div>
      <p className="text-xs text-muted-foreground">{rec.reason}</p>
      <div className="flex flex-wrap gap-1">
        {rec.keywords.map((kw) => (
          <span key={kw} className="text-xs bg-muted px-1.5 py-0.5 rounded">
            {kw}
          </span>
        ))}
      </div>
    </div>
  );
}
```

---

## HotlistPage 布局改造

现有 `HotlistPage` 的全部列表逻辑**提取为 `HotlistListPanel`**（只是包一层 div，逻辑不变），然后改为两栏：

```typescript
// 改造前（单栏）
export function HotlistPage() {
  // ... 现有逻辑 ...
  return <div>热榜列表...</div>;
}

// 改造后（两栏，现有逻辑移入 HotlistListPanel）
export function HotlistPage() {
  return (
    <div className="flex flex-1 min-h-0">
      <HotlistListPanel className="flex-1 min-w-0 overflow-y-auto" />
      <HotlistAnalysisPanel />
    </div>
  );
}
```

**HotlistListPanel** = 把原 `HotlistPage` return 内容原样搬入，不改任何逻辑。

---

## workspace-store 新增 topicDraft

「采用选题」需要跨路由传参，通过 store 的短暂草稿状态实现：

```typescript
// frontend/src/store/workspace-store.ts 新增

type TopicDraft = {
  name: string;
  keywords: string[];
} | null;

// state
topicDraft: TopicDraft;

// action
setTopicDraft: (draft: TopicDraft) => void;

// 实现
setTopicDraft: (draft) => set({ topicDraft: draft }),
```

CollectPage 在 mount 时检查并消费 draft：

```typescript
// CollectPage useEffect
useEffect(() => {
  const draft = useWorkspaceStore.getState().topicDraft;
  if (draft) {
    // 填入主题输入区
    setTopicName(draft.name);
    setKeywords(draft.keywords);
    // 消费后清空，防止刷新后重复触发
    useWorkspaceStore.getState().setTopicDraft(null);
  }
}, []);
```

---

## 实施阶段

### Phase 1：类型与解析工具
- [ ] `types/workflow.ts` 追加 `HotlistAnalysisResult`、`AnalysisStatus`
- [ ] 实现 `hotlist-analysis-parser.ts`（纯函数，先写测试）

### Phase 2：Store 扩展
- [ ] `workspace-store.ts` 新增 `topicDraft` + `setTopicDraft`

### Phase 3：组件实现
- [ ] 实现 `HotlistAnalysisPanel`（含子组件）
- [ ] 将现有 `HotlistPage` 内容提取为 `HotlistListPanel`
- [ ] 改造 `HotlistPage` 为两栏布局

### Phase 4：CollectPage 接收 draft
- [ ] CollectPage mount 时读取并消费 `topicDraft`

### Phase 5：测试
- [ ] `parseAnalysisResult` 单元测试（正常 JSON、格式错误 JSON、空字符串）
- [ ] `HotlistAnalysisPanel` 组件测试（Mock `agentChat`，验证各状态渲染）
- [ ] `RecommendationCard` 点击「采用」后 store 和路由的联动测试

---

## 测试策略

```typescript
// parseAnalysisResult 纯函数测试（无 DOM，最快）
test("正常 JSON 返回解析结果", () => {
  const json = JSON.stringify({
    topicDistribution: [{ field: "职场", count: 5, examples: [] }],
    contentOpportunities: [{ direction: "AI 转型", reason: "热度高" }],
    audienceMood: "焦虑",
    recommendations: [{ topic: "AI 会取代你吗", reason: "...", keywords: [] }],
  });
  expect(parseAnalysisResult(json)).not.toBeNull();
});

test("格式错误时返回 null", () => {
  expect(parseAnalysisResult("不是JSON")).toBeNull();
  expect(parseAnalysisResult('{"missing": "fields"}')).toBeNull();
});

// 组件测试：验证「采用」跳转
test("点击采用后跳转到采集页", async () => {
  vi.mocked(agentChat).mockResolvedValueOnce({
    reply: JSON.stringify(mockAnalysisResult),
    answerUpdated: false,
    operationSummary: "热榜分析",
  });
  render(<HotlistAnalysisPanel />, { wrapper: RouterWrapper });
  fireEvent.click(screen.getByText("开始分析"));
  await waitFor(() => screen.getByText("采用 →"));
  fireEvent.click(screen.getAllByText("采用 →")[0]);
  expect(mockNavigate).toHaveBeenCalledWith("/collect");
  expect(useWorkspaceStore.getState().topicDraft).not.toBeNull();
});
```

---

## 与现有功能的共存关系

```
HotlistPage
├── 热榜列表（现有）               ← 逻辑完整保留在 HotlistListPanel
│   └── 「导入」按钮              ← 导入单条到工作区，保留不变
└── AI 分析面板（新增）            ← 独立面板，不干扰列表
      └── 「采用选题」按钮         ← 跳转采集页，通过 store 传参
```
