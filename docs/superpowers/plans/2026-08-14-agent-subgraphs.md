# Agent Subgraphs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert Orchestrator, Researcher, Writer, and Reviewer into compiled LangGraph workflows while preserving all public behavior and leaving Memory unchanged.

**Architecture:** Keep `MultiAgentState` as the public compatibility dataclass. Introduce an internal parent `MultiAgentGraphState` and private TypedDict extensions for each subgraph; shared keys flow through compiled subgraphs while private keys remain internal. The Orchestrator parent graph mounts compiled Researcher, Writer, and Reviewer subgraphs and invokes the unchanged Memory function through an adapter node.

**Tech Stack:** Python 3.11+, LangGraph, pytest, pytest-asyncio, Pydantic-compatible DTOs.

## Global Constraints

- Preserve `run_multi_agent_plan(goal, workspace_id="default") -> MultiAgentState`.
- Preserve current API response fields and existing LLM/tool call behavior.
- Preserve partial failure isolation and Reviewer fallback to the original draft.
- Do not change Memory Agent implementation.
- Do not add dependencies or database migrations.
- Write a failing test before each production change.

---

### Task 1: Define shared and private graph state contracts

**Files:**
- Modify: `app/agents/orchestrator/state.py`
- Modify: `app/agents/researcher/state.py`
- Modify: `app/agents/writer/state.py`
- Modify: `app/agents/reviewer/state.py`
- Test: `tests/test_multi_agent_graph.py`

**Interfaces:**
- Consumes: Existing `TaskPlan`, `SubAgentState`, and public `MultiAgentState`.
- Produces: `MultiAgentGraphState`, `ResearcherState`, `WriterState`, and `ReviewerState` TypedDict schemas.

- [ ] **Step 1: Write the failing state-isolation test**

```python
def test_agent_private_state_keys_are_not_parent_state_keys():
    assert "research_tasks" in ResearcherState.__annotations__
    assert "writing_prompt" in WriterState.__annotations__
    assert "review_context" in ReviewerState.__annotations__
    assert "research_tasks" not in MultiAgentGraphState.__annotations__
    assert "writing_prompt" not in MultiAgentGraphState.__annotations__
    assert "review_context" not in MultiAgentGraphState.__annotations__
```

- [ ] **Step 2: Run the state test and verify RED**

Run: `uv run pytest tests/test_multi_agent_graph.py::test_agent_private_state_keys_are_not_parent_state_keys -v`

Expected: FAIL because `MultiAgentGraphState` and private TypedDict fields do not exist.

- [ ] **Step 3: Implement the state schemas**

Define `MultiAgentGraphState(TypedDict, total=False)` with the approved shared fields. Define each private state as a TypedDict extending the shared schema and containing only that Agent's transient fields. Keep the existing dataclasses unchanged.

- [ ] **Step 4: Run the state test and verify GREEN**

Run: `uv run pytest tests/test_multi_agent_graph.py::test_agent_private_state_keys_are_not_parent_state_keys -v`

Expected: PASS.

### Task 2: Build the Researcher subgraph

**Files:**
- Create: `app/agents/researcher/nodes/prepare_tasks.py`
- Create: `app/agents/researcher/nodes/execute_tasks.py`
- Create: `app/agents/researcher/nodes/build_report.py`
- Modify: `app/agents/researcher/nodes/__init__.py`
- Modify: `app/agents/researcher/graph.py`
- Test: `tests/test_multi_agent_graph.py`

**Interfaces:**
- Consumes: `ResearcherState`, `execute_task_plan(TaskPlan)`, and `topological_order(TaskPlan)`.
- Produces: `build_researcher_graph()`, compiled `researcher_graph`, and compatibility wrapper `research_agent_node(MultiAgentState)`.

- [ ] **Step 1: Write failing graph and behavior tests**

```python
def test_researcher_is_compiled_graph():
    assert set(researcher_graph.get_graph().nodes) >= {
        "prepare_tasks", "execute_tasks", "build_report"
    }

@pytest.mark.asyncio
async def test_researcher_graph_preserves_parallel_results(monkeypatch):
    monkeypatch.setattr(
        "app.agents.researcher.nodes.execute_tasks.execute_task_plan",
        AsyncMock(return_value={"s1": "one", "s2": "two"}),
    )
    result = await researcher_graph.ainvoke({
        "plan": parallel_plan,
        "sub_agent_states": {},
    })
    assert result["research_report"] == "## s1\none\n\n## s2\ntwo"
    assert result["sub_agent_states"]["research"].status == "done"
```

- [ ] **Step 2: Run Researcher tests and verify RED**

Run: `uv run pytest tests/test_multi_agent_graph.py -k researcher -v`

Expected: FAIL because the compiled graph and Node modules do not exist.

- [ ] **Step 3: Implement Researcher Nodes and Graph**

Use `StateGraph(ResearcherState)`. Add `prepare_tasks`, conditional routing for empty/non-empty tasks, `execute_tasks`, and `build_report`; connect all terminal paths to `END`. Keep `execute_task_plan()` as the only task execution mechanism so concurrency and call counts remain unchanged.

