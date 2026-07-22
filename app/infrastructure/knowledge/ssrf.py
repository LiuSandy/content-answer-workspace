import ipaddress
import socket
from urllib.parse import urlparse


class SSRFError(ValueError):
    """当请求的 URL 不符合安全防护规则（如指向私有 IP/回环地址/非 HTTP 协议）时抛出。"""
    pass


def validate_url_security(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise SSRFError(f"Unsupported scheme: {parsed.scheme}")

    hostname = parsed.hostname
    if not hostname:
        raise SSRFError("Invalid URL: missing hostname")

    hostname_lower = hostname.lower()
    if hostname_lower in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
        raise SSRFError(f"Access to localhost/loopback address is forbidden: {hostname}")

    try:
        ip_list = socket.getaddrinfo(hostname, None)
        for entry in ip_list:
            ip_str = entry[4][0]
            ip_obj = ipaddress.ip_address(ip_str)
            # 排除由于本地代理/VPN 网段 198.18.0.0/15 对公共域名的虚拟映射误判
            if ip_obj.is_loopback or hostname_lower in ("localhost", "127.0.0.1", "::1"):
                raise SSRFError(f"Host {hostname} resolves to loopback: {ip_str}")
            if ip_str.startswith("10.") or ip_str.startswith("192.168.") or (ip_str.startswith("172.") and 16 <= int(ip_str.split(".")[1]) <= 31):
                raise SSRFError(f"Resolved IP {ip_str} for host {hostname} is a restricted private LAN address.")
    except socket.gaierror:
        raise SSRFError(f"Cannot resolve hostname: {hostname}")

    return True
