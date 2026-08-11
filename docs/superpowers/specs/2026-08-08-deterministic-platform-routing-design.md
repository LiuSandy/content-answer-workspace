# Deterministic Platform Routing Design

## Goal

Make explicit platform collection requests use the matching platform tool deterministically, terminate cleanly on non-retryable platform failures, and render a persisted failure only once.

## Scope

- Requests recognized as `intent="chat"` with both `intent_platform` and `intent_query` enter a platform collection path before the generic chat agent.
- The first implementation supports every platform that already exposes a search-style tool, with Zhihu as the regression-critical case.
- Zhihu collection invokes only `zhihu_search`; it does not fall back to DDGS, `web_fetch`, or `crawl4ai_fetch` after an authentication failure.
- The removed official Zhihu hotlist API remains removed. “知乎热门问题” is treated as a keyword search, not represented as an authoritative hotlist.
- Generic requests without an explicit supported platform continue through the existing ReAct chat path.

## Architecture

Add a deterministic `platform_collect` graph node selected by `_route_after_intent`. The node resolves a platform to one existing search tool, invokes it once with `intent_query`, parses its JSON result, and emits both a `ToolMessage` and a final `AIMessage`.

The final AI message lets the existing chat persistence path save a normal assistant response. The tool message lets the existing `source_list` persistence logic save structured source cards without adding a second persistence implementation.

Tool results use a small normalized contract:

- Success: `platform`, `items`, optional `topic`.
- Failure: `platform`, `items=[]`, `error`, optional `error_code`, `retryable`.

Legacy string errors are treated as non-retryable by the deterministic path. The platform path always terminates after one invocation; only the generic chat path retains the ReAct loop.

## Routing Rules

- `intent_platform` and a supported search tool exist: `route_intent -> platform_collect -> END`.
- Platform is absent, query is absent, or platform has no search mapping: retain `route_intent -> knowledge_decision -> chat`.
- `parse_url`, `task_plan`, and `multi_agent` keep their existing higher-priority routes.

Initial search mapping:

- `zhihu -> zhihu_search(keyword, limit)`
- `xiaohongshu -> xiaohongshu_search(query, limit)`
- `bilibili -> bilibili_search(query, limit)`
- `twitter -> twitter_search(query, limit)`
- `reddit -> reddit_search(query, limit)`
- `github -> github_search_repos(query, limit)`

Platforms whose current tools do not expose keyword search remain on generic chat routing.

## Error Handling

- Platform tool exception: convert to a single non-retryable platform error response.
- JSON result with `error` and no items: emit one user-facing assistant error and stop.
- Empty successful result: emit a clear “未检索到结果” message and stop.
- No fallback to unrelated tools occurs inside the deterministic platform path.

The frontend continues to show `run.failed` while streaming, but clears `streamingError` after the persisted message history refresh succeeds. The database message becomes the single source of truth.

## Tests

- Routing test: explicit Zhihu platform/query routes to `platform_collect`.
- Node success test: invokes only `zhihu_search` once and emits source data plus final response.
- Node failure test: authentication error produces a final response and does not request another tool.
- Generic chat test: requests without an explicit supported platform retain the existing route.
- Frontend lifecycle test: a refreshed persisted error clears the transient SSE error.
- Run focused backend tests, full relevant agent tests, frontend unit tests, typecheck, and build.

## Non-goals

- Reintroducing the deleted official Zhihu API or hotlist page.
- Circumventing Zhihu authentication controls.
- Making Agent Reach provide a Zhihu backend; it currently has none.
