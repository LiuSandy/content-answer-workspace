# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

本地可视化内容工作台：从知乎等平台按主题采集问题，通过 LLM 批量生成 AI 回答，在前端编辑并保存。

技术栈：
- 后端：Python 3.11+、FastAPI、uv 包管理
- 前端：React + TypeScript、Vite、Tailwind CSS、Zustand、TanStack Query、bun

## 常用命令

### 后端

```bash
# 安装依赖
uv sync

# 启动后端（默认 http://127.0.0.1:3000）
uv run python -m app.server

# 运行所有测试
uv run pytest tests/

# 运行单个测试文件
uv run pytest tests/test_answer_service.py -v
```

### 前端（在 frontend/ 目录执行）

```bash
cd frontend
bun install
bun run dev      # 开发服务器 http://127.0.0.1:5173
bun run build    # 构建到 frontend/dist（由 FastAPI 托管）
bun run typecheck  # TypeScript 类型检查（tsc --noEmit）
```

前端 dev 模式下 `/api/*` 已通过 Vite 代理转发到后端 `http://127.0.0.1:3000`。

## 架构

### 后端分层

```
app/
├── server.py              # FastAPI 入口，挂载路由，托管 frontend/dist
├── models.py              # 全局 Pydantic 模型（Topic, QuestionItem, WorkflowConfig…）
├── core/
│   ├── config.py          # 环境变量读取与 WorkflowConfig 构建
│   └── prompts.py         # 默认提示词与主题预设
├── application/
│   └── workflow_service.py  # 用例编排：collect / generate_one / generate_many / run
├── api/routes/
│   ├── workflow.py        # POST /api/workflow/collect、/generate、/generate-one
│   ├── session.py         # GET/POST /api/session/*
│   └── config.py          # GET /api/config
├── services/
│   ├── zhihu_service.py   # 知乎搜索与问题详情抓取
│   ├── answer_service.py  # LLM 回答生成（含配图）
│   ├── session_service.py # 本地 JSON 会话读写
│   └── topic_expansion_service.py  # LLM 扩展主题关键词
└── infrastructure/
    ├── collectors/factory.py         # CollectorFactory（按 platform 实例化）
    ├── collectors/zhihu_collector.py # 知乎采集器实现
    └── llm/deepseek_client.py        # OpenAI-compatible LLM 客户端
```

`WorkflowService`（`application/`）是核心编排层，负责：串联采集器 → 主题扩展 → 去重截断 → 回答生成，并向 API 层屏蔽平台差异。

### 前端结构

```
frontend/src/
├── app/
│   ├── App.tsx             # 根组件
│   └── providers.tsx       # QueryClientProvider 等全局 Provider
├── features/workspace/
│   ├── workspace-shell.tsx # 三栏工作台 UI 主体
│   ├── use-workspace.ts    # 业务逻辑 Hook（封装 API 调用与状态同步）
│   ├── workflow-api.ts     # 所有后端 API 调用函数
│   └── defaults.ts         # 默认配置值
├── store/
│   └── workspace-store.ts  # Zustand 全局状态（topics、questions、UI 状态等）
├── types/
│   └── workflow.ts         # TypeScript 类型定义（与后端 Pydantic 模型对应）
├── components/ui/          # shadcn/ui 基础组件
└── lib/
    ├── api.ts              # fetch 工具函数
    └── utils.ts            # cn() 等工具
```

前端状态流：`use-workspace.ts` 持有所有 TanStack Query mutation，通过 `workflow-api.ts` 调用后端，结果写入 `workspace-store.ts`（Zustand）；`workspace-shell.tsx` 只读取 store 渲染 UI。

### Pydantic 字段别名约定

后端模型使用 `alias="camelCase"`（如 `answer_style` ↔ `answerStyle`），并设置 `populate_by_name=True`。序列化时对外统一用 `model_dump(by_alias=True)`，前端传参也使用 camelCase。

## 环境变量

复制模板后补齐以下必填项：

```bash
cp .env.example .env
```

| 变量 | 说明 |
|------|------|
| `OPENAI_API_KEY` | 必填，LLM API 密钥 |
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
