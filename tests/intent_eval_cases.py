"""意图识别评测集：真实输入 + 期望意图，用于回归验证三层意图识别。

每条用例含：
  - input: 用户消息
  - intent: 期望执行模式
  - knowledge_mode: 期望知识模式（None 表示不校验）
  - platform: 期望平台（None 表示不校验）
  - rule_only: True 表示应由规则层确定性命中（不依赖 LLM）

运行方式：直接跑本文件（mock LLM），验证规则层与校验层；
或用 run_intent_eval.py 跑真实 LLM 全量评测。
"""
from __future__ import annotations

INTENT_EVAL_CASES = [
    # ── 寒暄/闲聊 ──
    {"input": "你好", "intent": "chat", "knowledge_mode": "off", "rule_only": True},
    {"input": "在吗？", "intent": "chat", "knowledge_mode": "off", "rule_only": True},
    {"input": "谢谢", "intent": "chat", "knowledge_mode": "off", "rule_only": True},
    {"input": "hello", "intent": "chat", "knowledge_mode": "off", "rule_only": True},
    # ── 平台采集 ──
    {"input": "帮我搜搜知乎上关于副业的热门讨论", "intent": "chat", "platform": "zhihu", "rule_only": True},
    {"input": "请您检索一下小红书关于历史播客的帖子，需要发布时间最近的，只要五个，不要重复",
     "intent": "chat", "platform": "xiaohongshu", "rule_only": True},
    {"input": "采集 B站 上关于 AI 的视频", "intent": "chat", "platform": "bilibili", "rule_only": True},
    {"input": "看看 YouTube 有没有做手冲咖啡的教程", "intent": "chat", "platform": "youtube", "rule_only": True},
    {"input": "搜搜推特上关于 AI 绘画的讨论", "intent": "chat", "platform": "twitter", "rule_only": True},
    {"input": "github 上有没有好用的 RAG 项目", "intent": "chat", "platform": "github", "rule_only": True},
    # ── URL 解析 ──
    {"input": "解析一下 https://zhuanlan.zhihu.com/p/123", "intent": "parse_url", "rule_only": True},
    # ── 单篇创作 ──
    {"input": "写一篇关于 RAG 的回答", "intent": "task_plan", "rule_only": True},
    {"input": "写个小红书种草笔记", "intent": "task_plan", "rule_only": True},
    {"input": "帮我写一份关于知识管理的文章", "intent": "task_plan", "rule_only": True},
    # ── 多阶段创作 ──
    {"input": "调研并输出一份 AI Agent 行业现状的完整分析报告", "intent": "multi_agent", "rule_only": True},
    {"input": "策划并产出一个小红书爆款选题矩阵", "intent": "multi_agent", "rule_only": True},
    # ── 严格知识模式 ──
    {"input": "只能根据我上传的文件回答，为什么 chmod 能防止未授权访问",
     "intent": "chat", "knowledge_mode": "strict", "rule_only": True},
    {"input": "只许用私有资料，解释一下 RAG 的流程",
     "intent": "chat", "knowledge_mode": "strict", "rule_only": True},
    # ── 普通问答（应交给 LLM，或规则未命中） ──
    {"input": "你觉得人工智能未来的发展趋势如何", "intent": "chat", "knowledge_mode": "normal"},
    {"input": "为什么天空是蓝色的", "intent": "chat", "knowledge_mode": "normal"},
    {"input": "解释一下什么是区块链", "intent": "chat", "knowledge_mode": "normal"},
    # ── 模糊/边界 ──
    {"input": "帮我找找有哪些做副业的内容", "intent": "chat", "knowledge_mode": "normal"},
    {"input": "写一个关于 AI 的回答，顺便调研下当前进展",
     "intent": "multi_agent", "knowledge_mode": "normal"},
]