- [ ] **Step 4: Preserve the compatibility wrapper**

Make `research_agent_node(state: MultiAgentState)` invoke `researcher_graph.ainvoke(...)`, copy only shared outputs back into the dataclass, and return the same dictionary keys as before.

- [ ] **Step 5: Run Researcher tests and verify GREEN**

Run: `uv run pytest tests/test_multi_agent_graph.py -k 'researcher or research_agent' -v`

Expected: PASS.

### Task 3: Build the Writer subgraph

**Files:**
- Create: `app/agents/writer/nodes/prepare_prompt.py`
- Create: `app/agents/writer/nodes/generate_draft.py`
- Create: `app/agents/writer/nodes/finalize_draft.py`
- Modify: `app/agents/writer/nodes/__init__.py`
- Modify: `app/agents/writer/graph.py`
- Test: `tests/test_multi_agent_graph.py`

**Interfaces:**
- Consumes: `WriterState`, `_get_planner_llm()`, parent `plan` and `research_report`.
- Produces: `build_writer_graph()`, compiled `writer_graph`, and compatibility wrapper `writing_agent_node(MultiAgentState)`.

- [ ] **Step 1: Write failing Writer graph tests**

```python
def test_writer_is_compiled_graph():
    assert set(writer_graph.get_graph().nodes) >= {
        "prepare_prompt", "generate_draft", "finalize_draft"
    }

@pytest.mark.asyncio
async def test_writer_graph_preserves_prompt_and_output(monkeypatch):
    fake_llm = MagicMock()
    fake_llm.analyze = AsyncMock(return_value="draft")
    monkeypatch.setattr(
        "app.agents.writer.nodes.generate_draft._get_planner_llm",
        lambda: fake_llm,
    )
    result = await writer_graph.ainvoke({
        "plan": _mock_plan(),
        "research_report": "research",
        "sub_agent_states": {},
    })
    assert result["draft"] == "draft"
    assert result["sub_agent_states"]["writing"].status == "done"
```

- [ ] **Step 2: Run Writer tests and verify RED**

Run: `uv run pytest tests/test_multi_agent_graph.py -k writer -v`

Expected: FAIL because `writer_graph` and its new Nodes do not exist.

- [ ] **Step 3: Implement Writer Nodes and Graph**

Move the existing prompt construction unchanged into `prepare_prompt_node`; call the same adapter in `generate_draft_node`; set status and metadata in `finalize_draft_node`. Route generation failures to finalization without raising them to the parent.

- [ ] **Step 4: Preserve refinement and compatibility APIs**

Keep `build_refinement_graph()` unchanged. Implement `writing_agent_node(MultiAgentState)` as an adapter around `writer_graph.ainvoke()` and preserve its existing result dictionary.

- [ ] **Step 5: Run Writer tests and verify GREEN**

Run: `uv run pytest tests/test_multi_agent_graph.py -k 'writer or writing_agent' -v`

Expected: PASS.

### Task 4: Build the Reviewer subgraph

**Files:**
- Create: `app/agents/reviewer/nodes/prepare_review.py`
- Create: `app/agents/reviewer/nodes/run_review.py`
- Create: `app/agents/reviewer/nodes/finalize_review.py`
- Create: `app/agents/reviewer/nodes/preserve_draft.py`
- Modify: `app/agents/reviewer/nodes/__init__.py`
- Modify: `app/agents/reviewer/graph.py`
- Test: `tests/test_multi_agent_graph.py`

**Interfaces:**
- Consumes: `ReviewerState`, `run_creation_review()`, `evaluate_content()`, and `DeepSeekLLMAdapter.refine()`.
- Produces: `build_reviewer_graph()`, compiled `reviewer_graph`, and compatibility wrapper `review_agent_node(MultiAgentState)`.

- [ ] **Step 1: Write failing Reviewer graph tests**

```python
def test_reviewer_is_compiled_graph():
    assert set(reviewer_graph.get_graph().nodes) >= {
        "prepare_review", "run_review", "finalize_review", "preserve_draft"
    }

@pytest.mark.asyncio
async def test_reviewer_graph_preserves_draft_on_failure(monkeypatch):
    monkeypatch.setattr(
        "app.agents.reviewer.nodes.run_review.evaluate_content",
        AsyncMock(side_effect=RuntimeError("review failed")),
    )
    result = await reviewer_graph.ainvoke({
        "plan": _mock_plan(),
        "draft": "original",
        "sub_agent_states": {},
    })
    assert result["final_output"] == "original"
    assert result["sub_agent_states"]["review"].status == "failed"
```

- [ ] **Step 2: Run Reviewer tests and verify RED**

Run: `uv run pytest tests/test_multi_agent_graph.py -k reviewer -v`

Expected: FAIL because `reviewer_graph` and its Nodes do not exist.

- [ ] **Step 3: Implement Reviewer Nodes and conditional route**

