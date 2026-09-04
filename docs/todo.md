# TODO

## 调研 AI 回复耗时统计

- [ ] 调研并重新设计 AI 回复耗时的起止时间、统计口径和持久化方式；涉及 `app/modules/conversation/`、`app/shared/agent/runtime.py`、`frontend/src/features/chat/`。

## 接入 LangSmith Agent Trace

- [ ] 配置 LangSmith 环境变量并接入 Agent 全链路 Trace，覆盖 HTTP 请求、LangGraph 节点、LLM 调用、RAG 检索、工具调用和最终结果；为自定义 RAG、采集器和 Memory 服务增加必要的手动埋点，并补充 `run_id`、`chat_id`、模型/Prompt 版本、Token、延迟、错误和成本等元数据，同时完成敏感信息脱敏验证。

## 使用 Tokenizers 优化 Token 计算

- [ ] 使用 Hugging Face `tokenizers` 包替换 RAG 中基于字符比例的 `estimate_tokens()`，让分块和 `token_count` 使用模型对应的 Tokenizer；由于 `qwen3.7-text-embedding` 尚未公开官方 `tokenizer.json`，接入前需要用多语种样本与服务端返回的 `usage.prompt_tokens` 做一致性验证，不能直接假设公开的 `Qwen3-Embedding` Tokenizer 完全兼容。

## 使用 Celery 优化 Worker

- [ ] 评估并使用 Celery 改造当前基于 `asyncio` 的 Worker 调度实现，引入 Redis 或 RabbitMQ 作为消息代理，实现任务持久化、独立 Worker 进程、横向扩容、自动重试、定时调度与优雅停机；改造时保留统一的任务提交接口，并处理现有异步 `TaskHandler` 与 Celery 同步任务模型之间的适配以及任务幂等性问题。

## 重新设计 Writer 工作流

- [ ] 重新梳理 Writer Graph 的工作流边界：当前 `retrieve_memory` 完成记忆召回后直接按 `operation` 分流，Compose 主线与直接文档操作分支的职责、命名和收尾机制不够清晰，需要重新设计节点职责、路由和持久化边界。

## 接入知乎开放平台能力

- [ ] 知乎知识库管理；涉及 `docs/zhihu/知识库列表API.md`、`docs/zhihu/知识库内容列表 API.md`、`app/modules/knowledge/`、`frontend/src/features/knowledge/`。
- [ ] 基于知乎知识库的 RAG 问答与写作辅助；涉及 `docs/zhihu/知识库检索 API.md`、`app/modules/knowledge/`、`app/modules/conversation/`、`app/modules/writing/`、`frontend/src/features/chat/`。
