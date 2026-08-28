# Agent 清单与节点分析

> 基于代码实测（2026-08-16），所有结论附 `文件:行号`。`app/agents/_shared/` 是公共工具与
> 运行支持（工具注册、SSRF 安全、SSE 封装、共享 prompt），**不是 Agent**，不在统计内。

## 0. 总览

**共 6 个 Agent**（5 个编译 LangGraph 图 + 1 个 legacy 节点函数）：

| Agent | 类型 | 节点数 | 职责一句话 | 入口 |
|---|---|---|---|---|
| chat | 顶层图（带 checkpointer） | **15** | 用户对话主入口：意图路由、RAG、工具 ReAct、HITL、平台采集、URL 解析 | `build_chat_agent_graph`（chat/graph.py:79） |
| orchestrator | 父图（无 checkpointer） | **7**（含 3 个子图节点） | 多 Agent 协作指挥：拆解计划、分配任务、串联子图、收尾 | `orchestrator_graph` 单例（orchestrator/graph.py:43） |
| researcher | 子图 | **3** | 资料研究：筛选搜索/分析任务并拓扑执行，汇总研究报告 | `researcher_graph` 单例（researcher/graph.py:35） |
| writer | 子图（+1 个精修图） | **3**（主图）+ 3（精修图，遗留未接线） | 依据研究报告生成 Markdown 草稿 | `writer_graph` 单例（writer/graph.py:30） |
| reviewer | 子图 | **4** | 审核-重写循环，产出终稿与质量分；失败保留草稿 | `reviewer_graph` 单例（reviewer/graph.py:38） |
| memory | legacy 节点（非图） | **1** | 从目标与产出中提取长期记忆 | `memory_agent_node`（memory/graph.py:10） |

挂载关系：

```text
chat 图（server lifespan 编译，SQLite checkpointer）
  ├─ "task_plan"     ← 复用 orchestrator/nodes/task_plan.py 的节点函数（graph.py:19,90）
  ├─ "multi_agent"   ← 复用 orchestrator/nodes/execute.py 的节点函数（graph.py:20,91）
  │                      └─ run_multi_agent_plan → orchestrator_graph.ainvoke
  └─ orchestrator 父图（graph.py:21-27）
       ├─ researcher ← researcher_graph（已编译子图直接作节点）
       ├─ writer     ← writer_graph
       ├─ reviewer   ← reviewer_graph
       └─ memory     ← run_memory_node（适配层）→ memory_agent_node（实际实现）
```

## 1. Chat Agent（对话主图，15 节点）

**职责**：整个产品的对话主入口。预处理用户消息、检索长期记忆、三层意图识别，然后按意图
分流到 RAG 对话、URL 解析、任务计划、多 Agent 协作或平台采集；支持 ReAct 工具环路和
HITL 人工选择中断。是**唯一带 checkpointer 的图**（graph.py:150），承载分支续跑与
interrupt 恢复。

| 节点 | 实现位置 | 职责 |
|---|---|---|
| preprocess | nodes/preprocess.py | 确定性提取 URL、清空上轮意图/工具/HITL 状态，建立请求上下文 |
| memory_retriever | nodes/memory_retriever.py | 检索相关长期记忆写入 applied_memories；失败不阻断主链路 |
| route_intent | nodes/route_intent.py | 三层意图识别（规则→LLM→校验兜底），产出 intent/知识模式/平台/查询词 |
| knowledge_decision | nodes/knowledge_decision.py（图内包装 graph.py:42） | 判定是否触发 RAG 检索（off/寒暄/过短消息跳过） |
| retrieve_knowledge | nodes/retrieve_knowledge.py | 执行混合 RAG 检索，写入 retrieval_result/trace_id/降级原因 |
| strict_refusal | graph.py:65-68（图内定义） | 严格模式下证据不足时直接拒答 |
| task_plan | orchestrator/nodes/task_plan.py（借用） | 生成并执行 TaskPlan，落库供前端卡片查询，产出即终态 |
| multi_agent | orchestrator/nodes/execute.py（借用） | 调 run_multi_agent_plan 启动 5 子 Agent 协作，产出即终态 |
| platform_collect | nodes/platform_collect.py | 确定性调用平台专用搜索工具，生成终态回复并保存采集结果 |
| hitl_decision | nodes/hitl_decision.py | 检测工具结果 conflict，有则 `interrupt()` 生成 choice_request 暂停 |
| chat | nodes/chat.py | 对话 LLM 节点：注入 RAG/记忆/分支摘要，预算内裁剪消息生成回复 |
| chat_tools | `ToolNode(ALL_TOOLS)`（graph.py:96） | prebuilt 工具执行节点（计算器/datetime/平台工具，按配置开关注册） |
| parse_url | nodes/tool_nodes.py | 经 SourceRegistry 按 URL 路由平台适配器，解析为 SourceItem 列表 |
| normalize_and_persist | nodes/tool_nodes.py | 采集项标准化入库，回填数据库主键到 DTO |
| build_response | nodes/tool_nodes.py | 构造稳定 SSE 载荷（source_list / error） |

**路由**（4 处 conditional_edges）：意图路由（graph.py:104-114）→ RAG 决策（:116-120）→
检索结果路由（:122-126，严格模式无证据走 strict_refusal）→ chat 后工具环路
（:138-142，`chat → chat_tools → hitl_decision → chat`）。

```text
START → preprocess → memory_retriever → route_intent
  ├─ parse_url   → normalize_and_persist → build_response → END
  ├─ task_plan / multi_agent / platform_collect → END
  └─ knowledge_decision ─┬─ chat ⇄ chat_tools → hitl_decision（冲突时 interrupt）
                         └─ retrieve_knowledge ─┬─ chat
                                                └─ strict_refusal → END（严格模式）
```

