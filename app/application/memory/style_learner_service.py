"""StyleLearnerService：从版本编辑中提炼风格规则（roadmap R9）。

- 仅分析 AI→用户手动版本对（version_type 非 initial/refine/rewrite 等）。
- 每文档每来源版本对只分析一次（幂等）。
- 提炼结果作为 pending implicit 记忆，经确认后生效。
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from sqlalchemy import select

from ...persistence.models.documents import AnswerDocument, AnswerVersion
from ...persistence.models.user_memories import UserMemoryModel

logger = logging.getLogger(__name__)

# 排除的 AI 自动版本类型（不参与学习）
AI_VERSION_TYPES = {
    "initial_generation",
    "inline_refinement",
    "full_rewrite",
    "refinement_loop",
}


async def learn_style_from_versions(
    session,
    version_pair: tuple[AnswerVersion, AnswerVersion],
    document_id,
) -> int:
    """分析一个 (before_version, after_version) 对，提取风格规则并存入 pending implicit 记忆。

    返回提取到的规则数；仅在学习 AI 版本 → 用户手动版本时提取。
    对已分析过的版本对跳过（幂等）。
    """
    before_v, after_v = version_pair

    # 仅分析 AI→手动版本
    if before_v.version_type not in AI_VERSION_TYPES:
        return 0
    if after_v.version_type in AI_VERSION_TYPES:
        return 0  # AI→AI 不提炼

    diff_text = _diff_text(before_v.content or "", after_v.content or "")
    if not diff_text.strip():
        return 0

    # 幂等：已分析过的版本对跳过
    existing = (
        await session.execute(
            select(UserMemoryModel.id).where(
                UserMemoryModel.source == f"learn:{document_id}_{before_v.id}",
            ).limit(1)
        )
    ).scalar_one_or_none()
    if existing:
        return 0

    rules = await _extract_rules(f"原文：" + diff_text[:2000])
    count = 0
    for rule in rules:
        mem = UserMemoryModel(
            workspace_id="default",
            memory_type="implicit",
            content=rule["content"],
            confidence=rule.get("confidence", 0.75),
            status="pending_confirmation",
            evidence=f"从第 {after_v.version_number} 版对比提炼（原版为 {before_v.version_type}）",
            source=f"learn:{document_id}_{before_v.id}",
        )
        session.add(mem)
        count += 1

    if count:
        await session.commit()
    return count


def _diff_text(before: str, after: str) -> str:
    """简单行级别 diff 摘要。"""
    before_lines = [l.strip() for l in before.splitlines() if l.strip()]
    after_lines = [l.strip() for l in after.splitlines() if l.strip()]
    removed = set(before_lines) - set(after_lines)
    added = set(after_lines) - set(before_lines)
    parts = []
    if removed:
        parts.append("删除:" + "; ".join(list(removed)[:5]))
    if added:
        parts.append("新增:" + "; ".join(list(added)[:5]))
    return "\n".join(parts)


async def _extract_rules(diff_text: str) -> list[dict]:
    from ...prompts.registry import prompt_registry
    from ...application.agent.adapters import DeepSeekLLMAdapter

    rendered = prompt_registry.render(
        "analysis.style_rules",
        diff_text=diff_text,
    )
    llm = DeepSeekLLMAdapter()
    raw = await llm.analyze(
        rendered.messages[0].content,
        rendered.messages[1].content if len(rendered.messages) > 1 else "",
    )
    try:
        data = json.loads(raw)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


async def analyze_document_versions(
    session, document_id
) -> int:
    """对某文档的所有版本对进行分析，提取风格规则。

    返回新提取的规则数。
    """
    versions = (
        await session.execute(
            select(AnswerVersion)
            .where(AnswerVersion.document_id == document_id)
            .order_by(AnswerVersion.created_at)
        )
    ).scalars().all()

    total = 0
    for i in range(len(versions) - 1):
        pair = (versions[i], versions[i + 1])
        try:
            count = await learn_style_from_versions(session, pair, document_id)
            total += count
        except Exception as e:
            logger.warning("Style learning failed for %s pair %d: %s", document_id, i + 1, e)
    return total
