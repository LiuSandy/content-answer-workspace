"""RAG 上下文组装器：把检索命中的内容块拼装成带引用标签的上下文文本。

单独成模块是为了把 token 预算控制集中在一处——上游只管召回排序，
"塞多少进上下文"的裁剪决策全部由这里负责。
"""
from dataclasses import dataclass
from typing import Any


@dataclass
class ContextBlock:
    doc_title: str
    content: str
    source_type: str
    source_url: str | None = None
    updated_at: str | None = None


def estimate_tokens(text: str) -> int:
    """粗略估算文本 token 数：CJK 字符按 1 token，其余按 4 字符 1 token。

    不引入真实 tokenizer 是权衡：预算控制只需数量级正确，
    而 tokenizer 依赖会拖慢每次检索。
    """
    cjk = sum(1 for ch in text if "一" <= ch <= "鿿")
    other = len(text) - cjk
    return cjk + (other + 3) // 4


class ContextBuilder:
    def __init__(self, max_tokens: int = 6000):
        self.max_tokens = max_tokens

    def build_context(self, blocks: list[ContextBlock]) -> tuple[str, list[dict[str, Any]]]:
        """按顺序拼装 block，累计估算 token 超过预算即停止追加。

        返回 (上下文文本, 实际纳入的来源列表)——调用方必须以返回的
        来源列表为准生成引用标签，不能假设所有 block 都被纳入。
        """
        context_parts = []
        sources = []
        used_tokens = 0

        for idx, block in enumerate(blocks, start=1):
            label = f"[S{idx}]"
            part = f"{label} Source: {block.doc_title}\n{block.content}\n"
            part_tokens = estimate_tokens(part)
            # 第一个 block 即使超预算也纳入，保证上下文不为空
            if context_parts and used_tokens + part_tokens > self.max_tokens:
                break
            context_parts.append(part)
            used_tokens += part_tokens
            sources.append({
                "label": label,
                "title": block.doc_title,
                "sourceType": block.source_type,
                "sourceUrl": block.source_url,
                "contentSnippet": block.content[:150],
            })

        full_context = "\n".join(context_parts)
        return full_context, sources
