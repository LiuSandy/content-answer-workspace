# Plan: Agent Layer 实施方案（LangGraph）

## 设计原则

| 原则 | 体现 |
|------|------|
| 单一职责 | 每个 Node 只做一件事（读 / 改 / 写 / 分析），Graph 只做流程编排 |
| 开闭原则 | 新增场景 = 新增 Node + 新建 Graph，已有 Node 和 Graph 不修改 |
| 依赖倒置 | Node 依赖 Service 接口（Port），不直接调用 Service 实现 |
| 高内聚 | 同一 Graph 内的 Node 共同完成一个完整用例，不跨图复用节点状态 |
| 低耦合 | Node 之间只通过 `AgentState` 传递数据，互不感知对方 |

---

## 架构分层

```
API Layer（FastAPI）
    └── AgentRouter（路由层）
            ├── RefinementGraph  ←─ LangGraph CompiledGraph
            │     ├── FetchAnswerNode
            │     ├── ApplyInstructionNode   ← LLM 调用在此
            │     └── SaveAnswerNode
            └── AnalysisGraph    ←─ LangGraph CompiledGraph
                  ├── FetchHotlistNode
                  └── AnalyzeHotlistNode     ← LLM 调用在此

Node 层依赖
    FetchAnswerNode    → SessionServicePort
    ApplyInstruction   → LLMClientPort
    SaveAnswerNode     → SessionServicePort
    FetchHotlistNode   → HotlistServicePort
    AnalyzeHotlist     → LLMClientPort
```

**核心设计决策**：Node 只调用 Port（接口），不直接调用具体 Service 实现。这样 Node 单独可测（注入 Mock），未来替换 Service 不改 Node。

---

## 接口定义（Ports）

```python
# app/application/agent/ports.py
from typing import Protocol
from ...models import QuestionItem
from ...services.hotlist_service import HotlistResponse

class SessionServicePort(Protocol):
    """Node 依赖的 Session 数据访问接口"""

    async def get_answer(self, session_id: str, question_id: str) -> str:
        """读取指定问题的当前回答，问题不存在时返回空字符串"""
        ...

    async def update_answer(
        self, session_id: str, question_id: str, content: str
    ) -> None:
        """覆盖写入指定问题的回答"""
        ...

class LLMClientPort(Protocol):
    """Node 依赖的 LLM 调用接口"""

    async def refine(self, instruction: str, current_answer: str) -> str:
        """按指令定向修改回答，返回修改后全文"""
        ...

    async def analyze(self, system_prompt: str, user_prompt: str) -> str:
        """调用 LLM 分析，返回原始文本（通常为 JSON 字符串）"""
        ...

class HotlistServicePort(Protocol):
    """Node 依赖的热榜数据接口"""

    async def fetch(self, limit: int) -> list[dict]:
        """获取热榜，返回序列化后的 dict 列表"""
        ...
```

---

## AgentState

```python
# app/application/agent/state.py
from typing import TypedDict

class AgentState(TypedDict):
    # ── 输入（请求带入）──────────────────────────
    session_id: str
    question_id: str | None
    user_message: str

    # ── 工作数据（节点间传递，请求结束后丢弃）────
    current_answer: str | None
    hotlist_items: list[dict] | None

    # ── 输出（最终返回给 API 层）────────────────
    reply: str
    answer_updated: bool
    updated_answer: str | None
    operation_summary: str
```

**State 字段分组说明**：
- 输入字段由 API 层在调用时写入，Node 只读
- 工作数据字段在节点间传递，不持久化到 Checkpointer
- 输出字段由最后一个有意义的 Node 写入

---

## Node 详细设计

每个 Node 是一个**无副作用的纯异步函数**（除 `SaveAnswerNode` 外），接收完整 State，只返回本节点负责的字段变更。

### FetchAnswerNode

```python
# app/application/agent/nodes/fetch_answer.py
from ..state import AgentState
from ..ports import SessionServicePort

async def fetch_answer_node(
    state: AgentState,
    *,
    session_svc: SessionServicePort,
) -> dict:
    """
    职责：从 Session 读取当前回答，写入 current_answer。
    不做：任何业务判断，不修改回答内容。
    """
    answer = await session_svc.get_answer(
        state["session_id"], state["question_id"]
    )
    return {"current_answer": answer}
```