## 2. Orchestrator Agent（协作父图，7 节点）

**职责**：多 Agent 协作指挥。把协作目标拆解为 TaskPlan、分配任务，然后依次驱动
researcher→writer→reviewer 子图与 memory 节点，收尾输出。**无 checkpointer**（graph.py:40），
从 chat 图进入时 `ainvoke` 不带 thread_id（orchestrator/nodes/execute.py→graph.py:60），
中断即丢。plan 生成失败会沿现有异常传播；子 Agent 失败只更新各自 SubAgentState。

| 节点 | 实现位置 | 职责 |
|---|---|---|
| generate_plan | nodes/generate_plan.py | 调 planning_service 把目标拆解为 TaskPlan 写入 state |
| assign_tasks | nodes/assign_tasks.py | 校验计划非空，记录分配结果到 sub_agent_states |
| researcher | researcher_graph 子图（graph.py:23） | 见 §3 |
| writer | writer_graph 子图（graph.py:24） | 见 §4 |
| reviewer | reviewer_graph 子图（graph.py:25） | 见 §5 |
| memory | nodes/run_memory.py | 状态适配层：父图 state → 旧 MultiAgentState，转发 memory_agent_node |
| finalize | nodes/finalize.py | 显式结束流程，保留共享 sub_agent_states 输出 |

**路由**：`assign_tasks →(orchestrator failed ? END : researcher)`（graph.py:30-34），
其余为线性链 `researcher → writer → reviewer → memory → finalize → END`。

## 3. Researcher Agent（研究子图，3 节点）

**职责**：从计划中筛选 search/analyze 任务，按拓扑分层并行执行（复用
`planning_service.execute_task_plan`），汇总为研究报告。失败只记录部分结果。

| 节点 | 实现位置 | 职责 |
|---|---|---|
| prepare_tasks | nodes/prepare_tasks.py | 筛选 search/analyze 任务，初始化 research 子状态；无任务直通 build_report |
| execute_tasks | nodes/execute_tasks.py | 组装部分计划，按拓扑分层并行执行搜索与分析任务 |
| build_report | nodes/build_report.py | 汇总任务结果为 research_report，标记成败与并发统计 |

```text
START → prepare_tasks ─┬（有任务）→ execute_tasks → build_report → END
                       └（无任务）──────────────→ build_report
```

## 4. Writer Agent（写作子图，3 节点 + 遗留精修图 3 节点）

**职责**：依据目标+研究报告构造 Prompt 生成 Markdown 初稿；失败时草稿置空并隔离错误。

**主图**（`writer_graph` 单例）：

| 节点 | 实现位置 | 职责 |
|---|---|---|
| prepare_prompt | nodes/prepare_prompt.py | 构造写作 Prompt，初始化 writing 子状态 |
| generate_draft | nodes/generate_draft.py | 调 planner LLM 生成初稿；异常不抛出子图 |
| finalize_draft | nodes/finalize_draft.py | 按成败收尾 writing 状态（done/failed + 元数据） |

**精修图** `build_refinement_graph(session_svc)`（graph.py:48-62，`functools.partial`
注入请求级依赖）：`fetch_answer`（读当前回答）→ `apply_instruction`（LLM 按指令修改）→
`save_answer`（持久化）。**注意：app/ 内无调用方，属遗留保留代码**——线上精修/重写走的是
`nodes/answer_generation.py / inline_refinement.py / full_rewrite.py` 这三个**非图节点的
async generator 薄适配器**（委托 `writing_service.run_writer_stream`，SSE 流式输出）。

## 5. Reviewer Agent（审阅子图，4 节点）

**职责**：驱动审核-重写循环（`creation_review_service.run_creation_review`），产出终稿与
质量分；审核失败时保留原草稿降级。

| 节点 | 实现位置 | 职责 |
|---|---|---|
| prepare_review | nodes/prepare_review.py | 建立 ReviewContext（问题/目标字数/迭代轮次），初始化 review 状态 |
| run_review | nodes/run_review.py | 驱动评审-重写循环，取 outcome 或记录 review_error |
| finalize_review | nodes/finalize_review.py | 成功路径：写回 final_output + quality_score，标记 done |
| preserve_draft | nodes/preserve_draft.py | 失败路径：原草稿充当 final_output，隔离错误标记 failed |

```text
START → prepare_review → run_review ─┬（无错误）→ finalize_review → END
                                     └（有错误）→ preserve_draft  → END
```

## 6. Memory Agent（legacy 节点，1 节点）

**职责**：从本次协作的目标与最终产出中提取长期记忆（`memory_service.extract_memories`），
记录保存数量。**不是 StateGraph**——子图化重构时明确暂缓
（`docs/superpowers/specs/2026-08-14-agent-subgraphs-design.md` Scope），由 orchestrator
父图以普通节点方式调用。实际实现在 `memory/graph.py:10` `memory_agent_node`；orchestrator
挂载的 `run_memory_node`（orchestrator/nodes/run_memory.py）只是状态适配层。

## 7. 附注

- 各图均有「兼容单节点包装」（如 `research_agent_node`、`writing_agent_node`、
  `review_agent_node`、`orchestrator_node`），内部 ainvoke 已编译子图，供旧调用方使用。
- Agent 私有 State 字段（researcher 的 task_results、writer 的 draft_metadata、reviewer
  的 review_outcome 等）不写入父图共享状态（各 state.py；subgraphs 设计文档约定）。
- 设计文档：`docs/superpowers/specs/2026-08-14-agent-subgraphs-design.md`；
  机制细节（checkpointer/SSE/HITL/乐观锁/消息树）见 `docs/core-mechanisms.md`。
