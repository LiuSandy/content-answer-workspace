# Plan: 工作台页面实施方案

## 设计原则

| 原则 | 体现 |
|------|------|
| 职责分离 | 工作台状态独立存放在 `workbench-store.ts`，不污染现有 `workspace-store.ts` |
| 优先复用 | URL 导入逻辑复用现有 `ImportPage` 的 `useWorkspace` hook；回答区复用现有 `AnswerPanel` |
| 单一来源 | 平台列表、问题去重逻辑集中在 `workbench-store.ts`，页面组件只读取 store |
| 前端会话 | 数据只存 Zustand，刷新后清空，无需后端新接口 |

---

## 一、类型变更

**文件**：`frontend/src/types/workflow.ts`

### 1. Platform 类型无需变更

工作台的来源平台就是采集时的实际平台（`zhihu` / `xiaohongshu`），`Platform` 类型保持不变。热榜页面和对话页面不是独立平台，热榜问题的实际来源平台仍是 `zhihu`。

平台 Tabs 固定为：**全部 / 知乎 / 小红书**，无需动态扩展。

### 2. 新增 WorkbenchItem 类型

在现有 `QuestionItem` 基础上扩展，附加工作台专属元数据：

```ts
export type WorkbenchItem = QuestionItem & {
  addedAt: string          // ISO 时间，用于排序
  sourcePlatform: Platform // 来源平台（决定平台 Tab 归属）
  sourceTopic: string      // 来源主题
  promptConfig: {
    answerStyle: string
    systemPrompt: string
    generationPrompt: string
  }
}
```

> `QuestionItem` 本身已有 `platform?: Platform`，`WorkbenchItem.sourcePlatform` 作为强制字段，与现有可选字段共存。

---

## 二、新建 Workbench Store

**文件**：`frontend/src/store/workbench-store.ts`（新建）

### 状态结构

```ts
type WorkbenchState = {
  items: WorkbenchItem[]                     // 工作台问题列表
  selectedItemId: string | null              // 当前选中问题
  statusFilter: "all" | "pending" | "done"  // 状态筛选
  platformFilter: Platform | "all"           // 平台筛选（由平台 Tab 驱动）
  searchKeyword: string                      // 搜索关键词

  // 回答生成状态
  isGenerating: boolean

  // Actions
  addItems: (items: WorkbenchItem[]) => void  // 批量加入，按 id 去重
  removeItem: (id: string) => void
  selectItem: (id: string | null) => void
  updateItemAnswer: (id: string, answer: string) => void
  updateItemStatus: (id: string, status: "pending" | "done") => void
  setStatusFilter: (f: "all" | "pending" | "done") => void
  setPlatformFilter: (p: Platform | "all") => void
  setSearchKeyword: (kw: string) => void
  setIsGenerating: (v: boolean) => void
}
```

### 去重逻辑（addItems）

```
新传入的 items
    ↓
过滤掉 id 已存在于 state.items 的条目
    ↓
将剩余条目追加到 state.items 头部（最新在前）
    ↓
return toast "已加入 N 条，跳过 M 条重复"
```

---

## 三、新建 WorkbenchPage

**文件**：`frontend/src/features/workbench/workbench-page.tsx`（新建）

### 布局结构

```
section.flex.flex-col.flex-1        ← 全屏 flex 链路（对齐现有页面约定）
  ├── WorkbenchUrlImportBar          ← 顶部 URL 导入栏（固定高度）
  ├── div.flex.flex-1.min-h-0
  │    ├── WorkbenchQuestionList     ← 左侧问题列表（固定宽度 320px）
  │    └── WorkbenchAnswerPanel      ← 右侧回答工作区（flex-1）
```

### 子组件分工

| 组件 | 文件 | 职责 |
|------|------|------|
| `WorkbenchUrlImportBar` | `workbench-url-import-bar.tsx` | URL 输入 + 平台选择 + 导入按钮 + 状态行，复用现有 `workflow-api.ts` 的 `parseQuestionUrl` |
| `WorkbenchQuestionList` | `workbench-question-list.tsx` | 搜索栏 + 状态 filter + 平台 Tabs + 问题列表 + 分页 |
| `WorkbenchAnswerPanel` | 复用现有 `AnswerPanel` 组件 | 右侧回答编辑区，传入 workbench store 的当前问题 |

---

## 四、WorkbenchQuestionList 设计

**文件**：`frontend/src/features/workbench/workbench-question-list.tsx`（新建）

### 结构

```
div（左侧列，overflow-y-auto）
  ├── Input（搜索框）
  ├── 状态 filter（Select 或 chip row）：全部 / 未生成 / 已生成
  ├── Tabs（shadcn/ui）
  │    ├── TabsList：全部 | 知乎 | 小红书 | 热榜 | 对话
  │    └── TabsContent（每个平台对应一份列表）
  └── 底部：计数文本 + 分页（复用现有分页逻辑）
```

### 平台 Tab 数据来源

Tab 固定为三个：**全部 / 知乎 / 小红书**，与现有 `Platform` 类型一一对应，无需动态生成。

### shadcn Tabs 安装

```bash
cd frontend && bunx --bun shadcn@latest add tabs
mv frontend/@/components/ui/tabs.tsx frontend/src/components/ui/tabs.tsx
```

---

## 五、CollectPage 改造

**文件**：`frontend/src/features/workspace/workspace-shell.tsx`（修改）

### 改造内容

在 `CollectPage` 组件的问题列表区域（`QuestionList`）增加：

