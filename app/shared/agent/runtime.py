"""Agent 运行调度与稳定 SSE 事件封装（roadmap R2 Step 4）。

提供三类能力：
1. run_agent_stream —— 包装 graph.astream_events：
   - 事件匹配子图感知：事件 name 或 metadata.langgraph_node 命中即算
     （子图内节点不再依赖单一 langgraph_node 字符串，spec §11.8）
   - 每个事件都有超时预算，超时/取消产出稳定终态 agent.error 并结束
   - 生成/图执行错误不自动重试（由调用方决定重试策略）
2. retrieve_with_retry —— 幂等检索最多重试一次，返回 (result, error)
3. ChatRuntime —— 每 chat 并发运行锁（同一 chat 同时最多 1 个运行）
"""
from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator, Awaitable, Callable

AGENT_TIMEOUT_ERROR = "agent_timeout"


async def retrieve_with_retry(
    fn: Callable[[], Awaitable[Any]],
    max_attempts: int = 2,
) -> tuple[Any, str | None]:
    """幂等检索最多重试 max_attempts 次。

    检索是幂等的（同样的查询每次结果一致），失败重试一次是安全的；
    始终失败时返回 (None, error_message)，由调用方决定降级路径。
    """
    last_error: Exception | None = None
    for _ in range(max_attempts):
        try:
            return await fn(), None
        except Exception as e:  # noqa: BLE001 - 检索失败统一降级
            last_error = e
    return None, str(last_error) if last_error else "unknown error"


def _rag_events(node_state: dict) -> list[tuple[str, dict]]:
    """从 retrieve_knowledge 输出构造稳定 RAG 事件。"""
    retrieval = node_state.get("retrieval_result")
    if retrieval is None:
        return []
    trace_id = node_state.get("trace_id")
    sources = [
        {
            "label": s.get("label"),
            "title": s.get("title", "Unknown Document"),
            "sourceType": s.get("sourceType", "私有资料"),
            "sourceUrl": s.get("sourceUrl"),
            "contentSnippet": (s.get("text") or "")[:300],
        }
        for s in (getattr(retrieval, "sources", None) or [])
        if s.get("label")
    ]
    if getattr(retrieval, "has_evidence", False) and sources:
        return [("rag.sources", {"sources": sources, "traceId": trace_id})]
    return [
        (
            "rag.fallback",
            {
                "reason": (
                    getattr(retrieval, "fallback_reason", None)
                    or "私有资料证据不足，使用了其他知识来源"
                ),
                "traceId": trace_id,
            },
        )
    ]


