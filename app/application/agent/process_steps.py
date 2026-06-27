"""工具调用过程的展示文案；单独定义是为了让流式接口与历史接口共用同一套措辞，
避免实时进度与历史回看两处文案漂移。前端实时块直接展示这里下发的 text。"""

from __future__ import annotations


def tool_start_step(name: str) -> str:
    """生成「开始调用某工具」的过程文案；name 为工具名。"""
    return f"🔧 开始调用 {name or '工具'}"


def tool_end_step(name: str) -> str:
    """生成「某工具已返回结果」的过程文案；不展示条数，规避不同工具输出格式不统一的问题。"""
    return f"✅ {name or '工具'} 已返回结果"