### ApplyInstructionNode

```python
# app/application/agent/nodes/apply_instruction.py
from ..state import AgentState
from ..ports import LLMClientPort

async def apply_instruction_node(
    state: AgentState,
    *,
    llm: LLMClientPort,
) -> dict:
    """
    职责：调用 LLM 按用户指令定向修改回答。
    约束：只改用户指定部分，不自行添加内容。
    不做：持久化、路由判断。
    """
    updated = await llm.refine(
        instruction=state["user_message"],
        current_answer=state["current_answer"] or "",
    )
    short = state["user_message"][:30]
    return {
        "updated_answer": updated,
        "reply": "已按您的要求完成修改。",
        "answer_updated": True,
        "operation_summary": f"修改：{short}",
    }
```

### SaveAnswerNode

```python
# app/application/agent/nodes/save_answer.py
from ..state import AgentState
from ..ports import SessionServicePort

async def save_answer_node(
    state: AgentState,
    *,
    session_svc: SessionServicePort,
) -> dict:
    """
    职责：将修改后的回答持久化。
    唯一有副作用的节点，副作用范围明确且单一。
    """
    await session_svc.update_answer(
        state["session_id"],
        state["question_id"],
        state["updated_answer"] or "",
    )
    return {}
```

### FetchHotlistNode

```python
# app/application/agent/nodes/fetch_hotlist.py
from ..state import AgentState
from ..ports import HotlistServicePort

async def fetch_hotlist_node(
    state: AgentState,
    *,
    hotlist_svc: HotlistServicePort,
) -> dict:
    """
    职责：获取热榜数据，写入 hotlist_items。
    复用现有 HotlistService，不重复实现采集逻辑。
    """
    items = await hotlist_svc.fetch(limit=30)
    return {"hotlist_items": items}
```

### AnalyzeHotlistNode

```python
# app/application/agent/nodes/analyze_hotlist.py
from ..state import AgentState
from ..ports import LLMClientPort

_SYSTEM_PROMPT = """
你是内容策略分析师。分析知乎热榜数据，严格按以下 JSON 格式输出：
{
  "topicDistribution": [{"field": "领域", "count": N, "examples": ["标题"]}],
  "contentOpportunities": [{"direction": "方向", "reason": "理由"}],
  "audienceMood": "情绪基调",
  "recommendations": [{"topic": "选题", "reason": "理由", "keywords": ["词"]}]
}
只返回 JSON，不要其他说明。
""".strip()

async def analyze_hotlist_node(
    state: AgentState,
    *,
    llm: LLMClientPort,
) -> dict:
    """
    职责：调用 LLM 分析热榜，返回结构化 JSON 字符串。
    不做：JSON 解析（解析在前端进行，便于降级处理）。
    """
    items = state["hotlist_items"] or []
    lines = [
        f"{item['rank']}. {item['title']}（热度：{item['heat']}）\n   {item.get('summary', '')}"
        for item in items
    ]
    user_prompt = f"以下是当前知乎热榜 {len(items)} 条内容：\n\n" + "\n".join(lines)
    result = await llm.analyze(_SYSTEM_PROMPT, user_prompt)
    return {
        "reply": result,
        "answer_updated": False,
        "operation_summary": "热榜分析",
    }
```

---

## Port 适配器（连接现有 Service）

Node 依赖 Port 接口，需要提供适配现有 Service 的实现：

```python
# app/application/agent/adapters.py

from .ports import SessionServicePort, LLMClientPort, HotlistServicePort
from ...services.hotlist_service import fetch_hotlist
from ...infrastructure.llm.deepseek_client import DeepSeekAnswerGenerator

class DeepSeekLLMAdapter:
    """将 DeepSeekAnswerGenerator 适配为 LLMClientPort"""

    def __init__(self) -> None:
        self._gen = DeepSeekAnswerGenerator()

    async def refine(self, instruction: str, current_answer: str) -> str:
        prompt = "\n".join([
            "请严格按照用户指令修改以下回答。",
            "只改动用户指定的部分，其余内容保持原样，不要自行发挥。",
            "",
            f"用户指令：{instruction}",
            "",
            "当前回答：",
            current_answer,
        ])
        return await self._gen.call_raw(
            system="你是专业的内容编辑助手。",
            user=prompt,
        )

    async def analyze(self, system_prompt: str, user_prompt: str) -> str:
        return await self._gen.call_raw(system=system_prompt, user=user_prompt)


class HotlistServiceAdapter:
    """将 hotlist_service 适配为 HotlistServicePort"""

    async def fetch(self, limit: int) -> list[dict]:
        response = await fetch_hotlist(limit=limit)
        return [item.model_dump(by_alias=True) for item in response.items]
```