def _normalize_event(event: dict) -> list[tuple[str, dict]]:
    """把单个 langgraph 事件规范化为稳定命名的事件元组列表。

    匹配规则子图感知（spec §11.8）：事件 name 或 metadata.langgraph_node
    命中关键节点即算完成，不再依赖单一字符串。
    """
    kind = event.get("event")
    name = event.get("name")
    metadata = event.get("metadata") or {}

    if kind == "on_node_start":
        status_map = {
            "route_intent": ("agent.status", {"status": "routing_intent"}),
            "chat": ("agent.status", {"status": "generating"}),
            "parse_url": ("tool.started", {"tool_type": "parse_url"}),
            "collect": ("tool.started", {"tool_type": "collect"}),
        }
        mapped = status_map.get(name)
        return [mapped] if mapped else []

    if kind == "on_chain_end":
        output = (event.get("data") or {}).get("output") or {}
        if not isinstance(output, dict):
            output = {}
        meta_node = metadata.get("langgraph_node")

        if name == "guard" or meta_node == "guard":
            if output.get("guard_blocked"):
                messages = output.get("messages") or []
                for message in reversed(messages):
                    content = getattr(message, "content", None)
                    if content:
                        return [
                            ("agent.status", {"status": "blocked"}),
                            ("message.delta", {"delta": content}),
                        ]
            return []

        if name == "platform_collect" or meta_node == "platform_collect":
            messages = output.get("messages") or []
            for message in reversed(messages):
                if getattr(message, "type", None) == "ai" and getattr(message, "content", None):
                    return [("message.delta", {"delta": message.content})]
            return []

        if name == "retrieve_knowledge" or meta_node == "retrieve_knowledge":
            return _rag_events(output)
        if name == "task_plan" or meta_node == "task_plan":
            tp = output.get("task_plan_result")
            if tp:
                return [
                    (
                        "task_plan.created",
                        {
                            "planId": tp.get("planId"),
                            "goal": tp.get("goal"),
                            "status": tp.get("status"),
                            "preview": tp.get("preview"),
                        },
                    )
                ]
            return []
        if name == "multi_agent" or meta_node == "multi_agent":
            ma = output.get("multi_agent_result")
            if ma:
                return [
                    (
                        "multi_agent.status",
                        {
                            "status": ma.get("status"),
                            "agents": ma.get("agents", []),
                            "finalContent": ma.get("finalContent"),
                        },
                    )
                ]
            return []
        if name == "writer" or meta_node == "writer":
            events: list[tuple[str, dict]] = []
            task_plan = output.get("task_plan_result")
            if task_plan:
                events.append(
                    (
                        "task_plan.created",
                        {
                            "planId": task_plan.get("planId"),
                            "goal": task_plan.get("goal"),
                            "status": task_plan.get("status"),
                            "preview": task_plan.get("preview"),
                        },
                    )
                )
            multi_agent = output.get("multi_agent_result")
            if multi_agent:
                events.append(
                    (
                        "multi_agent.status",
                        {
                            "status": multi_agent.get("status"),
                            "agents": multi_agent.get("agents", []),
                            "finalContent": multi_agent.get("finalContent"),
                        },
                    )
                )
            messages = output.get("messages") or []
            for message in reversed(messages):
                content = getattr(message, "content", None)
                if content:
                    events.append(("message.delta", {"delta": content}))
                    break
            return events

    if kind == "on_chat_model_stream":
        # route_intent 使用结构化输出调用模型。该模型的流片段（通常是
        # IntentRoute JSON）只用于内部路由，不能作为 assistant 文本推送给前端。
        # 仅透传真正负责生成用户回答的 chat/writer 模型事件。
        langgraph_node = metadata.get("langgraph_node")
        if langgraph_node in {"route_intent", "guard"}:
            return []
        chunk = (event.get("data") or {}).get("chunk")
        if chunk is not None and getattr(chunk, "content", None):
            return [("message.delta", {"delta": chunk.content})]

    return []


async def run_agent_stream(
    graph: Any,
    inputs: dict,
    config: dict,
    timeout_seconds: float = 30.0,
) -> AsyncIterator[tuple[str, dict]]:
    """包装 graph.astream_events，统一产出稳定命名的事件元组。

    每个事件都有 timeout_seconds 的预算；超时或取消时产出稳定终态
    ("agent.error", {"errorCode": "agent_timeout", ...}) 并结束，不抛异常。
    其他异常（生成失败等）原样上抛——运行错误不自动重试。
    """
    agen = graph.astream_events(inputs, config, version="v2")
    try:
        while True:
            try:
                event = await asyncio.wait_for(agen.__anext__(), timeout=timeout_seconds)
            except StopAsyncIteration:
                return
            for name, data in _normalize_event(event):
                yield (name, data)
    except asyncio.TimeoutError:
        yield (
            "agent.error",
            {
                "errorCode": AGENT_TIMEOUT_ERROR,
                "message": f"生成超时（超过 {timeout_seconds:.0f}s 无新事件），已自动停止。请换个说法重试。",
            },
        )
    except asyncio.CancelledError:
        yield (
            "agent.error",
            {"errorCode": AGENT_TIMEOUT_ERROR, "message": "运行已取消"},
        )


class ChatRuntime:
    """每 chat 并发运行锁：同一 chat 同时最多 1 个 Agent 运行。

    配合 POST /choices 等入口使用：运行期间占用 chat 级锁，其他提交被拒（409），
    保证同一对话的消息与状态不会被并发写入打乱。
    """

    def __init__(self) -> None:
        self._running: set[str] = set()
        self._lock = asyncio.Lock()

    async def try_acquire(self, chat_id: str) -> bool:
        """尝试为 chat_id 获取运行锁；已被占用返回 False。"""
        async with self._lock:
            if chat_id in self._running:
                return False
            self._running.add(chat_id)
            return True

    def release(self, chat_id: str) -> None:
        """释放 chat_id 的运行锁（幂等）。"""
        self._running.discard(chat_id)

    @property
    def running(self) -> set[str]:
        """当前占用运行锁的 chat id 快照。"""
        return set(self._running)
