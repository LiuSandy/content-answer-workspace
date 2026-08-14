"""知识检索决策：判断当前查询是否需要触发 RAG 检索。

单独成模块是为了让"是否检索"的决策只有一处实现——图节点、API 路由
都调用 make_knowledge_decision，不各自内嵌判断逻辑。
"""

# 纯寒暄/客套语：这类消息检索知识库纯属浪费（每次检索含多次 LLM 调用）
_CHITCHAT_PHRASES = {
    "你好", "您好", "嗨", "哈喽", "在吗", "谢谢", "谢啦", "多谢",
    "好的", "嗯", "嗯嗯", "行", "可以", "没了", "拜拜", "再见",
    "hi", "hello", "hey", "thanks", "thank you", "ok", "okay", "bye",
}


def make_knowledge_decision(query: str, mode: str = "normal") -> tuple[bool, str]:
    """返回 (是否检索, 决策原因)。

    normal 模式默认检索（创作/问题类查询都可能受益于私有资料），
    仅对纯寒暄和过短消息跳过——这是真实生效的决策，
    不是"永远返回 True"的伪判断。
    """
    if mode == "off":
        return False, "Knowledge retrieval disabled by user mode setting."

    if mode == "strict":
        return True, "Strict knowledge mode requested."

    normalized = query.strip().lower().rstrip("！!。.~？?")
    if not normalized:
        return False, "Empty query, retrieval skipped."
    if normalized in _CHITCHAT_PHRASES:
        return False, "Chitchat message, retrieval skipped."
    if len(normalized) <= 2:
        return False, "Query too short to benefit from retrieval."

    return True, "Substantive query, retrieval enabled in normal mode."
