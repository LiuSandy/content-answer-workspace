# Feature: Agent Layer — 基于 LangGraph 的 AI 协作层

## 背景与问题

当前 AI 能力是孤立的一次性调用，每个场景单独一个接口，无法共享上下文，无法扩展。
随着场景增多，需要一个统一的 AI 协作层来承载所有 AI 交互。

## 技术选型：LangGraph

LangGraph 是基于状态机的 Agent 框架。核心概念：

- **State**：在所有节点间流动的共享数据结构（TypedDict）
- **Node**：接收 State、返回更新后 State 的普通 Python 函数
- **Edge**：节点之间的流转关系（固定边或条件边）
- **Graph**：由节点和边组成的完整工作流，`.compile()` 后可执行
- **Checkpointer**：自动持久化 State，支持跨请求的状态恢复

**与「LLM 调用工具」的区别**：LangGraph 是代码驱动的——**你的代码决定流程**，LLM 只在特定节点内负责语言生成，不决定下一步走哪里。

---

## 现有代码（不得破坏）

| 文件 | 现有功能 |
|------|---------|
| `app/infrastructure/llm/deepseek_client.py` | LLM 客户端，节点内直接调用 |
| `app/services/answer_service.py` | 回答生成/润色，节点内复用 |
| `app/services/hotlist_service.py` | 热榜获取，节点内复用 |
| `app/api/routes/workflow.py` | 现有路由，完全保留 |
| `app/application/workflow_service.py` | 工作流编排，完全保留 |

---

## 架构设计

### 整体结构

```
POST /api/agent/chat
        ↓
GraphRouter（根据请求选择 Graph）
    ├── question_id 存在  →  RefinementGraph（精修回答）
    └── question_id 为空  →  AnalysisGraph（热榜分析）
        ↓
LangGraph Graph.ainvoke(state, config)
        ↓
返回最终 AgentState
```

### 共享 State

所有 Graph 共用同一个 State 定义，节点只更新自己负责的字段：

```python
# app/application/agent/state.py
from typing import TypedDict

class AgentState(TypedDict):
    # ── 输入 ──────────────────────────────
    session_id: str
    question_id: str | None       # 有值 → 精修场景；None → 分析场景
    user_message: str

    # ── 节点间传递的工作数据 ───────────────
    current_answer: str | None    # fetch_answer 节点写入
    hotlist_items: list[dict] | None  # fetch_hotlist 节点写入

    # ── 输出 ──────────────────────────────
    reply: str                    # 返回给用户的文字
    answer_updated: bool          # 回答是否被修改
    updated_answer: str | None    # 修改后的回答全文
    operation_summary: str        # 本次操作的简短描述（用于日志）
```

---

## Graph 一：RefinementGraph（精修回答）

**流程**：固定三步，代码控制，LLM 只做语言改写

```
START → fetch_answer → apply_instruction → save_answer → END
                            ↑ LLM 在这里
```

### 节点实现

```python
# app/application/agent/nodes/fetch_answer.py
from ..state import AgentState
from ....services.session_service import get_answer_by_question_id

async def fetch_answer_node(state: AgentState) -> dict:
    """读取当前问题的最新回答内容"""
    answer = await get_answer_by_question_id(state["session_id"], state["question_id"])
    return {"current_answer": answer}
```

```python
# app/application/agent/nodes/apply_instruction.py
from ..state import AgentState
from ....infrastructure.llm.deepseek_client import DeepSeekAnswerGenerator

_generator = DeepSeekAnswerGenerator()

async def apply_instruction_node(state: AgentState) -> dict:
    """调用 LLM，按用户指令定向修改回答"""
    prompt = "\n".join([
        "请严格按照用户指令修改以下回答。",
        "只改动用户指定的部分，其余内容保持原样，不要自行发挥。",
        "",
        f"用户指令：{state['user_message']}",
        "",
        "当前回答：",
        state["current_answer"] or "",
    ])
    updated = await _generator.refine_answer(prompt)
    short_desc = state["user_message"][:30]
    return {
        "updated_answer": updated,
        "reply": "已按您的要求完成修改。",
        "answer_updated": True,
        "operation_summary": f"修改：{short_desc}",
    }
```

