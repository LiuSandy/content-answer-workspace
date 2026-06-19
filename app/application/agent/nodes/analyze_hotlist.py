from __future__ import annotations

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
