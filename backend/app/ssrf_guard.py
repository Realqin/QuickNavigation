"""SSRF 防护工具。

提供 URL 校验：禁止访问私有 IP 段、回环、链路本地、云元数据地址等，
避免服务端请求伪造（SSRF）攻击。适用于通用 HTTP 代理类接口。

注意：连接测试类接口（数据库/K8s 连接测试）本身需要访问用户配置的内网地址，
不应使用本模块的严格校验，应通过鉴权 + 审计日志控制风险。
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

# 私有 / 保留 IP 段判断
_BLOCKED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),  # 回环
    ipaddress.ip_network("10.0.0.0/8"),  # 私有 A
    ipaddress.ip_network("172.16.0.0/12"),  # 私有 B
    ipaddress.ip_network("192.168.0.0/16"),  # 私有 C
    ipaddress.ip_network("169.254.0.0/16"),  # 链路本地（含云元数据 169.254.169.254）
    ipaddress.ip_network("0.0.0.0/8"),  # 本网络
    ipaddress.ip_network("100.64.0.0/10"),  # 运营商级 NAT
    ipaddress.ip_network("::1/128"),  # IPv6 回环
    ipaddress.ip_network("fc00::/7"),  # IPv6 私有
    ipaddress.ip_network("fe80::/10"),  # IPv6 链路本地
]


class SsrfViolation(ValueError):
    """URL 违反 SSRF 策略。"""


def _is_blocked_ip(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return True  # 无法解析为 IP 视为非法
    for network in _BLOCKED_NETWORKS:
        if ip in network:
            return True
    return False


def _resolve_host_ips(host: str) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return []
    return list({info[4][0] for info in infos})


def assert_safe_url(url: str, *, allow_loopback: bool = False) -> None:
    """校验 URL 是否符合 SSRF 策略，违规抛出 SsrfViolation。

    - 仅允许 http/https
    - 禁止私有/回环/链路本地/保留 IP
    - 解析域名后对所有 A/AAAA 记录校验（防 DNS rebinding 初步防护）
    """
    target = (url or "").strip()
    if not target:
        raise SsrfViolation("URL 不能为空")

    parsed = urlparse(target)
    scheme = (parsed.scheme or "").lower()
    if scheme not in {"http", "https"}:
        raise SsrfViolation("仅支持 http/https 协议")
    if not parsed.netloc:
        raise SsrfViolation("URL 缺少主机名")

    host = parsed.hostname or ""
    if not host:
        raise SsrfViolation("URL 缺少主机名")

    # 如果 host 本身就是 IP，直接校验
    try:
        ipaddress.ip_address(host)
        if _is_blocked_ip(host) and not (allow_loopback and host in {"127.0.0.1", "::1"}):
            raise SsrfViolation(f"禁止访问的目标地址：{host}")
    except ValueError:
        # 域名：解析后校验所有 IP
        ips = _resolve_host_ips(host)
        if not ips:
            raise SsrfViolation(f"无法解析主机名：{host}")
        for ip in ips:
            if _is_blocked_ip(ip) and not (allow_loopback and ip in {"127.0.0.1", "::1"}):
                raise SsrfViolation(f"主机 {host} 解析到禁止访问的地址：{ip}")