---

## Graph 构建（工厂函数）

节点依赖通过 `functools.partial` 注入，Graph 本身只关心流程结构：

```python
# app/application/agent/graphs/refinement.py
from functools import partial
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from ..state import AgentState
from ..nodes.fetch_answer import fetch_answer_node
from ..nodes.apply_instruction import apply_instruction_node
from ..nodes.save_answer import save_answer_node
from ..adapters import DeepSeekLLMAdapter
from ..session_adapter import InMemorySessionAdapter   # 见下文

def build_refinement_graph():
    session_svc = InMemorySessionAdapter()
    llm = DeepSeekLLMAdapter()

    graph = StateGraph(AgentState)
    graph.add_node("fetch_answer",       partial(fetch_answer_node,       session_svc=session_svc))
    graph.add_node("apply_instruction",  partial(apply_instruction_node,  llm=llm))
    graph.add_node("save_answer",        partial(save_answer_node,        session_svc=session_svc))

    graph.add_edge(START,              "fetch_answer")
    graph.add_edge("fetch_answer",     "apply_instruction")
    graph.add_edge("apply_instruction","save_answer")
    graph.add_edge("save_answer",       END)

    return graph.compile(checkpointer=MemorySaver())
```

```python
# app/application/agent/graphs/analysis.py
from functools import partial
from langgraph.graph import StateGraph, START, END
from ..state import AgentState
from ..nodes.fetch_hotlist import fetch_hotlist_node
from ..nodes.analyze_hotlist import analyze_hotlist_node
from ..adapters import DeepSeekLLMAdapter, HotlistServiceAdapter

def build_analysis_graph():
    hotlist_svc = HotlistServiceAdapter()
    llm = DeepSeekLLMAdapter()

    graph = StateGraph(AgentState)
    graph.add_node("fetch_hotlist", partial(fetch_hotlist_node, hotlist_svc=hotlist_svc))
    graph.add_node("analyze",       partial(analyze_hotlist_node, llm=llm))

    graph.add_edge(START,          "fetch_hotlist")
    graph.add_edge("fetch_hotlist","analyze")
    graph.add_edge("analyze",       END)

    return graph.compile()
```

---

## GraphRouter（注册表模式）

```python
# app/application/agent/router.py
from langgraph.graph.graph import CompiledGraph
from .graphs.refinement import build_refinement_graph
from .graphs.analysis import build_analysis_graph

class GraphRouter:
    """
    职责：根据请求特征选择对应的 Graph。
    使用注册表模式（Registry），新增场景只需注册新 Graph，不修改路由逻辑。
    """

    def __init__(self) -> None:
        # Graph 在进程启动时编译一次，后续复用
        self._graphs: dict[str, CompiledGraph] = {
            "refinement": build_refinement_graph(),
            "analysis": build_analysis_graph(),
        }

    def route(self, question_id: str | None) -> CompiledGraph:
        key = "refinement" if question_id else "analysis"
        return self._graphs[key]

    def register(self, key: str, graph: CompiledGraph) -> None:
        """扩展点：运行时注册新 Graph，不重启进程"""
        self._graphs[key] = graph

# 单例，进程内共享（Graph 编译开销较大）
_router = GraphRouter()

def get_router() -> GraphRouter:
    return _router
```

---

## DeepSeekAnswerGenerator 新增方法

现有类需补充一个通用 LLM 调用方法，供 Adapter 使用，**不影响现有方法**：

