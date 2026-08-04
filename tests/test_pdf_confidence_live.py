"""Phase 1.5 · Task 2：真实 PDF conversion_confidence 端到端验证。

用 PyMuPDF 生成真实 PDF 字节流，mock MinerU 远端解析，走完整
`_parse_pdf_to_markdown` 链路（探测页数 → MinerU/本地解析 → estimator 算分），
证明置信度链路在真实 PDF 输入下有真实数据流过：

  - 扫描页模拟 PDF（10 页只识别 50 字符 + 含 U+FFFD）→ confidence < 0.7
  - 富文本 PDF（MinerU 返回 5000 字符干净文本）→ confidence ≥ 0.9
  - MinerU 未配置时降级本地提取，confidence 仍按启发式计算（非硬编码 1.0）

前置条件（spec 7.1 第 3 项）：真实 PDF 验证 conversion_confidence 非 NULL，
低置信度时前端能看到警告。前端警告已在上一轮修复中完成，本测试聚焦后端链路。
"""
from __future__ import annotations

import fitz
import pytest
from unittest.mock import AsyncMock

from app.api.routes.knowledge import _parse_pdf_to_markdown
from app.infrastructure.knowledge.parsers import ParsedMarkdown


def _make_pdf_bytes(num_pages: int = 10) -> bytes:
    """用 PyMuPDF 生成真实 PDF 字节流；不写入内容，模拟纯图像/扫描页。"""
    doc = fitz.open()
    for _ in range(num_pages):
        doc.new_page()
    return doc.tobytes()


def _make_settings(mineru_key: str = "fake-key"):
    """构造带 MinerU 配置的 fake settings。"""
    from app.core.config import KnowledgeSettings
    return KnowledgeSettings(mineru_api_key=mineru_key)


@pytest.mark.asyncio
async def test_scan_like_pdf_with_mineru_returns_low_confidence(monkeypatch):
    """扫描页模拟：MinerU 返回 50 字符 + 替换字符 → confidence < 0.7。"""
    pdf_bytes = _make_pdf_bytes(10)

    async def _fake_single_chunk(_self, _client, _chunk, _filename):
        return "a" * 25 + "\ufffd" * 25  # 50 字符，一半替换字符
    monkeypatch.setattr(
        "app.infrastructure.knowledge.parsers.MinerUCloudParser._parse_single_chunk",
        _fake_single_chunk,
    )

    settings = _make_settings(mineru_key="fake-key")
    pm = await _parse_pdf_to_markdown(pdf_bytes, "scan.pdf", "doc-1", settings)

    assert isinstance(pm, ParsedMarkdown)
    assert pm.confidence < 0.7
    assert pm.confidence > 0.0  # 非零非空，证明链路真实产出
    # 低于阈值时有警告（供前端展示）
    assert any("校对" in w or "质量" in w for w in pm.warnings)


@pytest.mark.asyncio
async def test_rich_text_pdf_with_mineru_returns_high_confidence(monkeypatch):
    """富文本 PDF：MinerU 返回 5000 字符干净文本 → confidence ≥ 0.9。"""
    pdf_bytes = _make_pdf_bytes(10)

    async def _fake_single_chunk(_self, _client, _chunk, _filename):
        return "x" * 5000  # 密度 500/页，纯净
    monkeypatch.setattr(
        "app.infrastructure.knowledge.parsers.MinerUCloudParser._parse_single_chunk",
        _fake_single_chunk,
    )

    settings = _make_settings(mineru_key="fake-key")
    pm = await _parse_pdf_to_markdown(pdf_bytes, "rich.pdf", "doc-2", settings)

    assert pm.confidence >= 0.9
    assert pm.warnings == []  # 无警告


@pytest.mark.asyncio
async def test_local_fallback_still_estimates_confidence(monkeypatch):
    """MinerU 不可用时降级本地提取，confidence 仍按启发式计算（非硬编码 1.0）。

    本地提取（pymupdf4llm）对纯空白页 PDF 返回的 md_text 几乎为空，
    estimator 应给出低分而非 1.0，证明降级路径不再硬编码。
    """
    pdf_bytes = _make_pdf_bytes(10)

    settings = _make_settings(mineru_key="")  # 触发本地降级

    pm = await _parse_pdf_to_markdown(pdf_bytes, "blank.pdf", "doc-3", settings)

    assert isinstance(pm, ParsedMarkdown)
    # 空白页本地提取的 md 文本很短 → density 极低 → confidence < 0.7
    assert pm.confidence < 0.7
    # 关键断言：不再是硬编码 1.0
    assert pm.confidence != 1.0


@pytest.mark.asyncio
async def test_mineru_failure_falls_back_to_local_with_confidence(monkeypatch):
    """MinerU 调用抛异常时降级本地提取，confidence 仍由 estimator 产出。"""
    pdf_bytes = _make_pdf_bytes(10)

    async def _raising_chunk(_self, _client, _chunk, _filename):
        raise RuntimeError("MinerU API down")
    monkeypatch.setattr(
        "app.infrastructure.knowledge.parsers.MinerUCloudParser._parse_single_chunk",
        _raising_chunk,
    )

    settings = _make_settings(mineru_key="fake-key")
    pm = await _parse_pdf_to_markdown(pdf_bytes, "fail.pdf", "doc-4", settings)

    assert isinstance(pm, ParsedMarkdown)
    assert pm.confidence < 0.7  # 空白页降级
    assert pm.confidence != 1.0  # 非硬编码