Build the existing `ReviewContext` in `prepare_review_node`; run the existing async review iterator in `run_review_node`; route by `review_error` to `finalize_review_node` or `preserve_draft_node`. Keep the current quality score and fallback semantics.

- [ ] **Step 4: Preserve the compatibility wrapper**

Make `review_agent_node(MultiAgentState)` invoke `reviewer_graph.ainvoke(...)`, copy shared outputs to the dataclass, and return the same dictionary keys.

- [ ] **Step 5: Run Reviewer tests and verify GREEN**

Run: `uv run pytest tests/test_multi_agent_graph.py -k 'reviewer or review_agent' -v`

Expected: PASS.

### Task 5: Build the Orchestrator parent graph

**Files:**
- Create: `app/agents/orchestrator/nodes/generate_plan.py`
- Create: `app/agents/orchestrator/nodes/assign_tasks.py`
- Create: `app/agents/orchestrator/nodes/run_memory.py`
- Create: `app/agents/orchestrator/nodes/finalize.py`
- Modify: `app/agents/orchestrator/nodes/__init__.py`
- Modify: `app/agents/orchestrator/graph.py`
- Modify: `app/graph.py`
- Test: `tests/test_multi_agent_graph.py`
- Test: `tests/test_multi_agent_api.py`

**Interfaces:**
- Consumes: compiled `researcher_graph`, `writer_graph`, `reviewer_graph`, unchanged `memory_agent_node()`, and `generate_plan()`.
- Produces: `build_orchestrator_graph()`, compiled `orchestrator_graph`, and unchanged `run_multi_agent_plan()` facade.

- [ ] **Step 1: Write failing parent graph tests**

```python
def test_orchestrator_is_compiled_parent_graph():
    assert set(orchestrator_graph.get_graph().nodes) >= {
        "generate_plan", "assign_tasks", "researcher",
        "writer", "reviewer", "memory", "finalize",
    }

@pytest.mark.asyncio
async def test_orchestrator_facade_returns_compatibility_dataclass(monkeypatch):
    monkeypatch.setattr(
        "app.agents.orchestrator.nodes.generate_plan.generate_plan",
        AsyncMock(return_value=_mock_plan()),
    )
    result = await run_multi_agent_plan("goal")
    assert isinstance(result, MultiAgentState)
```

- [ ] **Step 2: Run Orchestrator tests and verify RED**

Run: `uv run pytest tests/test_multi_agent_graph.py tests/test_multi_agent_api.py -k orchestrator -v`

Expected: FAIL because the compiled parent graph does not exist.

- [ ] **Step 3: Implement parent Nodes and Graph**

Use `StateGraph(MultiAgentGraphState)`. Mount each compiled subgraph by name, route assignment failure to `END`, wrap the unchanged Memory function in a node that converts graph state to `MultiAgentState`, and end through `finalize_node`.

- [ ] **Step 4: Preserve the public facade**

Make `run_multi_agent_plan()` invoke `orchestrator_graph.ainvoke({"goal": goal, "workspace_id": workspace_id, "sub_agent_states": {}})` and convert the shared result back to `MultiAgentState` without exposing private state.

- [ ] **Step 5: Export the parent graph**

Update `app/graph.py` to export Chat graph builders and the Orchestrator graph builder without changing existing exports.

- [ ] **Step 6: Run parent graph tests and verify GREEN**

Run: `uv run pytest tests/test_multi_agent_graph.py tests/test_multi_agent_api.py -v`

Expected: PASS.

### Task 6: Regression verification

**Files:**
- Modify only if a reference error is proven by a failing test.
- Test: existing Agent, Chat, HITL, Prompt, and structured-output suites.

**Interfaces:**
- Consumes: completed parent and child Graphs.
- Produces: evidence that public behavior remains compatible.

- [ ] **Step 1: Run compilation and test collection**

Run: `PYTHONPYCACHEPREFIX=/tmp/content-answer-pycache uv run python -m compileall -q app tests`

Run: `uv run pytest tests --collect-only -q`

Expected: compilation succeeds and all tests collect.

- [ ] **Step 2: Run focused regression suites**

Run: `uv run pytest tests/test_multi_agent_graph.py tests/test_multi_agent_api.py tests/test_chat_sse_events.py tests/test_conversation_graph_branches.py tests/test_hitl_graph.py tests/test_prompt_composer.py tests/test_structured_output.py -q`

Expected: PASS, except only previously documented environment-dependent failures outside this set.

- [ ] **Step 3: Validate structure and diff**

Run: `rg -n 'StateGraph|add_node|add_edge|compile' app/agents/{orchestrator,researcher,writer,reviewer}/graph.py`

Run: `git diff --check`

Expected: every target graph contains real graph construction and the diff has no whitespace errors.

- [ ] **Step 4: Commit the implementation**

```bash
git add app/agents app/graph.py tests/test_multi_agent_graph.py tests/test_multi_agent_api.py
git commit -m "agents: compose multi-agent workflows as graphs"
```
