# Deterministic Platform Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Route explicit platform searches to exactly one matching tool, stop cleanly on platform failures, and prevent duplicate persisted/transient error cards.

**Architecture:** Add a deterministic platform collection node before generic chat. Reuse existing tool and message persistence contracts, and make frontend stream cleanup choose persisted messages as the final error source.

**Tech Stack:** Python 3.11+, LangGraph, LangChain messages/tools, pytest, React 19, TypeScript, Vitest/Bun.

## Global Constraints

- Preserve the removed Zhihu official API and hotlist deletion.
- Do not fall back from an explicit Zhihu request to DDGS or unrelated fetch tools.
- Invoke at most one platform tool in the deterministic path.
- Preserve generic ReAct behavior for requests without an explicit supported platform.
- Follow test-first red-green-refactor for every production behavior change.

---

### Task 1: Deterministic platform routing

**Files:**
- Create: `app/application/agent/nodes/platform_collect.py`
- Modify: `app/application/agent/graphs/conversation.py`
- Test: `tests/test_platform_collect_node.py`
- Test: `tests/test_conversation_graph.py`

**Interfaces:**
- Consumes: `ChatAgentState.intent_platform`, `ChatAgentState.intent_query` and existing LangChain tools.
- Produces: `platform_collect_node(state) -> {"messages": [ToolMessage, AIMessage]}` and `has_platform_search_route(state) -> bool`.

- [ ] Write a failing test proving an explicit Zhihu query selects the platform path.
- [ ] Run the focused routing test and confirm it fails because the path does not exist.
- [ ] Implement the platform search-tool registry and conditional graph route.
- [ ] Run the focused routing test and confirm it passes.
- [ ] Write a failing node test proving `zhihu_search` is invoked once and success emits structured tool data.
- [ ] Implement the minimal single-invocation node.
- [ ] Run node tests and confirm they pass.

### Task 2: Terminal platform failure contract

**Files:**
- Modify: `app/application/agent/tools/zhihu_tool.py`
- Modify: `app/application/agent/nodes/platform_collect.py`
- Test: `tests/test_zhihu_agent_tool.py`
- Test: `tests/test_platform_collect_node.py`

**Interfaces:**
- Consumes: JSON tool payload containing `items` and optional `error`.
- Produces: `error_code`, `retryable=false`, and one final `AIMessage` for failures.

- [ ] Write failing tests for structured non-retryable Zhihu authentication failure and terminal node behavior.
- [ ] Run the tests and confirm the missing structured fields/terminal behavior cause failure.
- [ ] Add the minimal normalized failure fields and final-response formatting.
- [ ] Run focused tests and confirm they pass.

### Task 3: Clear duplicate transient errors

**Files:**
- Modify: `frontend/src/features/chat/chat-stream-lifecycle.ts`
- Modify: `frontend/src/features/chat/chat-panel.tsx`
- Test: `frontend/src/features/chat/chat-stream-lifecycle.test.ts`

**Interfaces:**
- Consumes: refreshed message list and current transient stream error.
- Produces: a lifecycle decision that clears the transient error after successful persisted-message refresh.

- [ ] Write a failing frontend test proving persisted error refresh clears the transient error.
- [ ] Run the focused frontend test and confirm it fails.
- [ ] Implement the minimal lifecycle helper/change and apply it in `refreshAfterStream`.
- [ ] Run the focused frontend test and confirm it passes.

### Task 4: Regression verification

**Files:**
- Verify only; modify tests only if a discovered regression reveals an omitted requirement.

**Interfaces:**
- Consumes: completed Tasks 1–3.
- Produces: fresh test, typecheck, build, and diff-check evidence.

- [ ] Run focused backend platform-routing and Zhihu tests.
- [ ] Run the relevant agent/chat backend suite.
- [ ] Run frontend lifecycle tests.
- [ ] Run `bun run typecheck` and `bun run build`.
- [ ] Run `git diff --check` and inspect `git diff` for unrelated changes.
