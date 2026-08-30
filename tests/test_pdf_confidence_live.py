"""Phase 1.5 · Task 2：真实 PDF conversion_confidence 端到端验证。

用 PyMuPDF 生成真实 PDF 字节流，mock MinerU 远端解析，走完整
`_parse_pdf_to_markdown` 链路（探测页数 → MinerU/本地解析 → estimator 算分），
证明置信度链路在真实 PDF 输入下有真实数据流过：

  - 扫描页模拟 PDF（10 页只识别 50 字符 + 含 U+FFFD）→ confidence < 0.7
  - 富文本 PDF（MinerU 返回 5000 字符干净文本）→ confidence ≥ 0.9
  - MinerU 未配置时直接抛错，不走本地降级

前置条件（spec 7.1 第 3 项）：真实 PDF 验证 conversion_confidence 非 NULL，
低置信度时前端能看到警告。前端警告已在上一轮修复中完成，本测试聚焦后端链路。
"""
from __future__ import annotations

import fitz
import pytest
from unittest.mock import AsyncMock

from app.api.routes.knowledge import _parse_pdf_to_markdown
from app.infrastructure.files.parsers import ParsedMarkdown


def _make_pdf_bytes(num_pages: int = 10) -> bytes:
    """用 PyMuPDF 生成真实 PDF 字节流；不写入内容，模拟纯图像/扫描页。"""
    doc = fitz.open()
    for _ in range(num_pages):
        doc.new_page()
    return doc.tobytes()


def _make_settings(mineru_key: str = "fake-key"):
    """构造带 MinerU 配置的 fake settings。"""
    from app.config.runtime import KnowledgeSettings
    return KnowledgeSettings(mineru_api_key=mineru_key)


@pytest.mark.asyncio
async def test_scan_like_pdf_with_mineru_returns_low_confidence(monkeypatch):
    """扫描页模拟：MinerU 返回 50 字符 + 替换字符 → confidence < 0.7。"""
    pdf_bytes = _make_pdf_bytes(10)

    async def _fake_single_chunk(_self, _client, _chunk, _filename):
        return "a" * 25 + "\ufffd" * 25  # 50 字符，一半替换字符
    monkeypatch.setattr(
        "app.infrastructure.files.parsers.MinerUCloudParser._parse_single_chunk",
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
        "app.infrastructure.files.parsers.MinerUCloudParser._parse_single_chunk",
        _fake_single_chunk,
    )

    settings = _make_settings(mineru_key="fake-key")
    pm = await _parse_pdf_to_markdown(pdf_bytes, "rich.pdf", "doc-2", settings)

    assert pm.confidence >= 0.9
    assert pm.warnings == []  # 无警告


@pytest.mark.asyncio
async def test_mineru_not_configured_raises():
    """MinerU 未配置时直接失败，不使用本地 PDF 解析。"""
    pdf_bytes = _make_pdf_bytes(10)

    settings = _make_settings(mineru_key="")

    with pytest.raises(RuntimeError, match="MinerU 未配置"):
        await _parse_pdf_to_markdown(pdf_bytes, "blank.pdf", "doc-3", settings)


@pytest.mark.asyncio
async def test_mineru_failure_raises(monkeypatch):
    """MinerU 调用失败时直接抛错，不使用本地 PDF 解析。"""
    pdf_bytes = _make_pdf_bytes(10)

    async def _raising_chunk(_self, _client, _chunk, _filename):
        raise RuntimeError("MinerU API down")
    monkeypatch.setattr(
        "app.infrastructure.files.parsers.MinerUCloudParser._parse_single_chunk",
        _raising_chunk,
    )

    settings = _make_settings(mineru_key="fake-key")
    with pytest.raises(RuntimeError, match="MinerU API down"):
        await _parse_pdf_to_markdown(pdf_bytes, "fail.pdf", "doc-4", settings)
