"""父子分块器：把 Markdown 切分为父块（上下文单元）与子块（检索单元）。

单独成模块是为了让"怎么切"与"怎么建索引"解耦——索引服务只消费
ChunkResult，不关心标题解析与句子边界的细节。
"""
import re
from dataclasses import dataclass, field
from typing import List

from app.application.knowledge.context_builder import estimate_tokens

# Markdown ATX 标题（# 至 ######）
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
# 句子终结符：中英文句号/问号/感叹号/分号 + 换行
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[。！？；!?;\.\n])")


@dataclass
class ChunkResult:
    parent_content: str
    child_chunks: List[str]
    heading_path: str = ""


@dataclass
class _Section:
    """同一标题路径下的连续段落集合；分块时父块绝不跨 Section 边界。"""

    heading_path: str
    paragraphs: List[str] = field(default_factory=list)


def _parse_sections(markdown_text: str) -> List[_Section]:
    """按标题层级把 Markdown 切成 Section，并维护 heading_path。

    单独抽出是因为标题栈的维护（进入更深层级 push、回到浅层级 pop）
    与后续的长度切分是两类逻辑；代码围栏内的 # 不算标题。
    """
    sections: List[_Section] = []
    heading_stack: List[tuple[int, str]] = []
    current_lines: List[str] = []
    in_code_fence = False

    def flush_paragraphs():
        text = "\n".join(current_lines)
        current_lines.clear()
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        if not paragraphs:
            return
        path = " > ".join(title for _, title in heading_stack)
        if sections and sections[-1].heading_path == path:
            sections[-1].paragraphs.extend(paragraphs)
        else:
            sections.append(_Section(heading_path=path, paragraphs=paragraphs))

    for line in markdown_text.splitlines():
        if line.lstrip().startswith("```"):
            in_code_fence = not in_code_fence
            current_lines.append(line)
            continue
        match = None if in_code_fence else _HEADING_RE.match(line)
        if match:
            flush_paragraphs()
            level = len(match.group(1))
            title = match.group(2).strip()
            while heading_stack and heading_stack[-1][0] >= level:
                heading_stack.pop()
            heading_stack.append((level, title))
        else:
            current_lines.append(line)
    flush_paragraphs()
    return sections


class ParentChildChunker:
    def __init__(self, parent_max_tokens: int = 1200, child_max_tokens: int = 350, overlap_tokens: int = 50):
        self.parent_max_tokens = parent_max_tokens
        self.child_max_tokens = child_max_tokens
        self.overlap_tokens = overlap_tokens

    def chunk(self, markdown_text: str) -> List[ChunkResult]:
        results: List[ChunkResult] = []
        for section in _parse_sections(markdown_text):
            results.extend(self._chunk_section(section))
        return results

    def _chunk_section(self, section: _Section) -> List[ChunkResult]:
        """在单个 Section 内按段落边界聚合父块；父块永不跨章节。"""
        results: List[ChunkResult] = []
        current_parent: List[str] = []
        current_tokens = 0

        def flush_parent():
            nonlocal current_tokens
            if not current_parent:
                return
            parent_str = "\n\n".join(current_parent)
            results.append(ChunkResult(
                parent_content=parent_str,
                child_chunks=self._slice_children(parent_str),
                heading_path=section.heading_path,
            ))
            current_parent.clear()
            current_tokens = 0

        for p in section.paragraphs:
            p_tokens = estimate_tokens(p)
            if current_parent and current_tokens + p_tokens > self.parent_max_tokens:
                flush_parent()
            current_parent.append(p)
            current_tokens += p_tokens
        flush_parent()
        return results

    def _slice_children(self, parent_text: str) -> List[str]:
        """把父块切成子块：优先在句子边界断开，带重叠；超长句子才硬切。

        不做纯字符滑窗是因为它会从句子/表格中间切断，
        破坏检索单元的语义完整性。
        """
        if estimate_tokens(parent_text) <= self.child_max_tokens:
            return [parent_text]

        sentences = [s for s in _SENTENCE_SPLIT_RE.split(parent_text) if s]
        # 超长单句先硬切成不超过 child_max 的片段，保证后续聚合可行
        units: List[str] = []
        for s in sentences:
            if estimate_tokens(s) <= self.child_max_tokens:
                units.append(s)
            else:
                step = max(self.child_max_tokens, 1)
                for i in range(0, len(s), step):
                    units.append(s[i:i + step])

        children: List[str] = []
        current: List[str] = []
        current_tokens = 0
        for unit in units:
            unit_tokens = estimate_tokens(unit)
            if current and current_tokens + unit_tokens > self.child_max_tokens:
                children.append("".join(current).strip())
                # 重叠：保留尾部若干句子作为下一子块的开头，维持上下文连续
                overlap: List[str] = []
                overlap_tokens = 0
                for prev in reversed(current):
                    prev_tokens = estimate_tokens(prev)
                    if overlap_tokens + prev_tokens > self.overlap_tokens:
                        break
                    overlap.insert(0, prev)
                    overlap_tokens += prev_tokens
                current = overlap
                current_tokens = overlap_tokens
            current.append(unit)
            current_tokens += unit_tokens
        if current:
            tail = "".join(current).strip()
            if tail:
                children.append(tail)
        return [c for c in children if c]
