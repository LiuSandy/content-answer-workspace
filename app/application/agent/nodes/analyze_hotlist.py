from __future__ import annotations

from ....config.loader import load_prompt
from ..state import AgentState
from ..ports import LLMClientPort

_SYSTEM_PROMPT = load_prompt("hotlist_analysis")


async def analyze_hotlist_node(state: AgentState, *, llm: LLMClientPort) -> dict:
    """调用 LLM 分析热榜，返回结构化 JSON 字符串。JSON 解析交给前端处理。"""
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