```python
# app/application/agent/nodes/save_answer.py
from ..state import AgentState
from ....services.session_service import update_answer_by_question_id

async def save_answer_node(state: AgentState) -> dict:
    """将修改后的回答持久化"""
    await update_answer_by_question_id(
        state["session_id"],
        state["question_id"],
        state["updated_answer"],
    )
    return {}
```

### Graph 构建

```python
# app/application/agent/graphs/refinement.py
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from ..state import AgentState
from ..nodes.fetch_answer import fetch_answer_node
from ..nodes.apply_instruction import apply_instruction_node
from ..nodes.save_answer import save_answer_node

def build_refinement_graph():
    graph = StateGraph(AgentState)

    graph.add_node("fetch_answer", fetch_answer_node)
    graph.add_node("apply_instruction", apply_instruction_node)
    graph.add_node("save_answer", save_answer_node)

    graph.add_edge(START, "fetch_answer")
    graph.add_edge("fetch_answer", "apply_instruction")
    graph.add_edge("apply_instruction", "save_answer")
    graph.add_edge("save_answer", END)

    return graph.compile(checkpointer=MemorySaver())
```

---

## Graph 二：AnalysisGraph（热榜分析）

**流程**：固定两步，代码控制，LLM 只做分析生成

```
START → fetch_hotlist → analyze → END
                           ↑ LLM 在这里
```

### 节点实现

```python
# app/application/agent/nodes/fetch_hotlist.py
from ..state import AgentState
from ....services.hotlist_service import fetch_hotlist

async def fetch_hotlist_node(state: AgentState) -> dict:
    """调用现有热榜服务取数据"""
    response = await fetch_hotlist(limit=30)
    items = [item.model_dump(by_alias=True) for item in response.items]
    return {"hotlist_items": items}
```

```python
# app/application/agent/nodes/analyze_hotlist.py
from ..state import AgentState
from ....infrastructure.llm.deepseek_client import DeepSeekAnswerGenerator

_generator = DeepSeekAnswerGenerator()

ANALYSIS_SYSTEM_PROMPT = """
你是内容策略分析师。分析知乎热榜数据，输出 JSON，结构如下：
{
  "topicDistribution": [{"field": "领域名", "count": N, "examples": ["标题1"]}],
  "contentOpportunities": [{"direction": "方向描述", "reason": "理由"}],
  "audienceMood": "整体情绪基调",
  "recommendations": [{"topic": "选题", "reason": "理由", "keywords": ["词1"]}]
}
只返回 JSON，不要其他说明。
""".strip()

async def analyze_hotlist_node(state: AgentState) -> dict:
    """调用 LLM 分析热榜数据"""
    items_text = "\n".join(
        f"{item['rank']}. {item['title']}（热度：{item['heat']}）\n   {item['summary']}"
        for item in (state["hotlist_items"] or [])
    )
    prompt = f"以下是当前知乎热榜 {len(state['hotlist_items'] or [])} 条内容：\n\n{items_text}"
    result = await _generator.analyze(ANALYSIS_SYSTEM_PROMPT, prompt)
    return {
        "reply": result,
        "answer_updated": False,
        "operation_summary": "热榜分析",
    }
```

### Graph 构建

```python
# app/application/agent/graphs/analysis.py
from langgraph.graph import StateGraph, START, END
from ..state import AgentState
from ..nodes.fetch_hotlist import fetch_hotlist_node
from ..nodes.analyze_hotlist import analyze_hotlist_node

def build_analysis_graph():
    graph = StateGraph(AgentState)

    graph.add_node("fetch_hotlist", fetch_hotlist_node)
    graph.add_node("analyze", analyze_hotlist_node)

    graph.add_edge(START, "fetch_hotlist")
    graph.add_edge("fetch_hotlist", "analyze")
    graph.add_edge("analyze", END)

    return graph.compile()
```