1. **每条问题左侧加 Checkbox**（shadcn `Checkbox` 组件，需安装）
2. **列表顶部增加批量操作栏**，仅在有勾选时显示：

```
已选 N 条  [清空选择]  [加入工作台 →]
```

3. **点击"加入工作台"逻辑**：
   - 将勾选的 `QuestionItem` 转换为 `WorkbenchItem`，补充 `sourcePlatform`、`sourceTopic`（来自当前 `selectedTopic`）、`promptConfig`（来自当前 store 的 answerStyle / systemPrompt / generationPrompt）
   - 调用 `workbenchStore.addItems()`
   - Toast 提示："已加入 N 条" 或 "已加入 N 条，跳过 M 条重复"
   - 清空勾选状态

### 勾选状态管理

勾选状态为 `CollectPage` 本地 state（`useState<Set<string>>`），不存入 store。

---

## 六、路由与导航变更

### App.tsx

**文件**：`frontend/src/app/App.tsx`（修改）

```tsx
import { WorkbenchPage } from "@/features/workbench/workbench-page"

// 在 WorkspaceLayout 下新增：
<Route path="workbench" element={<WorkbenchPage />} />
```

### AppSidebar

**文件**：`frontend/src/features/workspace/app-sidebar.tsx`（修改）

在 `navItems` 数组中新增工作台入口（位于"主题采集"之后）：

```ts
{ to: "/workbench", label: "工作台", icon: LayoutDashboard }
```

---

## 七、需要安装的 shadcn/ui 组件

| 组件 | 用途 |
|------|------|
| `tabs` | 工作台左侧平台 Tab |
| `checkbox` | CollectPage 批量勾选 |
| `toast` / `sonner` | 加入工作台的 toast 提示（确认是否已有） |

---

## 八、文件结构

```
新增文件
frontend/src/
├── store/
│   └── workbench-store.ts                     ← Workbench Zustand store
├── features/
│   └── workbench/
│       ├── workbench-page.tsx                  ← 页面主组件（布局）
│       ├── workbench-url-import-bar.tsx        ← 顶部 URL 导入栏
│       ├── workbench-question-list.tsx         ← 左侧问题列表（含平台 Tabs）
│       └── workbench-answer-panel.tsx          ← 右侧回答区（薄包装）
├── components/ui/
│   ├── tabs.tsx                                ← shadcn 安装后移入
│   └── checkbox.tsx                            ← shadcn 安装后移入

修改文件
frontend/src/
├── app/App.tsx                                 ← 新增 /workbench 路由
├── types/workflow.ts                           ← 扩展 Platform，新增 WorkbenchItem
└── features/workspace/
    ├── app-sidebar.tsx                         ← navItems 新增工作台
    └── workspace-shell.tsx                     ← CollectPage 加 checkbox + 批量操作栏
```

---

## 九、实施阶段

### Phase 1：基础设施

- [ ] 新增 `WorkbenchItem` 类型（`types/workflow.ts`，`Platform` 无需改动）
- [ ] 安装 shadcn `tabs`、`checkbox` 组件并移至正确位置
- [ ] 新建 `workbench-store.ts`，实现 `addItems`（去重）、`selectItem`、filter 等 actions

### Phase 2：WorkbenchPage 骨架

- [ ] 新建 `workbench-page.tsx`，搭建布局（顶部栏 + 左右两栏）
- [ ] 新建 `workbench-url-import-bar.tsx`，复用 `parseQuestionUrl` 实现 URL 导入
- [ ] 在 `App.tsx` 注册 `/workbench` 路由
- [ ] 在 `app-sidebar.tsx` 新增工作台导航项
- [ ] 验证路由可访问，页面骨架正常渲染

### Phase 3：问题列表

- [ ] 新建 `workbench-question-list.tsx`，实现搜索、状态 filter、平台 Tabs
- [ ] 平台 Tabs 动态生成（仅显示 items 中存在的平台）
- [ ] 分页逻辑（复用现有分页 UI 模式）
- [ ] 点击问题条目触发 `selectItem`

### Phase 4：回答工作区

- [ ] 新建 `workbench-answer-panel.tsx`，接入 workbench store 的选中问题
- [ ] 复用现有 `AnswerPanel` / `MarkdownEditor` 组件
- [ ] 接入生成回答逻辑（复用现有 `generateOne` API）

### Phase 5：CollectPage 批量导入

- [ ] `workspace-shell.tsx` 的 CollectPage 问题列表每条加 `Checkbox`
- [ ] 实现 `selectedIds: Set<string>` 本地状态
- [ ] 批量操作栏（已选 N 条 + 加入工作台按钮）
- [ ] 点击后转换数据格式，调用 `workbenchStore.addItems()`，清空选择，Toast 提示

### Phase 6：联调验证

- [ ] 从 CollectPage 勾选并加入，切换到工作台能看到问题
- [ ] 平台 Tab 随导入数据动态出现
- [ ] 重复导入静默去重，Toast 正确提示
- [ ] URL 直接导入能加入列表
- [ ] 选中问题后右侧正常展示并可生成回答
- [ ] 全屏高度不坍塌（flex 链路完整）

---

## 十、相关文档

- 需求规格：`docs/specs/workbench-page.md`
- 现有类型定义：`frontend/src/types/workflow.ts`
- 现有 Zustand store：`frontend/src/store/workspace-store.ts`
- 现有 workspace-shell：`frontend/src/features/workspace/workspace-shell.tsx`
- 现有路由：`frontend/src/app/App.tsx`
- 现有侧边栏：`frontend/src/features/workspace/app-sidebar.tsx`
