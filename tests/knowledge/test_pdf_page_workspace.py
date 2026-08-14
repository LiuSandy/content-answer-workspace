from pathlib import Path
from uuid import uuid4

import fitz

from app.infrastructure.knowledge.pdf_pages import PdfPageWorkspace, strip_markdown_front_matter


def _make_pdf(path: Path, pages: int = 3) -> None:
    document = fitz.open()
    for page_number in range(1, pages + 1):
        page = document.new_page()
        page.insert_text((50, 50), f"Page {page_number}")
    document.save(path)
    document.close()


def test_extracts_exactly_one_page_and_cleans_temporary_file(tmp_path: Path):
    source = tmp_path / "large.pdf"
    _make_pdf(source)
    workspace = PdfPageWorkspace(tmp_path / "work", uuid4())

    single = workspace.extract_single_page(source, 2)
    with fitz.open(single) as document:
        assert len(document) == 1
        assert "Page 2" in document[0].get_text()

    workspace.remove_temporary_page(2)
    assert not single.exists()


def test_merges_pages_in_order_and_inserts_failed_placeholder(tmp_path: Path):
    workspace = PdfPageWorkspace(tmp_path / "work", uuid4())
    workspace.save_page_markdown(3, "third")
    workspace.save_page_markdown(1, "first")

    merged = workspace.merge_pages(3, {2})

    assert merged.index("first") < merged.index("第 2 页识别失败") < merged.index("third")
    assert "<!-- source-page: 1 -->" in merged
    assert "<!-- source-page: 3 -->" in merged


def test_strips_converter_front_matter():
    assert strip_markdown_front_matter("---\ndoc_id: x\n---\n\nbody") == "body"
