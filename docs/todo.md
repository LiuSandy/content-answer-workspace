# TODO

## 联动 Prompt Model Profile 与 LLM Provider

- [ ] 让 `PromptRegistry` 解析并返回 Model Profile 中的 `provider`，使 `RenderedPrompt` 同时携带 `provider` 和 `model`。
- [ ] LLM 调用时根据 `rendered.provider` 从 `llm_provider_registry` 选择 Provider，避免始终使用 `get_default()`。
- [ ] 校验 Profile 中的模型名称、结构化输出方式与 Provider 能力匹配。
- [ ] 增加多 Provider 配置和错误配置的回归测试。

当前风险：`PromptRegistry` 会从 Model Profile 取得 `model`，但忽略 `provider`；调用方则独立通过 `LLM_PROVIDER` 选择默认 Provider。切换供应商后，可能把某个供应商的模型名称发送给另一个 Provider。
