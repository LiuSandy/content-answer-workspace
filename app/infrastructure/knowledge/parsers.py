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


# 启发式 PDF 转换置信度阈值；低于此值时前端候选稿确认页应展示人工校对警告
PDF_CONFIDENCE_DENSITY_FULL = 500  # 每页字符数达到该值视为密度满分
PDF_CONFIDENCE_MIN_PAGES_FOR_DENSITY = 1  # 至少 1 页才计算密度


def _estimate_pdf_confidence(md_text: str, total_pages: int) -> float:
    """启发式估算 PDF 转 Markdown 的置信度（0~1）。

    只依赖已产出的 Markdown 文本与 PDF 页数,不假设 MinerU 响应字段:
    - 文本密度: len(md_text) / total_pages 过低意味着该页大概率是纯图片或解析失败。
    - 替换字符 U+FFFD 及连续不可打印字符占比越高越低。
    最终用 0.7*密度 + 0.3*纯净度加权;无页数信息时仅用纯净度。
    """
    if not md_text:
        return 0.0

    text_len = len(md_text)

    # 纯净度: 1 - 替换字符占比
    replacement_count = md_text.count("\ufffd")
    replacement_ratio = replacement_count / text_len if text_len else 0.0
    purity_score = max(0.0, 1.0 - replacement_ratio)

    if total_pages and total_pages >= PDF_CONFIDENCE_MIN_PAGES_FOR_DENSITY:
        density = text_len / total_pages
        density_score = min(1.0, density / PDF_CONFIDENCE_DENSITY_FULL)
        score = 0.7 * density_score + 0.3 * purity_score
    else:
        score = purity_score

    return max(0.0, min(1.0, score))


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


import asyncio
import httpx
import logging
import fitz

logger = logging.getLogger(__name__)


class PdfSplitter:
    """使用 PyMuPDF (fitz) 检测 PDF 页数与大小，超过阈值时在内存中切分为子 PDF 字节流。"""
    def __init__(self, max_pages: int = 150, max_bytes: int = 150 * 1024 * 1024):
        self.max_pages = max_pages
        self.max_bytes = max_bytes

    def inspect_and_split(self, pdf_bytes: bytes) -> list[bytes]:
        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            total_pages = len(doc)
            total_size = len(pdf_bytes)
        except Exception:
            return [pdf_bytes]

        if total_pages <= self.max_pages and total_size <= self.max_bytes:
            doc.close()
            return [pdf_bytes]

        chunks = []
        for start in range(0, total_pages, self.max_pages):
            end = min(start + self.max_pages, total_pages) - 1
            part_doc = fitz.open()
            part_doc.insert_pdf(doc, from_page=start, to_page=end)
            part_bytes = part_doc.tobytes()
            part_doc.close()
            chunks.append(part_bytes)
        doc.close()
        return chunks if chunks else [pdf_bytes]


