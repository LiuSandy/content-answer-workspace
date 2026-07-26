import pytest
from app.application.knowledge.context_builder import ContextBuilder, ContextBlock


def test_context_builder_budget_and_labels():
    builder = ContextBuilder(max_tokens=6000)
    blocks = [
        ContextBlock(doc_title="Doc 1", content="Parent chunk 1 content", source_type="pdf"),
        ContextBlock(doc_title="Doc 2", content="Parent chunk 2 content", source_type="markdown"),
    ]
    context_str, sources = builder.build_context(blocks)
    assert "[S1]" in context_str
    assert "[S2]" in context_str
    assert len(sources) == 2
    assert sources[0]["label"] == "[S1]"


def test_context_builder_truncates_over_budget():
    # 预算只够放下第一个 block 时，后续 block 必须被裁剪
    builder = ContextBuilder(max_tokens=50)
    blocks = [
        ContextBlock(doc_title="Doc 1", content="内容" * 40, source_type="pdf"),
        ContextBlock(doc_title="Doc 2", content="内容" * 40, source_type="pdf"),
    ]
    context_str, sources = builder.build_context(blocks)
    assert len(sources) == 1
    assert "[S1]" in context_str
    assert "[S2]" not in context_str


def test_context_builder_first_block_always_included():
    # 即使单个 block 超预算，也必须至少纳入第一个，保证上下文不为空
    builder = ContextBuilder(max_tokens=10)
    blocks = [ContextBlock(doc_title="Doc 1", content="内容" * 100, source_type="pdf")]
    context_str, sources = builder.build_context(blocks)
    assert len(sources) == 1
    assert context_str != ""
