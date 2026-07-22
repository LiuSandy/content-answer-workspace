from dataclasses import dataclass, field
from datetime import datetime, timezone
import re
from bs4 import BeautifulSoup
import markdownify


@dataclass
class ParsedMarkdown:
    markdown: str
    confidence: float = 1.0
    warnings: list[str] = field(default_factory=list)


class MarkdownParser:
    async def parse_text(self, text: str, doc_id: str, source_type: str = "markdown") -> ParsedMarkdown:
        cleaned = text.strip()
        now_str = datetime.now(timezone.utc).isoformat()
        front_matter = f"---\ndoc_id: {doc_id}\nsource_type: {source_type}\nconverted_at: {now_str}\n---\n\n"
        if not cleaned.startswith("---"):
            final_md = front_matter + cleaned
        else:
            final_md = cleaned
        return ParsedMarkdown(markdown=final_md, confidence=1.0)


class TextParser:
    async def parse_text(self, text: str, doc_id: str, source_type: str = "text") -> ParsedMarkdown:
        cleaned = text.strip()
        now_str = datetime.now(timezone.utc).isoformat()
        front_matter = f"---\ndoc_id: {doc_id}\nsource_type: {source_type}\nconverted_at: {now_str}\n---\n\n"
        return ParsedMarkdown(markdown=front_matter + cleaned, confidence=1.0)


class HtmlCleanerParser:
    async def parse_html(self, html: str, doc_id: str, source_url: str = "") -> ParsedMarkdown:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "iframe", "noscript"]):
            tag.decompose()

        body = soup.body if soup.body else soup
        converted = markdownify.markdownify(str(body), heading_style="ATX").strip()
        # 清理多余空行
        cleaned_md = re.sub(r"\n{3,}", "\n\n", converted)

        now_str = datetime.now(timezone.utc).isoformat()
        front_matter = f"---\ndoc_id: {doc_id}\nsource_type: url\nsource_url: {source_url}\nconverted_at: {now_str}\n---\n\n"
        return ParsedMarkdown(markdown=front_matter + cleaned_md, confidence=1.0)
