import pytest
from app.infrastructure.files.ssrf import validate_url_security, SSRFError


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


def test_ssrf_blocks_metadata_and_internal_ranges():
    # 云元数据端点（link-local）必须被拦截
    with pytest.raises(SSRFError):
        validate_url_security("http://169.254.169.254/latest/meta-data/")

    # CGNAT 网段
    with pytest.raises(SSRFError):
        validate_url_security("http://100.64.0.1/")

    # 10.0.0.0/8 私网
    with pytest.raises(SSRFError):
        validate_url_security("http://10.1.2.3/")

    # IPv6 回环与 link-local
    with pytest.raises(SSRFError):
        validate_url_security("http://[::1]/")
    with pytest.raises(SSRFError):
        validate_url_security("http://[fe80::1]/")

    # IPv4-mapped IPv6 绕过尝试
    with pytest.raises(SSRFError):
        validate_url_security("http://[::ffff:192.168.1.1]/")
