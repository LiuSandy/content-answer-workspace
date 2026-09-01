"""Agent 工具安全测试（roadmap R2 Step 5）。

覆盖：初始 URL 拒绝内网/环回/云元数据、非 http(s) 协议拒绝、响应大小上限，
以及代码解释器默认不注册。
"""
from __future__ import annotations

import httpx
import pytest

from app.shared.agent import security
from app.plugins.tools.builtin import ALL_TOOLS
from app.platform.files.ssrf import SSRFError


def test_code_interpreter_not_in_default_tools():
    """默认工具集合不包含任意代码执行（阶段门禁）。"""
    names = {getattr(t, "name", "") for t in ALL_TOOLS}
    assert "code_interpreter" not in names
    assert not any("code" in name for name in names)


def test_zhihu_search_is_builtin_without_agent_reach_config(monkeypatch, tmp_path):
    from app.plugins.tools import builtin as tools

    monkeypatch.setattr(tools, "_AGENT_REACH_CONFIG", tmp_path / "missing.json")

    names = {getattr(tool, "name", "") for tool in tools._build_all_tools()}

    assert "zhihu_search" in names


def test_security_rejects_private_loopback_and_metadata():
    bad_urls = [
        "http://127.0.0.1:8080/admin",
        "http://localhost/admin",
        "http://10.0.0.8/x",
        "http://192.168.1.1/x",
        "http://100.64.0.1/x",
        "http://169.254.169.254/latest/meta-data/",
        "http://[::1]/x",
    ]
    for bad in bad_urls:
        with pytest.raises(SSRFError):
            security.validate_web_fetch_url(bad)


def test_security_rejects_non_http_scheme():
    for bad in ("file:///etc/passwd", "ftp://example.com/a", "javascript:alert(1)"):
        with pytest.raises(SSRFError):
            security.validate_web_fetch_url(bad)


@pytest.mark.asyncio
async def test_web_fetch_tool_refuses_internal_url_without_network():
    """web_fetch 对内网 URL 直接拒绝，不发起网络请求。"""
    from app.plugins.tools.builtin.web_fetch import web_fetch

    result = await web_fetch.ainvoke({"url": "http://127.0.0.1:8080/admin"})
    assert "拒绝" in result or "forbidden" in result.lower() or "SSRF" in result


@pytest.mark.asyncio
async def test_fetch_web_page_blocks_redirect_hop_to_internal(monkeypatch):
    """重定向的每一跳都重新做安全校验：公网 302 跳到内网必须被拒。"""
    from app.platform.files import ssrf as ssrf_mod

    calls: list[str] = []

    def spy_validate(url: str) -> bool:
        calls.append(url)
        if "http://169.254.169.254/" in url:
            raise SSRFError("redirect to metadata endpoint")
        return True

    monkeypatch.setattr(ssrf_mod, "validate_url_security", spy_validate)

    class _RedirectResp:
        status_code = 302
        headers = {"location": "http://169.254.169.254/latest/meta-data/"}
        charset_encoding = "utf-8"

        def raise_for_status(self):
            return None

        async def aiter_bytes(self):
            yield b""

    class _Ctx:
        async def __aenter__(self):
            return _RedirectResp()

        async def __aexit__(self, *a):
            return False

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        def stream(self, method, url):
            return _Ctx()

    monkeypatch.setattr(httpx, "AsyncClient", _Client)

    with pytest.raises(SSRFError, match="redirect to metadata"):
        await security.fetch_web_page("https://public.example.com/a")

    # 至少校验了初始 URL 与重定向目标两跳
    assert len(calls) >= 2
    assert "public.example.com" in calls[0]


@pytest.mark.asyncio
async def test_fetch_web_page_enforces_size_cap(monkeypatch):
    """响应超过大小上限即中断，防止超大响应打爆内存。"""
    class _Resp:
        status_code = 200
        headers = {}
        charset_encoding = "utf-8"

        def raise_for_status(self):
            return None

        async def aiter_bytes(self):
            yield b"a" * 2048
            yield b"b" * 2048

    class _Ctx:
        async def __aenter__(self):
            return _Resp()

        async def __aexit__(self, *a):
            return False

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        def stream(self, method, url):
            return _Ctx()

    monkeypatch.setattr(httpx, "AsyncClient", _Client)

    with pytest.raises(SSRFError, match="max size"):
        await security.fetch_web_page("https://public.example.com/x", max_bytes=2048)