```python
# app/infrastructure/llm/deepseek_client.py 新增

async def call_raw(self, system: str, user: str) -> str:
    """
    通用 LLM 调用，不附加任何业务提示词。
    供 Agent 层的 Adapter 使用，与现有 generate_answer / polish_answer 并列存在。
    """
    client = self.get_client()
    model = get_required_env("DEEPSEEK_MODEL")
    completion = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    content = completion.choices[0].message.content if completion.choices else None
    if isinstance(content, str):
        return content.strip()
    raise ValueError("LLM returned empty content")
```

---

## 文件结构

```
app/application/agent/
├── __init__.py
├── state.py                   ← AgentState TypedDict
├── ports.py                   ← SessionServicePort, LLMClientPort, HotlistServicePort
├── adapters.py                ← DeepSeekLLMAdapter, HotlistServiceAdapter
├── session_adapter.py         ← InMemorySessionAdapter（读写 session store）
├── router.py                  ← GraphRouter（注册表模式）
├── nodes/
│   ├── __init__.py
│   ├── fetch_answer.py
│   ├── apply_instruction.py
│   ├── save_answer.py
│   ├── fetch_hotlist.py
│   └── analyze_hotlist.py
└── graphs/
    ├── __init__.py
    ├── refinement.py           ← build_refinement_graph()
    └── analysis.py             ← build_analysis_graph()

app/api/routes/
└── agent.py                   ← POST /api/agent/chat
```

---

## 实施阶段

### Phase 1：接口与 State（无 IO 依赖）
- [ ] `state.py`：定义 `AgentState`
- [ ] `ports.py`：定义三个 Port 接口
- [ ] `DeepSeekAnswerGenerator.call_raw()`：新增方法，不改已有方法

### Phase 2：Node 实现（依赖 Port，可 Mock 测试）
- [ ] `nodes/fetch_answer.py`
- [ ] `nodes/apply_instruction.py`
- [ ] `nodes/save_answer.py`
- [ ] `nodes/fetch_hotlist.py`
- [ ] `nodes/analyze_hotlist.py`

### Phase 3：Adapter 实现（连接现有 Service）
- [ ] `adapters.py`：`DeepSeekLLMAdapter`、`HotlistServiceAdapter`
- [ ] `session_adapter.py`：`InMemorySessionAdapter`（读写现有 session store）

### Phase 4：Graph 构建与路由
- [ ] `graphs/refinement.py`：`build_refinement_graph()`
- [ ] `graphs/analysis.py`：`build_analysis_graph()`
- [ ] `router.py`：`GraphRouter`

### Phase 5：API 接入
- [ ] `api/routes/agent.py`：`POST /api/agent/chat`
- [ ] `server.py`：注册 agent router

### Phase 6：测试
- [ ] 每个 Node 的单元测试（Mock Port，验证 state 变化）
- [ ] RefinementGraph 集成测试（Mock Session + Mock LLM）
- [ ] AnalysisGraph 集成测试（Mock Hotlist + Mock LLM）
- [ ] API 端到端测试

---

## 测试策略

Node 的测试方法：注入 Mock Port，验证输入 State → 输出 dict 的正确性：

```python
async def test_apply_instruction_node():
    class MockLLM:
        async def refine(self, instruction, current_answer):
            return f"改写后：{current_answer}"
        async def analyze(self, system, user):
            return "{}"

    state: AgentState = {
        "session_id": "s1", "question_id": "q1",
        "user_message": "改得更简短",
        "current_answer": "原始回答",
        "hotlist_items": None,
        "reply": "", "answer_updated": False,
        "updated_answer": None, "operation_summary": "",
    }
    result = await apply_instruction_node(state, llm=MockLLM())
    assert result["answer_updated"] is True
    assert "改写后" in result["updated_answer"]
```

---

## 扩展指南：新增场景

以「内容规划」场景为例（未来需求）：

1. 新增 Node：`nodes/plan_content.py`
2. 新建 Graph：`graphs/planning.py`，串联 `fetch_hotlist → fetch_questions → plan_content`
3. 在 `GraphRouter.__init__` 中注册：`self._graphs["planning"] = build_planning_graph()`
4. 更新 `router.route()` 的路由判断

**已有 Node 和 Graph 零修改。**
