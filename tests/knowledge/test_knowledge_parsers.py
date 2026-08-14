import pytest
from app.infrastructure.files.parsers import MarkdownParser, TextParser, HtmlCleanerParser


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


def test_pdf_splitter():
    import fitz
    from app.infrastructure.files.parsers import PdfSplitter

    # 创建一个 5 页的测试 PDF
    doc = fitz.open()
    for i in range(5):
        page = doc.new_page()
        page.insert_text((50, 50), f"Page {i+1}")
    pdf_bytes = doc.tobytes()
    doc.close()

    # 设置 max_pages = 2，预期切分为 3 个小 PDF (2页 + 2页 + 1页)
    splitter = PdfSplitter(max_pages=2, max_bytes=10 * 1024 * 1024)
    chunks = splitter.inspect_and_split(pdf_bytes)

    assert len(chunks) == 3
    # 验证第一个 chunk 有 2 页
    doc1 = fitz.open(stream=chunks[0], filetype="pdf")
    assert len(doc1) == 2
    doc1.close()
    # 验证第三个 chunk 有 1 页
    doc3 = fitz.open(stream=chunks[2], filetype="pdf")
    assert len(doc3) == 1
    doc3.close()
