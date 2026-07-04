# AGENTS.md

This file provides guidance to Codex when working in this repository.

## 项目概述

这是一个本地内容采集、分析、回答生成与编辑工作台。后端通过 FastAPI 暴露采集、会话、设置、热榜、Agent 对话和 SSE 流式接口；前端用 React/Vite 提供导入、采集、热榜、工作台、对话和设置页面。

技术栈：

- 后端：Python 3.11+、FastAPI、uv、Pydantic v2、LangGraph、OpenAI-compatible LLM client
- 前端：React 19、TypeScript、Vite、Tailwind CSS v4、Zustand、TanStack Query、React Router、bun
- 采集：知乎 web/official、小红书 collector、YAML 驱动的 UniversalCollector，以及 Agent 工具层里的多平台搜索/抓取工具

## 常用命令

后端：

```bash
uv sync
uv run python -m app.server
uv run pytest tests/
uv run pytest tests/test_answer_service.py -v
```

前端命令在 `frontend/` 目录执行：

```bash
bun install
bun run dev
bun run typecheck
bun run build
bun run build:strict
```

运行地址：

- 后端默认 `http://127.0.0.1:3000`
- 前端默认 `http://127.0.0.1:5173`
- Vite dev server 已把 `/api/*` 代理到 `http://127.0.0.1:3000`
- `bun run build` 生成 `frontend/dist` 后，FastAPI 会直接托管前端静态文件

修改 `.ts` / `.tsx` 后必须至少跑 `bun run typecheck`。修改后端业务逻辑后优先跑相关 `uv run pytest tests/<file>.py -v`，跨层改动再跑全量测试。

## 关键目录

```text
app/
├── server.py                         # FastAPI 入口、路由挂载、frontend/dist 托管、LangGraph checkpoint 初始化
├── models.py                         # 前后端共享响应/请求模型，统一 camelCase alias
├── api/routes/                       # workflow/session/config/settings/hotlist/agent/stream 路由
├── application/
│   ├── workflow_service.py           # 采集、导入、生成、润色的应用编排层
│   └── agent/                        # LangGraph 对话、热榜分析、回答精修、工具适配
├── services/                         # LLM 回答、会话持久化、平台服务、设置服务、热榜服务
├── infrastructure/
│   ├── collectors/                   # CollectorFactory、知乎、小红书、UniversalCollector、fetcher/extractor
│   ├── llm/deepseek_client.py        # OpenAI-compatible LLM 调用封装
│   └── zhihu/official_client.py      # 知乎官方接口客户端
└── config/
    ├── loader.py                     # TOML 与 prompt 加载、启动 warmup
    ├── settings.toml                 # 非密钥运行常量
    ├── default_topics.toml           # 默认主题
    └── prompts/*.md                  # 系统、生成、对话、热榜提示词

frontend/src/
├── app/App.tsx                       # 路由表
├── features/workspace/               # 导入、采集、热榜、聊天、共享 workspace UI/API/hooks
├── features/workbench/               # 工作台页面与局部组件
├── features/settings/                # 设置页与 settings API hook
├── store/                            # Zustand store：workspace-store、workbench-store
├── types/workflow.ts                 # 前端 API 类型
└── components/ui/                    # shadcn/Radix 风格基础组件
```

## 后端架构约定

`app/server.py` 负责应用启动、路由挂载、统一异常响应、`/generated-images` 静态目录和 `frontend/dist` 托管。启动时会 `warmup_config()` 并创建 `output/agent_checkpoints.sqlite` 作为 LangGraph 对话 checkpoint。

HTTP 路由保持轻薄：参数校验、调用应用服务、包装 `{"ok": true, "data": ...}`。采集/生成/润色/URL 导入逻辑集中在 `WorkflowService`，不要把编排逻辑散落到路由里。

Pydantic 模型使用 `alias="camelCase"` 和 `populate_by_name=True`。返回给前端时统一 `model_dump(by_alias=True)`；前端请求字段也使用 camelCase。新增字段时同步更新 `app/models.py` 与 `frontend/src/types/workflow.ts`。

配置分两层：

- 密钥和部署环境来自 `.env` / 环境变量，由 `app/core/config.py` 读取。
- 可提交的默认运行常量、主题和提示词在 `app/config/`，由 `app/config/loader.py` 读取。新增 prompt 后如需启动校验，加入 `warmup()`。

## 采集与平台扩展

`CollectorFactory.create(platform, source)` 支持 `official`、`web`、`auto`：

- `source=official` 要求存在对应 `"<platform>:official"` collector
- `source=auto` 对知乎会在存在 `ZHIHU_ACCESS_SECRET` 时优先 official，否则降级 web
- 普通 collector 注册在 `CollectorFactory._collectors`
- 未注册平台会尝试读取 `app/infrastructure/collectors/platforms/<platform>.yaml` 并用 `UniversalCollector`

新增强类型平台 collector 时：

1. 实现 `app/domain/ports.py` 中的 collector port。
2. 放入 `app/infrastructure/collectors/`。
3. 在 `CollectorFactory._collectors` 注册平台名，必要时注册 `platform:official`。
4. 更新前端 `Platform` 类型、平台选择 UI、测试。

新增 YAML 平台时优先复用 `UniversalCollector`、`platform_config_loader.py`、`fetchers/`、`extractors/` 和 `question_item_mapper.py`，避免在业务层写平台分支。

## Agent 与流式接口

Agent 路由在 `app/api/routes/agent.py`：

