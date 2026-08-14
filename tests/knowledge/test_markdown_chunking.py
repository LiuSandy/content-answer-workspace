import pytest
from app.services.rag.chunking import ParentChildChunker


def test_parent_child_chunker():
    chunker = ParentChildChunker(parent_max_tokens=200, child_max_tokens=50, overlap_tokens=10)
    sample_text = "Paragraph 1: " + "A" * 80 + "\n\nParagraph 2: " + "B" * 80 + "\n\nParagraph 3: " + "C" * 80

    results = chunker.chunk(sample_text)
    assert len(results) > 0
    for r in results:
        assert len(r.parent_content) > 0
        assert len(r.child_chunks) > 0


def test_heading_path_populated():
    chunker = ParentChildChunker()
    md = (
        "# 第一章\n\n开头段落。\n\n"
        "## 小节甲\n\n小节甲的内容。\n\n"
        "## 小节乙\n\n小节乙的内容。\n\n"
        "# 第二章\n\n第二章内容。\n"
    )
    results = chunker.chunk(md)
    paths = [r.heading_path for r in results]
    assert "第一章" in paths
    assert "第一章 > 小节甲" in paths
    assert "第一章 > 小节乙" in paths
    assert "第二章" in paths


def test_parent_never_crosses_headings():
    # 即使内容很短能塞进一个父块，不同章节也必须分属不同父块
    chunker = ParentChildChunker(parent_max_tokens=10000)
    md = "# A\n\n甲内容。\n\n# B\n\n乙内容。\n"
    results = chunker.chunk(md)
    assert len(results) == 2
    assert "甲内容" in results[0].parent_content
    assert "乙内容" in results[1].parent_content


def test_children_split_at_sentence_boundary():
    chunker = ParentChildChunker(parent_max_tokens=1000, child_max_tokens=30, overlap_tokens=5)
    sentences = "".join(f"这是第{i}句测试内容，用来验证切分。" for i in range(10))
    results = chunker.chunk(sentences)
    assert len(results) == 1
    children = results[0].child_chunks
    assert len(children) > 1
    # 除硬切场景外，子块应在句子终结符处结束
    for child in children:
        assert child.rstrip()[-1] in "。！？；!?;."


def test_code_fence_heading_not_parsed():
    chunker = ParentChildChunker()
    md = "# 真标题\n\n```python\n# 这是注释不是标题\nprint(1)\n```\n"
    results = chunker.chunk(md)
    assert all("这是注释" not in r.heading_path for r in results)
    assert any(r.heading_path == "真标题" for r in results)
