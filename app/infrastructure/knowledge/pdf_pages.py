from __future__ import annotations

import hashlib
import os
import shutil
from pathlib import Path
from uuid import UUID

import fitz


class PdfPageWorkspace:
    """单页 PDF 临时文件、持久化页面 Markdown 与顺序合并。"""

    def __init__(self, root: Path, job_id: UUID):
        self.root = root.resolve() / str(job_id)
        self.pages_dir = self.root / "pages"
        self.temporary_dir = self.root / "temporary"
        self.pages_dir.mkdir(parents=True, exist_ok=True)
        self.temporary_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def page_count(source_path: Path) -> int:
        with fitz.open(source_path) as document:
            return len(document)

    def extract_single_page(self, source_path: Path, page_number: int) -> Path:
        """只提取一页到临时 PDF；page_number 从 1 开始。"""
        target = self.temporary_dir / f"{page_number:06d}.pdf"
        partial = target.with_suffix(".pdf.tmp")
        with fitz.open(source_path) as source:
            if page_number < 1 or page_number > len(source):
                raise ValueError(f"PDF page out of range: {page_number}")
            page_document = fitz.open()
            try:
                page_document.insert_pdf(source, from_page=page_number - 1, to_page=page_number - 1)
                page_document.save(partial)
            finally:
                page_document.close()
        os.replace(partial, target)
        return target

    def save_page_markdown(self, page_number: int, markdown: str) -> tuple[Path, str]:
        target = self.pages_dir / f"{page_number:06d}.md"
        partial = target.with_suffix(".md.tmp")
        content = markdown.strip()
        with partial.open("w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(partial, target)
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        return target, digest

    def merge_pages(self, total_pages: int, failed_pages: set[int]) -> str:
        sections: list[str] = []
        for page_number in range(1, total_pages + 1):
            marker = f"<!-- source-page: {page_number} -->"
            page_path = self.pages_dir / f"{page_number:06d}.md"
            if page_path.exists() and page_number not in failed_pages:
                body = page_path.read_text(encoding="utf-8").strip()
            else:
                body = f"> 第 {page_number} 页识别失败，请在确认前人工补充。"
            sections.append(f"{marker}\n\n{body}")
        return "\n\n---\n\n".join(sections)

    def remove_temporary_page(self, page_number: int) -> None:
        (self.temporary_dir / f"{page_number:06d}.pdf").unlink(missing_ok=True)
        (self.temporary_dir / f"{page_number:06d}.pdf.tmp").unlink(missing_ok=True)

    def cleanup(self) -> None:
        if self.root.exists():
            shutil.rmtree(self.root)


def strip_markdown_front_matter(markdown: str) -> str:
    stripped = markdown.lstrip()
    if not stripped.startswith("---\n"):
        return markdown.strip()
    end = stripped.find("\n---\n", 4)
    if end < 0:
        return markdown.strip()
    return stripped[end + 5 :].strip()
