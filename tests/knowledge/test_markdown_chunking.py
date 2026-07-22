import pytest
from app.application.knowledge.chunking import MarkdownChunker, ChunkResult


def test_markdown_parent_child_chunking():
    chunker = MarkdownChunker(parent_max_tokens=200, child_max_tokens=50, overlap_tokens=10)
    markdown = """# Section 1
This is paragraph 1 with some details.

## Subsection 1.1
This is paragraph 2 with detailed technical explanations about algorithmic steps.
    """
    chunks = chunker.chunk_markdown(markdown)
    assert len(chunks) > 0
    parent_chunks = [c for c in chunks if c.chunk_type == "parent"]
    child_chunks = [c for c in chunks if c.chunk_type == "child"]
    assert len(parent_chunks) >= 1
    assert len(child_chunks) >= 1
    # 子块包含指向父块的 parent_index / reference
    for child in child_chunks:
        assert child.parent_index is not None
