# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

本地可视化内容工作台：从知乎等平台按主题采集问题，通过 LLM 批量生成 AI 回答，在前端编辑并保存。

技术栈：
- 后端：Python 3.11+、FastAPI、uv 包管理
- 前端：React + TypeScript、Vite、Tailwind CSS v4、Zustand、TanStack Query、bun

## 常用命令

### 后端

```bash
uv sync                                        # 安装依赖
uv run python -m app.server                    # 启动后端 http://127.0.0.1:3000
uv run pytest tests/                           # 运行所有测试
uv run pytest tests/test_answer_service.py -v  # 运行单个测试文件
```

### 前端（在 frontend/ 目录执行）

```bash
bun install
bun run dev        # 开发服务器 http://127.0.0.1:5173
bun run build      # 构建到 frontend/dist（由 FastAPI 托管）
bun run typecheck  # tsc --noEmit（修改 .ts/.tsx 后必须通过）
```

前端 dev 模式下 `/api/*` 已通过 Vite 代理转发到后端 `http://127.0.0.1:3000`。

### 添加 shadcn/ui 组件

```bash
cd frontend && bunx --bun shadcn@latest add <component>
```

**注意**：CLI 会把文件生成到字面路径 `frontend/@/components/ui/<component>.tsx`，需要手动移到正确位置：

```bash
mv frontend/@/components/ui/<component>.tsx frontend/src/components/ui/<component>.tsx
```

首次运行可能因 zod 版本冲突报错，重新执行一次通常可以成功。

## 架构

### 后端分层

```
app/
├── server.py              # FastAPI 入口，挂载路由，托管 frontend/dist
├── models.py              # 全局 Pydantic 模型（Topic, QuestionItem, WorkflowConfig…）
├── core/config.py         # 环境变量读取与 WorkflowConfig 构建
├── application/
│   └── workflow_service.py  # 用例编排：collect / generate_one / generate_many / run
├── api/routes/            # workflow.py / session.py / config.py
├── services/              # zhihu_service / answer_service / session_service / topic_expansion
└── infrastructure/
    ├── collectors/factory.py   # CollectorFactory（按 platform 实例化）
    └── llm/deepseek_client.py  # OpenAI-compatible LLM 客户端
```

`WorkflowService`（`application/`）是核心编排层：串联采集器 → 主题扩展 → 去重截断 → 回答生成。

### 前端状态流

```
workflow-api.ts          # 所有后端 API 调用（纯函数）
    ↓
use-workspace.ts         # TanStack Query mutations + 业务逻辑 Hook
    ↓
workspace-store.ts       # Zustand 全局状态
    ↓
workspace-shell.tsx      # UI，只读取 store 渲染
```

**关键约束**：`useWorkspace()` 的返回值**不包含** `saveState` 和 `statusMessage`——这两个字段仅存在于 `workspace-store.ts`。需要使用它们的组件必须直接调用 `useWorkspaceStore()`：

```ts
const { saveState, statusMessage } = useWorkspaceStore();
```

### workspace-shell.tsx 组件结构

`WorkspaceLayout` → `WorkspaceTopbar` + `<Outlet>`（路由）

两个页面共用组件：
- `PromptConfigPanel` — 提示词配置左侧面板，内部使用 `PromptField`
- `PromptField` — 带"全屏"按钮的单个 Textarea，点击弹出 `PromptExpandDialog`（shadcn Dialog）
- `AnswerPanel` — 右侧回答编辑区，含 `QuestionBrief` + `MarkdownEditor`
- `StatusDot` — 内联状态指示器（idle / running / done / warn / error）

**ImportPage 布局**（`/import`）：
- 操作栏（URL 输入 + 平台 + 按钮 + 内联状态）
- 左侧（320px）：最近导入列表 + 提示词配置
- 右侧：回答工作区

**CollectPage 布局**（`/collect`）：
- 操作栏（主题 + 平台 + 采集上限 + 按钮 + 内联状态）
- 左侧（280px）：扩展检索词 + 当前主题 + 提示词配置
- 中间：问题列表（含搜索和分页）
- 右侧：回答工作区

### 全屏布局约束

页面卡片撑满视口依赖以下 flex 链路，如任意一层缺失会导致高度坍塌：

```
div.min-h-screen.flex.flex-col          ← WorkspaceLayout 根容器
  main.flex.flex-1.flex-col             ← 主内容区
    section.flex.flex-1.flex-col        ← 页面 section（每个 Page 组件）
      div.flex-1.min-h-0.grid           ← 内容 grid（三列/两列）
        div.overflow-y-auto             ← 各列（独立滚动）
```

### Pydantic 字段别名约定

后端模型用 `alias="camelCase"`，设置 `populate_by_name=True`。序列化统一用 `model_dump(by_alias=True)`，前端传参也使用 camelCase。

## 环境变量

```bash
cp .env.example .env
```

| 变量 | 说明 |
|------|------|
| `OPENAI_API_KEY` | 必填 |
| `OPENAI_BASE_URL` | 默认：智谱 AI `https://open.bigmodel.cn/api/paas/v4/` |
| `OPENAI_MODEL` | 默认：`GLM-4.7` |
| `ZHIHU_COOKIE_FILE` | 知乎 cookie 文件路径（默认 `.secrets/zhihu.cookie`） |
| `TEST_MODE` | `true` 时不追加公众号 CTA 文本 |
| `MAX_PUSH_COUNT` | 单次采集上限，最大 100 |

## 扩展平台

新增采集平台只需：
1. 实现 `domain/ports.py` 中的 `Collector` 接口
2. 放入 `infrastructure/collectors/`
3. 在 `infrastructure/collectors/factory.py` 的 `CollectorFactory.create()` 中注册 platform 名称
