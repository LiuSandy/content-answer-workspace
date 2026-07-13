"""采集和 URL 解析节点；通过 SourceRegistry 分派给具体适配器。"""
from __future__ import annotations

import logging
import uuid

from ....domain.dto import AgentError, ChatResponsePayload, ParseUrlRequest, ToolContext, ToolResult
from ....persistence.session import get_session_factory
from ...chat_service import ChatService
from ..state import ChatAgentState

logger = logging.getLogger(__name__)


async def parse_url_node(state: ChatAgentState) -> dict:
    """URL 解析节点；通过 Source Registry 路由到对应平台适配器。"""
    from ....infrastructure.sources.registry import source_registry

    urls = state.get("extracted_urls", [])
    if not urls:
        return {"tool_result": ToolResult(tool_type="parse_url", items=[], total_found=0)}

    run_id = str(uuid.uuid4())
    context = ToolContext(chat_id=state.get("chat_id"), run_id=run_id)
    items = []

    for url in urls:
        try:
            source = source_registry.get_for_url(url)
            request = ParseUrlRequest(url=url, chat_id=state.get("chat_id"))
            # Type ignore since it's a protocol
            item = await source.parse_url(request, context)  # type: ignore
            items.append(item)
        except Exception as e:
            logger.warning("Failed to parse URL %s: %s", url, e)

    return {
        "tool_result": ToolResult(
            tool_type="parse_url",
            items=items,
            total_found=len(items),
        )
    }


async def collect_node(state: ChatAgentState) -> dict:
    """主题采集节点；通过 Source Registry 选择适配器并返回帖子列表。"""
    from ....infrastructure.sources.registry import source_registry

    collection_request = state.get("collection_request")
    if not collection_request:
        return {"tool_result": ToolResult(tool_type="collect", items=[], total_found=0)}

    run_id = str(uuid.uuid4())
    context = ToolContext(chat_id=state.get("chat_id"), run_id=run_id)

    try:
        source = source_registry.get_for_collect(collection_request.platform)
        # Type ignore since it's a protocol
        items = await source.collect(collection_request, context)  # type: ignore
        return {
            "tool_result": ToolResult(
                tool_type="collect",
                platform=collection_request.platform,
                items=items,
                total_found=len(items),
            )
        }
    except Exception as e:
        logger.error("Collection failed: %s", e)
        return {"error": AgentError(error_code="collection_failed", message=str(e))}


async def normalize_and_persist_node(state: ChatAgentState) -> dict:
    """标准化并保存；将 ToolResult 中的 SourceItem 写入数据库，并将生成的主键 UUID 回填。"""
    tool_result = state.get("tool_result")
    chat_id_str = state.get("chat_id")
    if not tool_result or not tool_result.items or not chat_id_str:
        return {}

    try:
        chat_id = uuid.UUID(chat_id_str)
        session_factory = get_session_factory()
        async with session_factory() as session:
            chat_service = ChatService(session)
            saved_items = await chat_service.save_source_items(chat_id, tool_result.items)
            
            # 回填数据库的主键 UUID 到 DTO 列表中，供前端调用
            for dto, db_item in zip(tool_result.items, saved_items):
                dto.id = db_item.id

        return {"tool_result": tool_result}
    except Exception as e:
        logger.error("Failed to persist source items: %s", e)
        # 我们不中断执行，仅记录错误日志
    return {}





async def build_response_node(state: ChatAgentState) -> dict:
    """构造前端响应载荷；产生稳定的 SSE 事件载荷。"""
    error = state.get("error")
    if error:
        payload = ChatResponsePayload(
            message_id=str(uuid.uuid4()),
            message_type="error",
            structured={"error_code": error.error_code, "message": error.message},
        )
        return {"response_payload": payload}

    tool_result = state.get("tool_result")
    if tool_result and tool_result.items:
        serialized_items = []
        for item in tool_result.items:
            item_dict = item.model_dump(by_alias=True)
            if item_dict.get("id"):
                item_dict["id"] = str(item_dict["id"])
            serialized_items.append(item_dict)

        payload = ChatResponsePayload(
            message_id=str(uuid.uuid4()),
            message_type="source_list",
            structured={
                "tool_type": tool_result.tool_type,
                "total_found": tool_result.total_found,
                "items": serialized_items,
            },
        )
        return {"response_payload": payload}

    return {"response_payload": None}
