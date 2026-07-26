"""SSRF 防护：URL 导入的安全校验与安全抓取。

单独成模块是为了让"哪些地址不可访问"的安全策略只存在一处，
路由层只调用 fetch_url_safely，不自行拼装 httpx 请求。
"""
import ipaddress
import socket
from urllib.parse import urlparse, urljoin

import httpx


class SSRFError(ValueError):
    """当请求的 URL 不符合安全防护规则（如指向私有 IP/回环地址/非 HTTP 协议）时抛出。"""
    pass


# 单次导入允许的最大响应体（防止超大响应打爆内存）
DEFAULT_MAX_RESPONSE_BYTES = 10 * 1024 * 1024
# 手动跟随重定向的最大跳数（每一跳都重新做安全校验）
MAX_REDIRECTS = 5


# 本地代理（Clash/Surge 等）fake-IP 模式会把公网域名虚拟映射到
# 基准测试保留网段 198.18.0.0/15；该网段不属于内网路由范围，予以豁免，
# 否则开启代理的开发机上所有 URL 导入都会被误拦。
_FAKE_IP_PROXY_RANGE = ipaddress.ip_network("198.18.0.0/15")


def _assert_ip_allowed(ip_str: str, hostname: str) -> None:
    """拒绝一切非公网地址。

    统一用 ipaddress 的属性判断（对 IPv4/IPv6 同时生效），
    而不是脆弱的字符串前缀匹配——后者会漏掉 link-local（含云元数据
    端点 169.254.169.254）、CGNAT、IPv6 ULA 等网段。
    """
    ip_obj = ipaddress.ip_address(ip_str)
    # IPv4-mapped IPv6（::ffff:10.0.0.1）按映射后的 IPv4 判断
    if isinstance(ip_obj, ipaddress.IPv6Address) and ip_obj.ipv4_mapped:
        ip_obj = ip_obj.ipv4_mapped
    if isinstance(ip_obj, ipaddress.IPv4Address) and ip_obj in _FAKE_IP_PROXY_RANGE:
        return
    # is_global 为 False 即覆盖 loopback / private / link-local /
    # reserved / CGNAT(100.64.0.0/10) / unspecified 等全部内部网段
    if not ip_obj.is_global or ip_obj.is_multicast:
        raise SSRFError(
            f"Host {hostname} resolves to non-public address {ip_str}, access forbidden"
        )


def validate_url_security(url: str) -> bool:
    """校验 URL 是否允许抓取：仅 http(s)，且解析出的所有 IP 必须是公网地址。"""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise SSRFError(f"Unsupported scheme: {parsed.scheme}")

    hostname = parsed.hostname
    if not hostname:
        raise SSRFError("Invalid URL: missing hostname")

    try:
        ip_list = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        raise SSRFError(f"Cannot resolve hostname: {hostname}")

    for entry in ip_list:
        _assert_ip_allowed(entry[4][0], hostname)

    return True


async def fetch_url_safely(
    url: str,
    max_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
    timeout: float = 30.0,
) -> str:
    """安全抓取 URL 文本内容。

    禁用 httpx 自动重定向，改为手动逐跳跟随并对每一跳重新做
    validate_url_security——防止公网域名 302 跳转到内网/元数据端点绕过校验。
    响应体流式读取并限制在 max_bytes 内，超限即中断。
    """
    current_url = url
    async with httpx.AsyncClient(follow_redirects=False, timeout=timeout) as client:
        for _ in range(MAX_REDIRECTS + 1):
            validate_url_security(current_url)
            async with client.stream("GET", current_url) as response:
                if response.status_code in (301, 302, 303, 307, 308):
                    location = response.headers.get("location")
                    if not location:
                        raise SSRFError("Redirect response missing Location header")
                    current_url = urljoin(current_url, location)
                    continue
                response.raise_for_status()
                chunks: list[bytes] = []
                total = 0
                async for chunk in response.aiter_bytes():
                    total += len(chunk)
                    if total > max_bytes:
                        raise SSRFError(
                            f"Response exceeds max size of {max_bytes} bytes"
                        )
                    chunks.append(chunk)
                encoding = response.charset_encoding or "utf-8"
                return b"".join(chunks).decode(encoding, errors="replace")
    raise SSRFError(f"Too many redirects (>{MAX_REDIRECTS}) for url: {url}")
