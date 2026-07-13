# 本地内容采集与回答工作台 (Chat-first Agent Architecture)

本项目是一个本地内容采集与回答工作台。项目已全面重构为**基于 Clean Architecture/DDD 思想的 Chat-first Agent 架构**：

- **后端**：Python 3.11+ / FastAPI / SQLAlchemy 2.0 / Alembic / PostgreSQL 16 / LangGraph / DeepSeek LLM
- **前端**：React 19 / TypeScript / Zustand / TanStack Query / Tiptap 核心富文本编辑器 / Bun

---

## 📂 项目目录结构

### 1. 后端结构 (`app/`)
```text
app/
├── domain/                    # 领域层（纯 Protocols 接口与 Pydantic DTO，不依赖具体实现）
│   ├── ports.py               # 核心协议定义 (ContentSource, LLMProvider, TaskDispatcher)
│   └── dto.py                 # 数据传输契约 (SourceItemDTO, ChatResponsePayload, SelectionDTO 等)
├── persistence/               # 基础设施：持久化存储层 (SQLAlchemy 2.0)
│   ├── session.py             # 异步数据库 session 连接池
│   └── models/                # 9 张业务主外键关联表 (chats, messages, source_items, documents 等)
├── prompts/                   # 基础设施：提示词加载器
│   ├── registry.py            # PromptRegistry 单例（Jinja2 变量渲染与 includes 共享片段组装）
│   └── schemas.py             # Prompt YAML Schema 校验
├── infrastructure/            # 基础设施：外部服务适配器实现
│   ├── llm/                   # DeepSeek LLM Provider 实现与 Registry 动态路由
│   ├── sources/               # 多平台内容源适配器与 Registry (zhihu, xiaohongshu, universal)
│   └── zhihu/                 # 历史遗留知乎官方 API 客户端
├── workflows/                 # 业务应用层：核心优化流
│   ├── answer_generation.py   # AI 流式生成回答工作流
│   ├── inline_refinement.py   # AI 选区局部流式润色工作流
│   └── full_rewrite.py        # AI 全文流式重写工作流
├── application/               # 业务应用层：核心服务与 Agent
│   ├── chat_service.py        # 对话创建、消息持久化、去重内容关联服务
│   ├── document_service.py    # 乐观并发锁 (Optimistic Lock) 文档编辑更新服务
│   ├── version_service.py     # 历史版本手动打卡与恢复服务
│   └── agent/                 # LangGraph 对话 Agent (preprocess, route_intent, chat, tool_nodes)
├── api/                       # REST API 接口路由层
│   └── routes/                # 挂载 /api/chats, /api/documents, /api/config, /api/settings 等端点
├── errors.py                  # 业务系统统一异常层 (AppError, DocumentConflictError 等)
└── server.py                  # FastAPI 主程序入口，挂载静态文件托管与全局 exception_handler
```

### 2. 外部模板结构 (`prompts/`)
所有的 AI 提示词脱离 Python 硬编码，全部外置到根目录的 YAML 格式配置文件中：
- `prompts/model_profiles.yml`：配置默认、创新、推理等不同规格的模型参数。
- `prompts/shared/`：存放如 `style_rules.yml` 共享写作风格片段。
- `prompts/chat/`：意图路由分类器与系统初始引导词。
- `prompts/writing/` / `prompts/refinement/`：回答生成、润色和重写的模板。

### 3. 前端结构 (`frontend/`)
```text
frontend/src/
├── app/                       # 核心入口与 React Router 路由规则
├── features/
│   ├── chat/                  # 对话工作区：三栏布局组件
│   │   ├── chat-sidebar.tsx   # 左栏：会话管理（新增/删除/切换）
│   │   ├── chat-panel.tsx     # 中栏：流式交互、状态提示与结构化采集卡片
│   │   └── editor-panel.tsx   # 右栏：Tiptap 编辑器、选区优化指令、手动打卡与版本快照恢复
│   ├── hotlist/               # 热点分析：知乎实时热点 dashboard，一键用热点创建对话
│   └── settings/              # 配置设置：LLM 凭据、采集设置与主题管理
├── store/
│   └── chat-store.ts          # Zustand 轻量级当前会话状态仓
├── lib/
│   ├── api.ts                 # fetch API 包装器 (GET/POST/PUT/DELETE)
│   └── sse.ts                 # 异步 POST 的通用 SSE 流式解析协议客户端
└── components/ui/             # 规范化的 shadcn/ui 组件库
```

---

## ⚙️ 环境变量配置

请在项目根目录复制并填写 `.env` 环境变量：
```bash
cp .env.example .env
```
主要环境变量说明：
```bash
# 数据库连接
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/content_answer

# DeepSeek LLM 配置
DEEPSEEK_API_KEY=your-api-key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat

# 爬虫凭证配置 (可选，使用小红书或知乎 Web 模式时提供)
ZHIHU_COOKIE_FILE=.secrets/zhihu.cookie
XIAOHONGSHU_COOKIE_FILE=.secrets/xiaohongshu.cookie
```

---

## 🚀 快速启动说明

### 1. 数据库准备
确保本地安装并运行 Docker，在根目录下启动 PostgreSQL 16 数据库容器：
```bash
docker-compose up -d
```
首次运行或数据库更新时，执行 Alembic 自动迁移数据库 Schema 到最新版：
```bash
uv run alembic upgrade head
```

### 2. 后端服务启动
在根目录下运行：
```bash
uv sync
uv run python -m app.server
```
后端服务默认监听：`http://127.0.0.1:3000`。

### 3. 前端服务启动
在项目 `frontend/` 目录下运行：
```bash
bun install
bun run dev
```
前端开发服务默认监听：`http://127.0.0.1:5173`。

---

## 🔄 核心运行机制

```mermaid
graph TD
    A[用户发送消息] --> B[preprocess 节点: 提取 URL]
    B --> C[route_intent 节点: 提取意图]
    C -->|chat| D[chat 节点: 普通 LLM 对话流]
    C -->|parse_url| E[parse_url 节点: 通过 SourceRegistry 路由适配器解析内容]
    C -->|collect| F[collect 节点: 通过 SourceRegistry 路由并开始多平台抓取]
    E --> G[normalize_and_persist 节点: 采集帖去重写入 DB]
    F --> G
    G --> H[build_response 节点: 拼装结构化 DTO 并渲染 SSE 推送前端]
```

### 乐观并发锁机制
前端编辑器修改数据时会自动执行 `PUT /api/documents/{id}` 保存内容，当多人同时编辑或后台 AI 异步更新内容时，会通过 `expectedLockVersion` 机制校验版本。若不一致将触发 `409 DocumentConflictError` 终止覆写，确保内容不会被相互覆盖。