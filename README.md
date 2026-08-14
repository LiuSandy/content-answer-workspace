# 本地内容采集与回答工作台 (Chat-first Agent Architecture)

本项目是一个本地内容采集与回答工作台。项目已全面重构为**基于 Clean Architecture/DDD 思想的 Chat-first Agent 架构**：

- **后端**：Python 3.11+ / FastAPI / SQLAlchemy 2.0 / Alembic / PostgreSQL 16 / LangGraph / DeepSeek LLM
- **前端**：React 19 / TypeScript / Zustand / TanStack Query / Tiptap 核心富文本编辑器 / Bun

---

## 📂 项目目录结构

### 1. 后端结构 (`app/`)
```text
app/
├── server.py                  # FastAPI 主程序入口
├── graph.py                   # 多 Agent 系统顶层 Graph 入口
├── state.py                   # 系统共享 State
├── context.py                 # Graph 运行时上下文与输入组装
├── api/                       # API 路由、Schema 与流式响应
├── agents/                    # 独立 Agent：chat、orchestrator、researcher、writer、reviewer、memory
│   └── _shared/               # Agent 公共工具、Prompt 与运行支持，不是独立 Agent
├── services/                  # 业务逻辑与用例服务
├── infrastructure/           # 数据库、采集器、文件、可观测性及外部能力
│   └── llm/clients/           # 大模型底层客户端，与其他基础设施客户端隔离
├── contracts/                # 跨层 DTO、Port 与业务错误契约
├── prompts/                   # Prompt 加载、校验与渲染基础设施
├── config/                    # 运行配置及默认配置文件
└── evaluation/                # 评测数据集、指标与运行器
```

### 2. Agent Prompt 结构 (`app/agents/`)
每个 Agent 的 YAML Prompt 放在自己的 `prompts/` 目录；公共 Prompt 和模型配置放在
`app/agents/_shared/prompts/`。

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
后端服务默认监听：`http://127.0.0.1:8000`。

### 3. 前端服务启动
在项目 `frontend/` 目录下运行：
```bash
bun install
bun run dev
```
前端开发服务默认监听：`http://127.0.0.1:5173`。

### 4. 后端日志

后端日志同时输出到控制台和项目根目录下的日期目录：

```text
logs/YYYY-MM-DD/info.log
logs/YYYY-MM-DD/warning.log
logs/YYYY-MM-DD/error.log
logs/YYYY-MM-DD/critical.log
```

控制台使用紧凑文本格式，只显示非空的 request、run、job 等上下文；日志文件内部为一行一条完整 JSON。默认 `LOG_LEVEL=INFO`；如需调试日志，在 `.env` 中设置：

```dotenv
LOG_LEVEL=DEBUG
```

此时会额外生成 `logs/YYYY-MM-DD/debug.log`。每个级别文件默认达到 100MB 后独立轮转，历史日期目录默认保留 14 天。HTTP 响应的 `X-Request-ID` 可以用于关联同一次请求的日志；对话、生成和 PDF 识别日志还会携带对应的 run ID 或 job ID。

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

## 长期记忆与私有资料检索

长期记忆和知识库共用 Embedding 配置，数据库向量维度固定为 1536：

```bash
EMBEDDING_API_KEY=
EMBEDDING_BASE_URL=https://api.openai.com/v1
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_DIMENSIONS=1536
```

候选证据使用独立的批量 Cross-Encoder `/rerank` 服务，不再调用 Chat Completions：

```bash
RERANKER_API_KEY=
RERANKER_BASE_URL=
RERANKER_MODEL=BAAI/bge-reranker-v2-m3
```

普通模式在 Embedding 或 Reranker 不可用时会明确标记降级；严格模式无法验证证据阈值时直接拒答。

检查数据库迁移和索引：

```bash
uv run alembic upgrade head
uv run alembic current
docker compose exec -T postgres psql -U dev -d content_workspace \
  -c "SELECT indexname,indexdef FROM pg_indexes WHERE tablename='user_memories';"
```

运行确定性检索质量基线：

```bash
uv run python -m app.evaluation.run_retrieval_eval \
  --dataset docs/evaluations/private-knowledge-rag.jsonl \
  --backend deterministic
```

设置 `RUN_MEMORY_DB_TESTS=1` 可运行真实 PostgreSQL cosine Top-K、全新数据库迁移和 HNSW 查询计划测试。

聊天中的人工选择使用 LangGraph 原生 `interrupt()` 暂停。恢复必须依赖持久化 checkpointer、原分支 `thread_id` 和 `Command(resume=...)`；不得把选择作为新的用户问题重新执行工具链。
