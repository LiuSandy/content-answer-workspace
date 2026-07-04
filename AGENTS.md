# AGENTS.md

本文件是 Codex 在本仓库工作的快速指南。详细开发流程见
`docs/development-workflow.md`。

## 项目概述

本地内容工作台：从知乎、小红书等平台采集或导入问题，通过 LLM
生成回答，在前端编辑、保存，并支持 Agent 对话、热榜分析和设置管理。

技术栈：

- 后端：Python 3.11+、FastAPI、uv、Pydantic v2、LangGraph、OpenAI-compatible LLM client
- 前端：React 19、TypeScript、Vite、Tailwind CSS v4、Zustand、TanStack Query、React Router、bun

## 常用命令

后端：

```bash
uv sync
uv run python -m app.server
uv run pytest tests/
```

前端，在 `frontend/` 目录执行：

```bash
bun install
bun run dev
bun run typecheck
bun run build
```

运行地址：

- 后端：`http://127.0.0.1:3000`
- 前端：`http://127.0.0.1:5173`
- Vite dev server 会把 `/api/*` 代理到后端

修改 `.ts` / `.tsx` 后至少运行 `bun run typecheck`。修改后端业务逻辑后优先运行相关
`uv run pytest tests/<file>.py -v`。

## 关键结构

```text
app/
├── server.py                  # FastAPI 入口、路由挂载、静态文件托管
├── models.py                  # Pydantic 模型，使用 camelCase alias
├── api/routes/                # workflow/session/config/settings/hotlist/agent/stream
├── application/workflow_service.py
├── application/agent/         # LangGraph 对话、热榜分析、回答精修、工具适配
├── services/                  # 平台、回答、会话、设置、热榜等服务
└── infrastructure/            # collectors、llm、知乎 official client

frontend/src/
├── app/App.tsx
├── features/workspace/        # 导入、采集、热榜、聊天、共享 workspace UI
├── features/workbench/        # 工作台页面
├── features/settings/         # 设置页
├── store/                     # workspace-store、workbench-store
├── types/workflow.ts
└── components/ui/
```

## 架构约定

- 路由保持轻薄；采集、导入、生成、润色等编排放在 `WorkflowService` 或对应服务层。
- Pydantic 模型使用 `alias="camelCase"` 和 `populate_by_name=True`；返回前端时使用 `model_dump(by_alias=True)`。
- 新增后端字段时同步更新 `app/models.py`、`frontend/src/types/workflow.ts` 和相关测试。
- API 响应保持 `{"ok": true, "data": ...}`；异常由后端统一包装为 `{"ok": false, "error": ...}`。
- 不要在前端组件里直接写业务 `fetch`；通过 `workflow-api.ts`、settings API 或 feature 专属 API 层调用。

## 前端状态流

Workspace 页面：

```text
workflow-api.ts → use-workspace.ts → workspace-store.ts → workspace-shell.tsx
```

`useWorkspace()` 不是完整 store。`saveState`、`statusMessage`、`topicDraft` 等只存在于
`useWorkspaceStore()`；需要这些字段的组件必须直接读 store。

Workbench 页面使用独立的 `workbench-store.ts`。不要把工作台专属状态塞进
`workspace-store.ts`。

## 平台扩展

新增强类型平台 collector：

1. 实现 `app/domain/ports.py` 中的 collector port。
2. 放入 `app/infrastructure/collectors/`。
3. 在 `CollectorFactory._collectors` 注册平台名，必要时注册 `platform:official`。
4. 更新前端 `Platform` 类型、平台选择 UI 和测试。

新增 YAML 平台时优先复用 `UniversalCollector`、`platform_config_loader.py`、
`fetchers/`、`extractors/` 和 `question_item_mapper.py`。

## UI 与布局

- 新 UI 优先复用 `frontend/src/components/ui/` 和现有页面模式。
- 全屏页面依赖 `flex`、`flex-1`、`min-h-0`、独立滚动列；改布局时不要破坏这条链路。
- 添加 shadcn/ui 组件后，如果 CLI 生成到 `frontend/@/components/ui/`，手动移动到
  `frontend/src/components/ui/`。

## 文件与安全

- 不提交 `.env`、cookie、SQLite checkpoint、生成图片、输出会话和缓存目录。
- 可提交的默认配置在 `app/config/`；密钥只写 `.env.example` 的占位说明。
- 回答配图输出到 `generated-images/`，Agent checkpoint 位于 `output/agent_checkpoints.sqlite`。

## 测试提示

常用相关测试：

- URL 导入/知乎：`tests/test_zhihu_import.py`
- 回答生成：`tests/test_answer_service.py`
- 会话：`tests/test_session_service.py`
- Agent：`tests/test_agent_chat_node.py`、`tests/test_conversation_graph.py`
- 小红书/采集：`tests/test_xiaohongshu_collector.py`、`tests/test_playwright_fetcher.py`

有网络、真实 cookie、真实 LLM 依赖的路径尽量 mock 或小范围验证。无法完整验证时，在最终回复里说明原因。