---

## Router（图路由器）

```python
# app/application/agent/router.py
from langgraph.graph.graph import CompiledGraph
from .graphs.refinement import build_refinement_graph
from .graphs.analysis import build_analysis_graph

class GraphRouter:
    def __init__(self):
        self._refinement: CompiledGraph = build_refinement_graph()
        self._analysis: CompiledGraph = build_analysis_graph()

    def route(self, question_id: str | None) -> CompiledGraph:
        if question_id:
            return self._refinement
        return self._analysis

_router = GraphRouter()

def get_router() -> GraphRouter:
    return _router
```

---

## API 接口

### `POST /api/agent/chat`

**Request**
```json
{
  "sessionId": "sess_abc123",
  "questionId": "q_001",        // 精修场景填写；分析场景省略
  "message": "把第二段改得更口语一点"
}
```

**Response**
```json
{
  "reply": "已按您的要求完成修改。",
  "answerUpdated": true,
  "updatedAnswer": "修改后的完整回答...",
  "operationSummary": "修改：把第二段改得更口语一点"
}
```

### 接口实现

```python
# app/api/routes/agent.py
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from ...application.agent.router import get_router

router = APIRouter(prefix="/api/agent", tags=["agent"])

class AgentChatPayload(BaseModel):
    session_id: str = Field(alias="sessionId")
    question_id: str | None = Field(default=None, alias="questionId")
    message: str

    model_config = {"populate_by_name": True}

@router.post("/chat")
async def agent_chat(payload: AgentChatPayload) -> JSONResponse:
    graph = get_router().route(payload.question_id)
    config = {"configurable": {"thread_id": payload.session_id}}
    state = await graph.ainvoke(
        {
            "session_id": payload.session_id,
            "question_id": payload.question_id,
            "user_message": payload.message,
            "current_answer": None,
            "hotlist_items": None,
            "reply": "",
            "answer_updated": False,
            "updated_answer": None,
            "operation_summary": "",
        },
        config=config,
    )
    return JSONResponse({
        "ok": True,
        "data": {
            "reply": state["reply"],
            "answerUpdated": state["answer_updated"],
            "updatedAnswer": state["updated_answer"],
            "operationSummary": state["operation_summary"],
        },
    })
```

---

## Checkpointer 如何解决 Token 膨胀

LangGraph 的 `MemorySaver` 以 `thread_id`（= `session_id`）为键持久化 State。

每次调用：
- 只传入本轮新数据（`user_message`）
- State 中的 `current_answer` 由 `fetch_answer` 节点**实时读取**，不从历史携带
- 不存储对话历史，不累积 token

| 对比项 | 朴素多轮对话 | LangGraph Checkpointer |
|--------|------------|----------------------|
| 第 5 轮 token | ~12500 | ~2500（固定） |
| 历史存储位置 | LLM context | State（你的服务器） |
| 历史内容 | 全量对话文本 | 仅 operation_summary |

---

## 文件结构

```
app/
└── application/
    └── agent/
        ├── __init__.py
        ├── state.py
        ├── router.py
        ├── graphs/
        │   ├── __init__.py
        │   ├── refinement.py
        │   └── analysis.py
        └── nodes/
            ├── __init__.py
            ├── fetch_answer.py
            ├── apply_instruction.py
            ├── save_answer.py
            ├── fetch_hotlist.py
            └── analyze_hotlist.py
app/
└── api/
    └── routes/
        └── agent.py
```

---

## 未来扩展点

新增场景只需两步：
1. 在 `nodes/` 下新增节点函数
2. 在 `graphs/` 下新建 Graph，注册到 `GraphRouter`

若未来需要 LLM 自主决定流程（如「帮我规划本周内容」），可在 Graph 中加入**条件边**，由 LLM 输出决定下一个节点，无需修改整体架构。

---

## 依赖

- 新增 Python 包：`langgraph`
- 无前置 Feature 依赖，可独立实现
- `feature-answer-refinement-chat` 和 `feature-hotlist-analysis` 均依赖本 Feature
