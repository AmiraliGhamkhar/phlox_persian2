"""SSRF guard for user-supplied URLs fetched server-side.

Endpoints such as ``/api/config/validate-url`` and the vision-capability probe
fetch arbitrary URLs configured by the user. Local/LAN model servers (Ollama,
llama.cpp) are a legitimate target, so loopback and RFC1918 ranges stay
allowed — but cloud metadata (link-local), broadcast, reserved and multicast
targets are blocked. Scheme is restricted to http/https.
"""

import ipaddress
import logging
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)

ALLOWED_SCHEMES = {"http", "https"}


def _blocked_reason(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> str | None:
    """Return a reason string if this resolved address must not be fetched."""
    # Loopback and private ranges are intentionally allowed (local model
    # servers are the primary use case). Everything below is not.
    if ip.is_link_local:  # 169.254.0.0/16, fe80::/10 — cloud metadata lives here
        return "link-local addresses are blocked (cloud metadata)"
    if ip.is_unspecified:  # 0.0.0.0 / ::
        return "unspecified address"
    if ip.is_multicast:
        return "multicast address"
    if ip.is_reserved:
        return "reserved address"
    if ip.is_loopback:
        return None  # explicitly allowed
    return None


def validate_fetch_url(url: str) -> None:
    """Raise ValueError if the URL must not be fetched by the server.

    Checks the scheme and resolves the host, rejecting destinations whose
    resolved addresses are link-local/unspecified/multicast/reserved.
    Callers convert ValueError into a 4xx response.
    """
    if not url or not url.strip():
        raise ValueError("URL is empty")

    try:
        parts = urlsplit(url.strip())
    except ValueError as e:
        raise ValueError("URL could not be parsed") from e

    if parts.scheme.lower() not in ALLOWED_SCHEMES:
        raise ValueError("Only http:// and https:// URLs are allowed")

    host = parts.hostname
    if not host:
        raise ValueError("URL has no host")

    # Reject obviously non-domain hosts early (credentials in URL, etc.)
    if "@" in (parts.netloc or ""):
        raise ValueError("URLs with embedded credentials are not allowed")

    try:
        addr_infos = socket_getaddrinfo(host)
    except OSError as e:
        raise ValueError(f"Host could not be resolved: {host}") from e

    for _family, _type, _proto, _canonname, sockaddr in addr_infos:
        try:
            ip = ipaddress.ip_address(sockaddr[0])
        except ValueError:  # pragma: no cover - getaddrinfo returns IPs
            continue
        reason = _blocked_reason(ip)
        if reason:
            raise ValueError(f"Blocked: {host} resolves to {ip} ({reason})")


def socket_getaddrinfo(host: str, port: int | None = None):
    """Resolve ``host`` (kept as a tiny indirection for testability)."""
    import socket

    return socket.getaddrinfo(host, port)
