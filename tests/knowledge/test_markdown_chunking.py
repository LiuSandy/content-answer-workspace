import pytest
from app.application.knowledge.chunking import ParentChildChunker

def test_parent_child_chunker():
    chunker = ParentChildChunker(parent_max_tokens=200, child_max_tokens=50, overlap_tokens=10)
    sample_text = "Paragraph 1: " + "A" * 80 + "\n\nParagraph 2: " + "B" * 80 + "\n\nParagraph 3: " + "C" * 80
    
    results = chunker.chunk(sample_text)
    assert len(results) > 0
    for r in results:
        assert len(r.parent_content) > 0
        assert len(r.child_chunks) > 0
