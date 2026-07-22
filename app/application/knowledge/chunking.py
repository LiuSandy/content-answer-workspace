from dataclasses import dataclass
from typing import List

@dataclass
class ChunkResult:
    parent_content: str
    child_chunks: List[str]

class ParentChildChunker:
    def __init__(self, parent_max_tokens: int = 1200, child_max_tokens: int = 350, overlap_tokens: int = 50):
        self.parent_max_tokens = parent_max_tokens
        self.child_max_tokens = child_max_tokens
        self.overlap_tokens = overlap_tokens

    def chunk(self, markdown_text: str) -> List[ChunkResult]:
        paragraphs = [p.strip() for p in markdown_text.split("\n\n") if p.strip()]
        if not paragraphs:
            return []

        results = []
        current_parent = []
        current_len = 0

        for p in paragraphs:
            p_len = len(p)
            if current_len + p_len > self.parent_max_tokens and current_parent:
                parent_str = "\n\n".join(current_parent)
                children = self._slice_children(parent_str)
                results.append(ChunkResult(parent_content=parent_str, child_chunks=children))
                current_parent = [p]
                current_len = p_len
            else:
                current_parent.append(p)
                current_len += p_len

        if current_parent:
            parent_str = "\n\n".join(current_parent)
            children = self._slice_children(parent_str)
            results.append(ChunkResult(parent_content=parent_str, child_chunks=children))

        return results

    def _slice_children(self, parent_text: str) -> List[str]:
        if len(parent_text) <= self.child_max_tokens:
            return [parent_text]
        
        children = []
        start = 0
        step = self.child_max_tokens - self.overlap_tokens
        while start < len(parent_text):
            end = start + self.child_max_tokens
            children.append(parent_text[start:end])
            start += step
        return children
