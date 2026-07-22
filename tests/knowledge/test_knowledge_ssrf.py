import pytest
from app.infrastructure.knowledge.ssrf import validate_url_security, SSRFError


def test_ssrf_validation():
    # 允许合法的外部 URL
    assert validate_url_security("https://example.com/article") is True

    # 拒绝私有 / 本地 URL
    with pytest.raises(SSRFError):
        validate_url_security("http://localhost:8000")

    with pytest.raises(SSRFError):
        validate_url_security("http://127.0.0.1/admin")

    with pytest.raises(SSRFError):
        validate_url_security("http://192.168.1.1")

    with pytest.raises(SSRFError):
        validate_url_security("file:///etc/passwd")

    with pytest.raises(SSRFError):
        validate_url_security("ftp://example.com/file")
