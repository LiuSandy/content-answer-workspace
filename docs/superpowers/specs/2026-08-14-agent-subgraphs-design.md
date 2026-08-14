# Agent Subgraphs Design

## Goal

将现有多 Agent 协作流程改造成真正的 LangGraph 父图与独立子图，同时保持当前 API、返回类型、错误隔离和业务结果不变。Memory Agent 暂时保留现有普通异步函数实现。

## Scope

本次修改覆盖：

- 将 Orchestrator 改造成可编译的父 `StateGraph`。
- 将 Researcher、Writer、Reviewer 改造成可编译的独立子图。
- 保留 Chat Agent 现有 Graph，只调整多 Agent 调用边界。
- 保留 Memory Agent 当前执行函数，由 Orchestrator 将其作为普通 Node 调用。
- 保留 `run_multi_agent_plan(goal, workspace_id)` 的公开签名和 `MultiAgentState` 返回类型。

本次不覆盖：

- 不重写 Memory Agent。
- 不改变 Prompt 内容、LLM 参数、搜索算法、审核算法或数据库结构。
- 不引入新的外部依赖。
- 不改变 HTTP API 响应结构。

## Architecture

采用“顶层共享协作 State + Agent 私有 State + 子图边界适配”结构。

```text
Chat Graph
    ↓ multi_agent node
Orchestrator Graph
    ├── generate_plan
    ├── assign_tasks
    ├── Researcher Subgraph
    ├── Writer Subgraph
    ├── Reviewer Subgraph
    ├── Memory legacy node
    └── finalize
```

Orchestrator Graph 负责控制执行顺序和失败路由。每个子图通过与父图同名的共享字段读取输入、写回输出，同时使用只存在于自身 State 中的私有字段保存中间数据。

## State Model

### Public compatibility state

保留现有 `MultiAgentState` dataclass 作为公开输入输出模型，以避免破坏 API、测试和直接调用方。

### Parent graph state

新增内部 `MultiAgentGraphState`，包含：

- `goal`
- `workspace_id`
- `plan`
- `sub_agent_states`
- `research_report`
- `draft`
- `final_output`
- `quality_score`
- `interrupted`
- `interrupt_reason`

### Researcher private state

`ResearcherState` 在共享字段之外包含：

- `research_tasks`
- `task_results`
- `research_error`

### Writer private state

`WriterState` 在共享字段之外包含：

- `writing_prompt`
- `writing_error`
- `draft_metadata`

### Reviewer private state

`ReviewerState` 在共享字段之外包含：

- `review_context`
- `review_outcome`
- `review_error`

所有私有字段只在对应子图内部使用，不进入 Orchestrator 的长期共享状态。

## Graphs

### Researcher

```text
START
  ↓
prepare_tasks
  ├── no tasks → build_report
  └── has tasks → execute_tasks
                         ↓
                    build_report
                         ↓
                        END
```

- `prepare_tasks`：筛选 `search` 和 `analyze` 子任务并初始化 Agent 状态。
- `execute_tasks`：复用现有 `execute_task_plan()`，保持拓扑分层和并行行为不变。
- `build_report`：合并结果并更新 `research_report` 与 `sub_agent_states`。
- 任一步失败时记录失败状态，并输出已有的部分结果。

### Writer

```text
START → prepare_prompt → generate_draft → finalize_draft → END
```

- `prepare_prompt`：按现有格式生成写作 Prompt。
- `generate_draft`：复用现有 LLM 调用。
- `finalize_draft`：更新草稿及 Agent 状态。
- 失败时保持 `draft` 为空，并记录隔离错误。

现有回答精修 Graph `build_refinement_graph()` 保持不变。

### Reviewer

```text
START → prepare_review → run_review
                            ├── success → finalize_review → END
                            └── failure → preserve_draft → END
```

- `prepare_review`：建立现有 `ReviewContext`。
- `run_review`：复用 `run_creation_review()` 及当前 rewrite 回调。
- `finalize_review`：写入终稿、质量分和审核状态。
- `preserve_draft`：保持当前失败降级行为，将原始草稿作为终稿。

### Orchestrator

```text
START → generate_plan → assign_tasks
                           ├── failed → END
                           └── success
                                  ↓
                         Researcher Subgraph
                                  ↓
                           Writer Subgraph
                                  ↓
                          Reviewer Subgraph
                                  ↓
                         Memory legacy node
                                  ↓
                              finalize
                                  ↓
                                 END
```

- 父图直接挂载已编译子图，使嵌套执行可被 LangGraph 事件流识别。
- Memory 保持现有 `memory_agent_node()`，仅作为普通父图 Node 使用。
- `run_multi_agent_plan()` 负责把公开参数转换为父图输入，并把执行结果转换回 `MultiAgentState`。

## Error Handling

- Orchestrator 计划生成失败时沿用现有异常传播行为。
- Orchestrator 分配失败时立即结束流程。
- Researcher、Writer、Reviewer、Memory 的失败只更新各自 `SubAgentState`，不抛出到父图。
- Reviewer 失败时必须保留当前草稿作为 `final_output`。
- 子图节点不得吞掉 `asyncio.CancelledError`。
- 不新增自动重试次数，避免改变 LLM 和工具调用数量。

## Compatibility

以下行为必须保持：

- `run_multi_agent_plan(goal, workspace_id="default")` 签名不变。
- 返回对象继续是 `MultiAgentState`。
- `sub_agent_states` 继续包含 `orchestrator`、`research`、`writing`、`review`、`memory`。
- Researcher 继续通过 `execute_task_plan()` 并行执行同层任务。
- Writer Prompt 和 LLM 调用内容不变。
- Reviewer 审核循环和失败降级不变。
- Multi-Agent API JSON 字段不变。
- Chat Graph 的意图路由和 SSE 行为不变。

## Testing

采用测试驱动方式逐图实施：

1. 添加测试，确认每个目标 Agent 的 `graph.py` 返回已编译 LangGraph。
2. 添加测试，确认 Researcher 子图节点顺序、无任务分支和失败隔离。
3. 添加测试，确认 Writer 子图生成结果及失败状态。
4. 添加测试，确认 Reviewer 成功路径与保留草稿降级路径。
5. 添加测试，确认 Orchestrator 嵌套调用四个阶段并保持返回契约。
6. 运行现有 Multi-Agent、Chat、HITL、Prompt 和结构化输出回归测试。

## Acceptance Criteria

- Orchestrator、Researcher、Writer、Reviewer 均存在真实的 `StateGraph` 构建与 `compile()`。
- 每个目标 Agent 至少有两个具有独立职责的 Node，并通过 Edge 连接。
- Orchestrator 使用编译后的子图，而不是直接顺序 `await` 子 Agent 函数。
- Memory 实现保持不变。
- Agent 私有字段不会写入父图共享 State。
- 现有 API 和多 Agent 功能测试继续通过。
