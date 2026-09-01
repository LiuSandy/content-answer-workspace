# TODO

## 接入 LangSmith Agent Trace

- [ ] 配置 LangSmith 环境变量并接入 Agent 全链路 Trace，覆盖 HTTP 请求、LangGraph 节点、LLM 调用、RAG 检索、工具调用和最终结果；为自定义 RAG、采集器和 Memory 服务增加必要的手动埋点，并补充 `run_id`、`chat_id`、模型/Prompt 版本、Token、延迟、错误和成本等元数据，同时完成敏感信息脱敏验证。

## 使用 Tokenizers 优化 Token 计算

- [ ] 使用 Hugging Face `tokenizers` 包替换 RAG 中基于字符比例的 `estimate_tokens()`，让分块和 `token_count` 使用模型对应的 Tokenizer；由于 `qwen3.7-text-embedding` 尚未公开官方 `tokenizer.json`，接入前需要用多语种样本与服务端返回的 `usage.prompt_tokens` 做一致性验证，不能直接假设公开的 `Qwen3-Embedding` Tokenizer 完全兼容。

## 优化 Markdown 读取性能

- [ ] 优化 Markdown 的读取与 SHA-256 计算流程，避免大文件同时完整驻留在内存并额外创建 UTF-8 字节副本；评估采用分块读取或流式处理。

## 清理 RAG 入库任务记录

- [ ] 为 `knowledge_ingestion_jobs` 和 `knowledge_ingestion_pages` 增加数据清理策略：定时清理已完成/失败且超过保留期限的记录，或在任务完成后自动清理，避免任务历史数据无限增长。

## 使用 Celery 优化 Worker

- [ ] 评估并使用 Celery 改造当前基于 `asyncio` 的 Worker 调度实现，引入 Redis 或 RabbitMQ 作为消息代理，实现任务持久化、独立 Worker 进程、横向扩容、自动重试、定时调度与优雅停机；改造时保留统一的任务提交接口，并处理现有异步 `TaskHandler` 与 Celery 同步任务模型之间的适配以及任务幂等性问题。

## 联动 Prompt Model Profile 与 LLM Provider

- [x] 让 `PromptRegistry` 解析并返回 Model Profile 中的 `provider`，使 `RenderedPrompt` 同时携带 `provider` 和 `model`。
- [x] LLM 调用时根据 `rendered.provider` 从 `llm_provider_registry` 选择 Provider，避免始终使用 `get_default()`。
- [x] 校验 Profile 中的模型名称、结构化输出方式与 Provider 能力匹配。
- [x] 增加多 Provider 配置和错误配置的回归测试。

完成状态：`RenderedPrompt` 已携带 `provider`、`model` 和结构化输出方式；`LLMResolver` 统一完成 Provider/模型选择，Gateway 会拒绝 Profile 声明但 Provider 不支持的结构化输出方式。

## 重新设计 LLM 与业务服务架构

- [x] 重新评估并设计项目的 LLM 调用分层，解除通用 `LLMServiceAdapter` 对业务相关 `AnswerGenerationService` 的反向依赖。
- [x] 将通用文本生成、结构化输出、流式调用等能力下沉到独立的 LLM Gateway/Completion Service 或明确的 Port，避免回答生成、记忆抽取、摘要、质检等业务模块互相依赖。
- [x] 明确 `LLMProvider`、Provider Registry、通用 LLM 服务与各业务服务的职责边界，统一依赖注入、Provider 选择、模型配置和测试替身方案。
- [x] 重新梳理 Adapter、Service、Port、Registry/Factory 的使用方式，形成清晰的依赖方向后再实施代码重构。
- [x] 记忆抽取必须改为结构化输出：使用明确的 Pydantic Schema 调用 `generate_structured()`，在通过 JSON 解析、Schema 校验和业务字段校验前不得写入 `user_memories`；校验失败需按统一策略重试或放弃本次保存，并记录失败原因。
- [x] 调整结构化输出方案：评估并使用 `from langchain_openai import ChatOpenAI` 构建统一模型客户端，结合 `with_structured_output()` 重新设计 Provider 适配、Schema 校验、降级策略和错误审计流程。

## 重新设计 Writer 工作流

- [ ] 重新梳理 Writer Graph 的工作流边界：当前 `retrieve_memory` 完成记忆召回后直接按 `operation` 分流，Compose 主线与直接文档操作分支的职责、命名和收尾机制不够清晰，需要重新设计节点职责、路由和持久化边界。

## 接入知乎开放平台能力

- [x] 知乎内容搜索；使用知乎搜索 API，并清理返回链接中的 `utm_medium`、`utm_source` 跟踪参数；涉及 `docs/zhihu/知乎搜索API.md`、`app/plugins/tools/builtin/zhihu_tool.py`、`app/plugins/sources/`、`frontend/src/features/chat/`。
- [ ] 全网资料搜索；涉及 `docs/zhihu/全网搜索API.md`、`app/plugins/tools/`、`app/modules/conversation/`、`frontend/src/features/chat/`。
- [ ] 知乎知识库管理；涉及 `docs/zhihu/知识库列表API.md`、`docs/zhihu/知识库内容列表 API.md`、`app/modules/knowledge/`、`frontend/src/features/knowledge/`。
- [ ] 基于知乎知识库的 RAG 问答与写作辅助；涉及 `docs/zhihu/知识库检索 API.md`、`app/modules/knowledge/`、`app/modules/conversation/`、`app/modules/writing/`、`frontend/src/features/chat/`。
