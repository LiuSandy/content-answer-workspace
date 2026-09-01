# AGENTS.md

本文件是 AI 助手在本仓库工作的快速指南。代码库的完整分析（栈、结构、架构、
集成、测试、风险）见 `docs/codebase/`。

## 项目概述

本地内容工作台（Chat-first Agent 架构）：从知乎、小红书等平台采集或导入问题，
通过多 Agent 协作生成回答，在前端 Tiptap 编辑器中编辑、保存，并支持对话分支、
人工选择（HITL）、私有知识库 RAG、长期记忆和设置管理。

技术栈：

- 后端：Python 3.11+、FastAPI、uv、Pydantic v2、SQLAlchemy 2.0 + Alembic、
  PostgreSQL 16（ParadeDB 镜像，含 pgvector）、LangGraph、
  DeepSeek（OpenAI 兼容，默认 provider）
- 前端：React 19、TypeScript、Vite、Tailwind CSS v4（postcss 方案）、
  Zustand、TanStack Query、React Router、Tiptap 3、bun

## 常用命令

后端：

```bash
docker-compose up -d            # 启动 PostgreSQL（首次必须）
uv sync
uv run alembic upgrade head     # 迁移（server 启动时也会自动迁移）
uv run python -m app.bootstrap.server
uv run pytest tests/
```

前端，在 `frontend/` 目录执行：

```bash
bun install
bun run dev
bun run typecheck
bun run test                    # bun:test 单元测试
bun run build
```

运行地址：

- 后端：`http://127.0.0.1:8000`
- 前端：`http://127.0.0.1:5173`（路由：`/`、`/chat/:chatId`、`/knowledge`、`/settings`）
- Vite dev server 会把 `/api/*` 代理到后端

修改 `.ts` / `.tsx` 后至少运行 `bun run typecheck`。修改后端业务逻辑后优先运行相关
`uv run pytest tests/<file>.py -v`。多数 API 测试需要本地 PostgreSQL 在运行
（`docker-compose up -d`）。

## 关键结构

```text
app/
├── bootstrap/                 # FastAPI composition root、依赖容器、路由与生命周期
├── modules/                   # conversation、writing、memory、knowledge、acquisition、
│                              # documents、publishing、settings 业务模块
├── plugins/                   # LLM、采集源、Embedding、Reranker 与内置工具适配器
├── platform/                  # config、database、files、http、observability、prompts、
│                              # scheduler、tasking 系统基础设施
├── shared/                    # 稳定 DTO、错误、Port、Agent 与 LLM 契约
├── evaluation/                # 检索评测 datasets/metrics/runners
└── cli.py                     # 命令行入口

frontend/src/
├── app/                       # App.tsx（路由）、providers.tsx（QueryClient 等）
├── features/chat/             # 主工作区：三栏布局、Tiptap 编辑器、大纲、质检、版本
├── features/knowledge/        # 知识库页与检索调试
├── features/settings/         # 设置页
├── store/chat-store.ts        # 唯一 Zustand store
├── lib/                       # api.ts（REST 信封封装）、sse.ts（流式客户端）
├── types/workflow.ts
└── components/ui/             # shadcn/ui 组件库
```

## 架构约定

- 路由保持轻薄；采集、导入、生成、润色等编排放在对应模块的 `application/`。
- Pydantic 模型使用 `alias="camelCase"` 和 `populate_by_name=True`；返回前端时使用
  `model_dump(by_alias=True)`。
- 新增后端字段时同步更新对应模块的 API schema、`frontend/src/types/workflow.ts`
  和相关测试。
- API 响应保持 `{"ok": true, "data": ...}`；异常由后端统一包装为
  `{"ok": false, "error": ...}`。
- 不要在前端组件里直接写业务 `fetch`；通过 `lib/api.ts`、`lib/sse.ts` 或
  feature 专属 API 层（如 `settings-api.ts`）调用。
- Application 只能依赖 `app/shared/llm/port.py` 的 `LLMGatewayPort`；Provider、Resolver、
  Registry 与 SDK 仅存在于 `app/plugins/llm/`。业务模型由 Prompt 的 `model.profile`
  选择；Prompt 未指定时回退到 `LLMRuntimeConfig.default`。
- Agent 子图失败只更新各自 `SubAgentState`，不抛到 orchestrator 父图；
  不要吞掉 `asyncio.CancelledError`。

## 前端状态流

服务端状态（会话列表、知识库、设置等）走 TanStack Query：

```text
feature API 层（settings-api.ts / knowledge-api.ts / quality-review-api.ts 等）
  → feature hooks（use-settings.ts / use-knowledge.ts 等）
  → 组件
```

当前会话的轻量 UI 状态只在 `store/chat-store.ts`（`currentChatId`、
`selectedSourceItemId`、`activeLeafMessageId`）。

流式响应统一走 `lib/sse.ts` 的 `streamPost()`，SSE 事件由
`app/platform/http/sse.py` 产生。

## 平台扩展

新增强类型平台 collector：

1. 实现 `app/shared/ports.py` 中的 collector port。
2. 放入 `app/plugins/sources/`。
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

- 不提交 `.env`、cookie（`.secrets/`、`.data/`）、SQLite checkpoint、生成图片、
  输出会话和缓存目录。
- 可提交的默认配置在 `app/platform/config/defaults/`；密钥只写 `.env.example` 的占位说明。
- 回答配图输出到 `generated-images/`，Agent checkpoint 位于
  `output/agent_checkpoints.sqlite`，文件型会话位于 `output/sessions/`。

## 测试提示

常用相关测试：

- URL 导入/知乎：`tests/test_zhihu_import.py`
- 回答生成：`tests/test_answer_service.py`
- 对话图/分支：`tests/test_conversation_graph_branches.py`、`tests/test_chat_branching.py`、
  `tests/test_chat_checkpoint_resume.py`
- Agent/多 Agent/HITL：`tests/test_multi_agent_graph.py`、`tests/test_hitl_graph.py`
- 小红书/采集：`tests/test_xiaohongshu_collector.py`、`tests/test_playwright_fetcher.py`
- LLM provider：`tests/test_llm_provider_architecture.py`、`tests/test_structured_output.py`
- 知识库/RAG：`tests/knowledge/`；长期记忆：`tests/test_memory_service.py`

有网络、真实 cookie、真实 LLM 依赖的路径尽量 mock 或小范围验证。无法完整验证时，
在最终回复里说明原因。
