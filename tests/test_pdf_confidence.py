"""confidence estimator 与 PDF 转换链路的单元覆盖。

只覆盖高风险逻辑:启发式置信度函数的边界与基线行为,不依赖 MinerU 远端。
"""
from app.infrastructure.files.parsers import _estimate_pdf_confidence, ParsedMarkdown


def _norm_pages(text_len: int, pages: int, density_full: int = 500) -> float:
    return text_len / pages / density_full


def test_empty_markdown_returns_zero():
    assert _estimate_pdf_confidence("", 10) == 0.0


def test_rich_text_pdf_has_high_confidence():
    md = "x" * 5000  # 5000 字符
    pages = 10
    # 密度=500/页=满分1.0,纯净度1.0 => 0.7*1+0.3*1=1.0
    assert _estimate_pdf_confidence(md, pages) == 1.0


def test_scan_only_pdf_low_density_lowered():
    # 10 页只识别出 50 字符,密度极低
    md = "a" * 50
    pages = 10
    score = _estimate_pdf_confidence(md, pages)
    # 主要是密度项拉低
    assert 0.0 < score < 0.7


def test_replacement_chars_lower_confidence():
    md_clean = "x" * 5000
    md_noisy = "x" * 2500 + "\ufffd" * 2500  # 一半替换字符
    pages = 10
    clean_score = _estimate_pdf_confidence(md_clean, pages)
    noisy_score = _estimate_pdf_confidence(md_noisy, pages)
    assert noisy_score < clean_score


def test_no_page_info_falls_back_to_purity_only():
    md = "x" * 10  # 文本很短
    score = _estimate_pdf_confidence(md, 0)
    # 无页数信息时只用纯净度:无替换字符 => 1.0
    assert score == 1.0


def test_score_clamped_to_unit():
    md = "x" * 1000000  # 超大文本
    pages = 1
    assert _estimate_pdf_confidence(md, pages) == 1.0


def test_parsedmarkdown_defaults():
    pm = ParsedMarkdown(markdown="# hi")
    assert pm.confidence == 1.0
    assert pm.warnings == []