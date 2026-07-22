def make_knowledge_decision(query: str, mode: str = "normal") -> tuple[bool, str]:
    if mode == "off":
        return False, "Knowledge retrieval disabled by user mode setting."

    if mode == "strict":
        return True, "Strict knowledge mode requested."

    # 识别知识库启发关键词与问题意图
    keywords = ["资料", "算法", "教学", "网站搭建", "部署", "选型", "代码", "文档", "知识库", "笔记"]
    query_lower = query.lower()
    if any(k in query_lower for k in keywords):
        return True, "Query contains technical or knowledge-base domain keywords."

    # 默认正常创作模式触发智能检索
    return True, "Default RAG decision for creative assistant."
