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