class MinerUCloudParser:
    """使用 MinerU 官方云端精准解析 API (v4)，支持自动分卷切片与并发转换。"""
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://mineru.net/api/v4",
        model_version: str = "vlm",
        max_pages_per_chunk: int = 150,
        max_bytes_per_chunk: int = 150 * 1024 * 1024
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model_version = model_version
        self.splitter = PdfSplitter(max_pages=max_pages_per_chunk, max_bytes=max_bytes_per_chunk)

    async def _parse_single_chunk(self, client: httpx.AsyncClient, pdf_bytes: bytes, filename: str) -> str:
        headers = {"Authorization": f"Bearer {self.api_key}"}

        # 步骤 1：申请文件上传预签名 URL
        req_payload = {
            "files": [{"name": filename}],
            "model_version": self.model_version,
            "enable_formula": True,
            "enable_table": True,
        }

        try:
            init_resp = await client.post(
                f"{self.base_url}/file-urls/batch",
                headers=headers,
                json=req_payload,
                timeout=30.0
            )
            init_json = init_resp.json()
            if not init_resp.is_success or (init_json.get("code") != 0 and init_json.get("code") != 200):
                raise ValueError(f"MinerU batch file-urls failed: {init_json}")

            # 安全提取 upload_url 与 batch_id (防止返回元素为 str 而非 dict 导致 'str' object has no attribute 'get')
            data = init_json.get("data")
            batch_id = init_json.get("batch_id")
            upload_url = None

            if isinstance(data, dict):
                batch_id = batch_id or data.get("batch_id") or data.get("task_id")
                file_urls = data.get("file_urls") or data.get("files") or data.get("upload_urls") or []
                if isinstance(file_urls, list) and len(file_urls) > 0:
                    first = file_urls[0]
                    if isinstance(first, str):
                        upload_url = first
                    elif isinstance(first, dict):
                        upload_url = first.get("upload_url") or first.get("url")
                elif isinstance(file_urls, str):
                    upload_url = file_urls
            elif isinstance(data, list) and len(data) > 0:
                first = data[0]
                if isinstance(first, str):
                    upload_url = first
                elif isinstance(first, dict):
                    upload_url = first.get("upload_url") or first.get("url")
                    batch_id = batch_id or first.get("batch_id") or first.get("task_id")

            if not upload_url:
                raise ValueError(f"MinerU returned no upload_url: {init_json}")
        except Exception as e:
            logger.error(f"MinerU API init error: {e}")
            raise

        # 步骤 2：使用 PUT 上传文件字节流至预签名的 upload_url
        try:
            put_resp = await client.put(upload_url, content=pdf_bytes, timeout=120.0)
            if not put_resp.is_success and put_resp.status_code not in (200, 201, 204):
                raise ValueError(f"Failed to upload PDF bytes to MinerU presigned URL, status: {put_resp.status_code}")
        except Exception as e:
            logger.error(f"MinerU OSS upload error: {e}")
            raise

        # 步骤 3：轮询等待解析完成结果
        for poll_idx in range(60):
            await asyncio.sleep(5)
            status_resp = await client.get(f"{self.base_url}/extract-results/batch/{batch_id}", headers=headers, timeout=20.0)
            if not status_resp.is_success:
                status_resp = await client.get(f"{self.base_url}/extract/task/{batch_id}", headers=headers, timeout=20.0)

            status_json = status_resp.json()

            def find_first_val(obj, target_keys):
                if isinstance(obj, dict):
                    for k in target_keys:
                        if k in obj and obj[k]:
                            return obj[k]
                    for v in obj.values():
                        res = find_first_val(v, target_keys)
                        if res:
                            return res
                elif isinstance(obj, list):
                    for elem in obj:
                        res = find_first_val(elem, target_keys)
                        if res:
                            return res
                return None

            state_val = find_first_val(status_json, ["state", "status"])
            state = str(state_val).lower() if state_val else ""
            full_zip_url = find_first_val(status_json, ["full_zip_url", "download_url", "zip_url"])
            md_content = find_first_val(status_json, ["markdown_content", "markdown", "md_content"])

            logger.info("MinerU batch %s poll #%d state: '%s'", batch_id, poll_idx + 1, state)

            if state in ("completed", "success", "done", "finished"):
                # 完成时记录一次完整状态 JSON,以便后续确认 API 是否返回质量字段
                logger.info("MinerU batch %s completed; status_json=%s", batch_id, status_json)
                if md_content and isinstance(md_content, str) and len(md_content.strip()) > 0:
                    return md_content
                if full_zip_url and isinstance(full_zip_url, str):
                    zip_resp = await client.get(full_zip_url, timeout=40.0)
                    import io
                    import zipfile
                    with zipfile.ZipFile(io.BytesIO(zip_resp.content)) as z:
                        for name in z.namelist():
                            if name.endswith(".md"):
                                return z.read(name).decode("utf-8", errors="ignore")
                    return ""
                return ""
            elif state in ("failed", "error"):
                error_msg = status_json.get("msg") or "MinerU task failed"
                raise RuntimeError(f"MinerU task failed: {error_msg}")

        raise TimeoutError("MinerU parsing timed out after 300 seconds")

    async def parse_pdf(self, pdf_bytes: bytes, doc_id: str, filename: str = "document.pdf") -> ParsedMarkdown:
        # 探测总页数,供置信度启发式计算使用
        total_pages = 0
        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            total_pages = len(doc)
            doc.close()
        except Exception:
            logger.warning("Could not detect PDF page count for %s; confidence falls back to purity-only", filename)

        pdf_chunks = self.splitter.inspect_and_split(pdf_bytes)

        async with httpx.AsyncClient() as client:
            if len(pdf_chunks) == 1:
                md_text = await self._parse_single_chunk(client, pdf_chunks[0], filename)
            else:
                logger.info(f"PDF split into {len(pdf_chunks)} chunks for MinerU parsing.")
                tasks = [
                    self._parse_single_chunk(client, chunk_bytes, f"{filename}.part{idx+1}.pdf")
                    for idx, chunk_bytes in enumerate(pdf_chunks)
                ]
                results = await asyncio.gather(*tasks)
                md_text = "\n\n---\n\n".join(results)

        confidence = _estimate_pdf_confidence(md_text, total_pages)
        warnings = []
        if confidence < 0.7:
            warnings.append("PDF 识别质量较低,建议人工校对候选 Markdown 后再确认建立索引")
        now_str = datetime.now(timezone.utc).isoformat()
        front_matter = f"---\ndoc_id: {doc_id}\nsource_type: pdf\nconverted_at: {now_str}\nconverter: mineru_cloud_vlm\n---\n\n"
        final_md = front_matter + md_text.strip()
        return ParsedMarkdown(markdown=final_md, confidence=confidence, warnings=warnings)