- `/api/agent/conversation` 与 `/api/agent/conversation/stream`：对话页专用，使用 `conversation_graph` 和 SQLite checkpoint 持久历史。
- `/api/agent/conversation/{session_id}/history`：把 LangGraph 消息历史重建成前端 `ChatMessage[]`，其中工具调用会折叠为 `role: "tool"`，结构化采集结果会变成 `role: "collect"`。
- `/api/agent/chat` 与 `/api/agent/chat/stream`：旧的回答精修/热榜分析接口。带 `questionId` 是回答精修，不带则走热榜分析。
- `/api/agent/tools`：只读列出 `ALL_TOOLS`。

SSE 使用 `app/api/sse_utils.py` 和前端 `frontend/src/lib/sse.ts`。新增流式事件时要同步后端事件名和前端 callbacks，保持错误事件可被 `onError` 消费。

## 前端架构约定

路由在 `frontend/src/app/App.tsx`：

- `/import`：链接导入
- `/collect`：主题采集
- `/hotlist`：热榜
- `/workbench`：工作台
- `/chat`：持久 Agent 对话
- `/settings`：配置管理

Workspace 数据流：

```text
workflow-api.ts          # API 纯函数
use-workspace.ts         # TanStack Query + mutations + 业务动作
workspace-store.ts       # Zustand 全局 workspace 状态
workspace-shell.tsx      # 页面和共享 workspace UI
```

`useWorkspace()` 不是完整 store。`saveState`、`statusMessage`、`topicDraft` 等只存在于 `useWorkspaceStore()`；需要这些字段的组件必须直接读 store。

API 包装在 `frontend/src/lib/api.ts`，业务 API 函数放在 `workflow-api.ts` 或 settings/workbench 对应 API 文件。不要在组件里直接写 `fetch`。

前端类型以 `frontend/src/types/workflow.ts` 为准。新增后端字段、SSE payload 或页面状态时，先更新类型，再更新 hook/store/UI。

## UI 与布局注意事项

项目已有 shadcn/Radix 风格基础组件和 Tailwind v4。新增 UI 优先复用 `frontend/src/components/ui/` 与现有页面模式。

全屏页面高度依赖这条 flex/min-h-0 链路，改布局时不要随手删：

```text
WorkspaceLayout: div.min-h-screen.flex.flex-col
  main.flex.flex-1.flex-col
    section.flex.flex-1.flex-col
      div.flex-1.min-h-0.grid / flex
        column.overflow-y-auto
```

独立滚动列必须有上游 `min-h-0`。否则会出现页面撑高、滚动失效或编辑区坍塌。

添加 shadcn/ui 组件：

```bash
cd frontend && bunx --bun shadcn@latest add <component>
```

如果 CLI 生成到字面路径 `frontend/@/components/ui/<component>.tsx`，手动移动到 `frontend/src/components/ui/<component>.tsx`。首次运行可能遇到 zod 版本冲突，重跑通常可恢复。

## 会话与输出文件

本地会话由 `app/services/session_service.py` 管理，前端通过 `/api/session/*` 读写。回答配图输出到 `generated-images/` 并由 FastAPI 挂载为 `/generated-images`。Agent checkpoint 位于 `output/agent_checkpoints.sqlite`。

不要把 `.env`、cookie、SQLite checkpoint、生成图片和输出结果当作源码改动提交，除非用户明确要求。

## 环境变量

先复制模板：

```bash
cp .env.example .env
```

常用变量：

- `OPENAI_API_KEY`：必填
- `OPENAI_BASE_URL`：默认来自 `app/config/settings.toml`，当前为智谱兼容地址
- `OPENAI_MODEL`：默认来自 `app/config/settings.toml`
- `ZHIHU_COOKIE_FILE`：知乎 web 采集 cookie 文件
- `ZHIHU_ACCESS_SECRET`：存在时 `source=auto` 可优先知乎 official collector
- `TEST_MODE`：测试模式下不追加 CTA
- `MAX_PUSH_COUNT`：采集上限，仍受 settings 中最大值限制

外部平台工具可能还有自己的 API key。新增密钥只放 `.env.example` 的占位说明，不写真实值。

## 测试与验证策略

优先使用已有测试文件定位验证：

- 回答生成/提示词：`tests/test_answer_service.py`、`tests/test_deepseek_content_mode_prompt.py`
- 会话 payload/持久化：`tests/test_models_session_payload.py`、`tests/test_session_service.py`
- Agent/LangGraph：`tests/test_agent_chat_node.py`、`tests/test_conversation_graph.py`
- 平台采集：`tests/test_zhihu_import.py`、`tests/test_xiaohongshu_collector.py`、`tests/test_playwright_fetcher.py`

有网络、真实 cookie、真实 LLM 依赖的路径应尽量用 mock 或小范围测试。不能跑完整验证时，在最终回复里明确说明未验证项和原因。

## 代码风格与维护约束

- 后端保持路由薄、服务/应用层承载业务逻辑、基础设施层封装外部系统。
- 前后端 API 响应保持 `{"ok": true, "data": ...}`；异常由后端统一包装为 `{"ok": false, "error": {"message": ...}}`。
- 不要引入新的全局状态库；workspace 用 Zustand + TanStack Query 的既有模式。
- 不要在组件中绕过 hook 直接调用后端业务 API，除非是在新增的 feature 专属 hook/API 层。
- 修改模型字段时同步 Pydantic alias、前端类型、序列化、测试样例。
- 保持生成内容、会话文件和缓存目录与源码分离。
