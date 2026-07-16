"""Safety checks for outbound HTTP URLs."""
from __future__ import annotations

import ipaddress
from urllib.parse import urlparse

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address


class UnsafeURLError(ValueError):
    """Raised when an outbound URL targets an unsafe location."""


_ALLOWED_SCHEMES = {"http", "https"}
_LOCAL_HOSTNAMES = {"localhost", "localhost.localdomain"}


def ensure_public_http_url(url: str) -> str:
    """
    Validate that a URL is safe for outbound HTTP access.

    The check is intentionally DNS-free: it rejects obvious local, private, and
    metadata IP targets without resolving public hostnames.
    """
    cleaned_url = (url or "").strip()
    if not cleaned_url:
        raise UnsafeURLError("URL 不能为空")

    parsed = urlparse(cleaned_url)
    if parsed.scheme.lower() not in _ALLOWED_SCHEMES:
        raise UnsafeURLError("仅支持 HTTP/HTTPS URL")
    if not parsed.netloc or not parsed.hostname:
        raise UnsafeURLError("URL 缺少主机名")
    if parsed.username or parsed.password:
        raise UnsafeURLError("URL 不能包含用户名或密码")

    hostname = parsed.hostname.strip(".").lower()
    if hostname in _LOCAL_HOSTNAMES or hostname.endswith(".localhost") or hostname.endswith(".local"):
        raise UnsafeURLError("拒绝访问本机或局域网地址")

    try:
        ip = ipaddress.ip_address(hostname)
    except ValueError:
        if _parse_ipv4_alias(hostname) is not None:
            raise UnsafeURLError("拒绝非标准 IP 地址写法")
        return cleaned_url

    if _is_blocked_ip(ip):
        raise UnsafeURLError("拒绝访问内网、本机、链路本地或保留地址")

    return cleaned_url


def _is_blocked_ip(ip: IPAddress) -> bool:
    mapped_ip = getattr(ip, "ipv4_mapped", None)
    if mapped_ip is not None:
        return _is_blocked_ip(mapped_ip)

    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def _parse_ipv4_alias(hostname: str) -> ipaddress.IPv4Address | None:
    if hostname.isdigit():
        return _ipv4_from_int(hostname, 10)

    lowered = hostname.lower()
    if lowered.startswith("0x"):
        return _ipv4_from_int(lowered[2:], 16)

    parts = lowered.split(".")
    if len(parts) != 4:
        return None

    parsed_parts: list[int] = []
    used_non_decimal = False
    for part in parts:
        if not part:
            return None

        try:
            if part.startswith("0x"):
                parsed_part = int(part[2:], 16)
                used_non_decimal = True
            elif len(part) > 1 and part.startswith("0") and part.isdigit():
                parsed_part = int(part, 8)
                used_non_decimal = True
            elif part.isdigit():
                parsed_part = int(part, 10)
            else:
                return None
        except ValueError:
            return None

        if parsed_part > 255:
            return None
        parsed_parts.append(parsed_part)

    if not used_non_decimal:
        return None

    result = ipaddress.ip_address(".".join(str(part) for part in parsed_parts))
    if isinstance(result, ipaddress.IPv4Address):
        return result
    return None


def _ipv4_from_int(value: str, base: int) -> ipaddress.IPv4Address | None:
    try:
        parsed_value = int(value, base)
    except ValueError:
        return None

    if not 0 <= parsed_value <= 0xFFFFFFFF:
        return None

    result = ipaddress.ip_address(parsed_value)
    if isinstance(result, ipaddress.IPv4Address):
        return result
    return None
