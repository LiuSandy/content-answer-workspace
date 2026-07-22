import pytest
from app.infrastructure.knowledge.parsers import MarkdownParser, TextParser, HtmlCleanerParser


@pytest.mark.asyncio
async def test_markdown_parser():
    parser = MarkdownParser()
    raw = "# Title\n\nSome content."
    result = await parser.parse_text(raw, doc_id="doc1", source_type="markdown")
    assert "---" in result.markdown
    assert "doc_id: doc1" in result.markdown
    assert "# Title" in result.markdown


@pytest.mark.asyncio
async def test_text_parser():
    parser = TextParser()
    raw = "Plain text content line 1\nline 2"
    result = await parser.parse_text(raw, doc_id="doc2", source_type="text")
    assert "doc_id: doc2" in result.markdown
    assert "Plain text content line 1" in result.markdown


@pytest.mark.asyncio
async def test_html_cleaner_parser():
    parser = HtmlCleanerParser()
    html = "<html><head><script>alert(1)</script></head><body><h1>Hello</h1><p>World</p></body></html>"
    result = await parser.parse_html(html, doc_id="doc3", source_url="https://example.com")
    assert "alert(1)" not in result.markdown
    assert "# Hello" in result.markdown
    assert "World" in result.markdown
