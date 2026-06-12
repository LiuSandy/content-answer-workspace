# 知乎开发者平台能力整理

本文根据知乎公开开发者文档整理，主要来源如下：

- [知乎开发者文档首页](https://developer.zhihu.com/docs)
- [知乎开发者文档索引接口](https://developer.zhihu.com/console/api/v2/docs)

## 平台基本信息

知乎开发者平台当前公开了 4 类能力：

1. 鉴权说明
2. 公开 API
3. Skill
4. MCP 工具

平台的统一鉴权方式是 `Authorization: Bearer <access_secret>`，并要求请求携带秒级 Unix 时间戳 `X-Request-Timestamp`。官方文档说明 `Access Secret` 可在个人中心获取。

## 官方支持的能力

### 1. 公开 API

- `知乎搜索 API`
  - 用于站内内容搜索。
  - 返回问题、回答、文章等结果。
  - 支持 `Query` 和 `Count`，其中 `Count` 最大为 10。

- `全网搜索 API`
  - 用于全网内容搜索。
  - 支持 `Query`、`Count`、`Filter`、`SearchDB`。
  - `Filter` 可按 `host`、`publish_time` 做筛选。

- `知乎热榜 API`
  - 用于获取当前知乎热榜。
  - 返回标题、链接、缩略图、摘要。
  - `Limit` 最大为 30。

- `直答 API`
  - 用于通用问答、内容解释、内容总结。
  - 支持 `zhida-fast-1p5`、`zhida-thinking-1p5`、`zhida-agent`。
  - 支持流式和非流式输出。

### 2. Skill

- `知乎搜索 Skill`
  - 面向 Agent 的知乎站内搜索能力。
  - 适合补充知乎内容、检索高相关讨论、获取站内观点与经验。

- `全网搜索 Skill`
  - 面向 Agent 的全网搜索能力。
  - 适合补充站外公开信息、扩展参考来源。

- `知乎热榜 Skill`
  - 面向 Agent 的热榜获取能力。
  - 适合热点追踪、趋势发现、内容推荐。

- `直答 Skill`
  - 面向 Agent 的问答能力。
  - 提供简化 `query` 输入和对话式 `messages` 输入。

### 3. MCP

- `知乎搜索 MCP`
- `全网搜索 MCP`
- `知乎热榜 MCP`
- `直答 MCP`

这四个能力都可通过 MCP 接入支持 MCP 的 Agent、助手或工作流系统。

## 相关说明

对照你们当前项目的“现有功能 vs 官方可替代能力”，我已经单独整理到另一份文档中：

- [知乎功能对照表](./zhihu-official-vs-project.md)
