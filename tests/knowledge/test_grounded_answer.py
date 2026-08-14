import pytest
from app.application.agent.nodes.knowledge_decision import make_knowledge_decision


def test_knowledge_decision_node():
    # 用户显示指定 knowledgeMode == 'off'
    decision, reason = make_knowledge_decision(query="用通用知识回答", mode="off")
    assert decision is False

    # 包含私有资料/算法/教学等意图
    decision, reason = make_knowledge_decision(query="关于算法教学笔记", mode="normal")
    assert decision is True

    # 包含显式严格模式要求
    decision, reason = make_knowledge_decision(query="仅依据我的私有资料回答", mode="strict")
    assert decision is True
