# Remove Zhihu Official Infrastructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the Zhihu official API infrastructure and every runtime dependency on it, leaving the Agent-facing `zhihu_search` tool on the existing web collector path only.

**Architecture:** `app/application/agent/tools/zhihu_tool.py` remains the sole Agent-callable Zhihu capability and delegates to the existing web scraping service. Workflow collection remains available through `ZhihuCollector`; the official collector and standalone hotlist stack are removed rather than relocated into another layer.

**Tech Stack:** Python 3.11+, FastAPI, LangChain tools, pytest, React 19, TypeScript.

## Global Constraints

- Delete `app/infrastructure/zhihu/` and all runtime references to it.
- Do not read `ZHIHU_ACCESS_SECRET` anywhere in the remaining Zhihu flow.
- Preserve Zhihu web search, URL import, and web batch collection.
- Remove the standalone `/api/hotlist` contract without a compatibility proxy.
- Preserve the user's unrelated uncommitted `frontend/src/features/chat/` changes.

---

### Task 1: Make the Agent Zhihu tool web-only

**Files:**
- Create: `tests/test_zhihu_agent_tool.py`
- Modify: `app/application/agent/tools/zhihu_tool.py`

**Interfaces:**
- Consumes: `search_zhihu_for_keyword(topic, keyword, user_agent, limit)`.
- Produces: LangChain tool `zhihu_search(keyword: str, limit: int = 10) -> str`, returning JSON with `platform="zhihu"`, `mode="web"`, `topic`, and `items`.

- [ ] Write a failing async test that patches the external web retrieval boundary, invokes `zhihu_search.ainvoke`, and asserts the consumer-visible JSON has `mode == "web"` and mapped question fields.
- [ ] Run `uv run pytest tests/test_zhihu_agent_tool.py -v` and confirm failure because the current code enters the official branch.
- [ ] Delete the `ZhihuOfficialClient` import, official result mapper, and official-first branch; retain the web error JSON contract.
- [ ] Re-run `uv run pytest tests/test_zhihu_agent_tool.py -v` and confirm it passes.

### Task 2: Remove the official collector selection path

**Files:**
- Create: `tests/test_collector_factory.py`
- Modify: `app/infrastructure/collectors/factory.py`
- Modify: `app/infrastructure/sources/adapters/zhihu.py`
- Delete: `app/infrastructure/collectors/zhihu_official_collector.py`
- Delete: `app/infrastructure/zhihu/__init__.py`
- Delete: `app/infrastructure/zhihu/official_client.py`

**Interfaces:**
- Consumes: `ZhihuCollector`.
- Produces: `CollectorFactory.create("zhihu", source="auto"|"web") -> ZhihuCollector`; explicit `source="official"` raises `ValueError`.

- [ ] Write failing tests that verify `auto` and `web` return `ZhihuCollector`, even when `ZHIHU_ACCESS_SECRET` is set, and `official` raises a clear unsupported-source error.
- [ ] Run `uv run pytest tests/test_collector_factory.py -v` and confirm the credential-driven official-selection case fails.
- [ ] Remove the official collector registration and environment credential branch; update `ZhihuSource.collect` to always instantiate `ZhihuCollector`.
- [ ] Delete the official collector and official client directory.
- [ ] Re-run the collector and Zhihu import tests and confirm they pass.

### Task 3: Remove the standalone hotlist stack and its consumers

**Files:**
- Modify: `tests/test_opportunity_scanner.py`
- Modify: `app/server.py`
- Modify: `app/application/opportunity_service.py`
- Modify: `app/application/agent/adapters.py`
- Modify: `app/application/agent/ports.py`
- Delete: `app/api/routes/hotlist.py`
- Delete: `app/services/hotlist_service.py`
- Delete: `app/application/agent/graphs/analysis.py`
- Delete: `app/application/agent/nodes/fetch_hotlist.py`
- Modify: `app/models.py`
- Modify: `app/config/loader.py`
- Modify: `app/config/settings.toml`

**Interfaces:**
- Produces: FastAPI application without `/api/hotlist`; `OpportunityService.scan_and_persist(...)` safely returns `0` because automatic hotlist sensing is unavailable.

- [ ] Replace the hotlist-backed opportunity test with a failing test asserting enabled scanning returns zero without trying to import or call a hotlist service.
- [ ] Run the focused opportunity test and confirm it fails while the old hotlist dependency exists.
- [ ] Remove the hotlist router/service, Agent analysis adapter/port/node/graph, hotlist models and settings.
- [ ] Convert proactive scanning to an explicit logged no-op while preserving opportunity CRUD and scoring helpers.
- [ ] Run `uv run pytest tests/test_opportunity_scanner.py -v` and a server import check.

### Task 4: Remove the dead frontend hotlist entry point and verify the boundary

**Files:**
- Modify: `frontend/src/app/App.tsx`
- Modify: `frontend/src/types/workflow.ts`
- Delete: `frontend/src/features/hotlist/hotlist-page.tsx`

**Interfaces:**
- Produces: Frontend routing without `/hotlist` and without an API caller for `/api/hotlist`.

- [ ] Remove the hidden route, component import, component file, and now-unused hotlist transport types.
- [ ] Run `bun run typecheck` from `frontend/`.
- [ ] Run `rg -n "infrastructure\\.zhihu|ZhihuOfficialClient|ZhihuOfficialCollector|/api/hotlist|hotlist_service" app frontend/src tests` and require no runtime references.
- [ ] Run the focused backend test set, then `uv run pytest tests/` if the focused set passes.
- [ ] Run `git diff --check` and inspect `git status --short` to ensure unrelated chat files are untouched.
