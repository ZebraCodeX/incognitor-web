"""SSRF protection for outbound requests made by the agent / web-form engine.

Resolves the destination host and rejects loopback, private, link-local
(including cloud metadata 169.254.169.254), reserved, multicast and unspecified
addresses. An optional host allowlist (``SENTINEL_ALLOWED_WEBFORM_HOSTS``) can
further restrict which broker domains may be visited.

Note: this blocks the common SSRF vectors but does not fully defend against DNS
rebinding (TOCTOU between resolve and connect). For untrusted egress, run the
browser/HTTP client behind an egress proxy.
"""

import ipaddress
import socket
from urllib.parse import urlparse

from django.conf import settings


class UnsafeURLError(ValueError):
    """Raised when a URL points at a disallowed destination."""


_BLOCKED_V4 = ipaddress.ip_network("169.254.0.0/16")  # link-local / metadata


def _is_disallowed(ip: ipaddress._BaseAddress) -> bool:
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
        or (ip.version == 4 and ip in _BLOCKED_V4)
    )


def validate_outbound_url(url, allowlist=None, resolve=True):
    """Raise :class:`UnsafeURLError` if ``url`` is not safe to fetch."""
    parsed = urlparse(url or "")
    if parsed.scheme not in ("http", "https"):
        raise UnsafeURLError(f"scheme not allowed: {parsed.scheme!r}")
    host = parsed.hostname
    if not host:
        raise UnsafeURLError("missing host")

    if allowlist is None:
        allowlist = getattr(settings, "SENTINEL_ALLOWED_WEBFORM_HOSTS", [])
    if allowlist:
        if not any(host == a or host.endswith("." + a) for a in allowlist):
            raise UnsafeURLError(f"host not in allowlist: {host}")

    if not resolve:
        return url

    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise UnsafeURLError(f"could not resolve host {host}: {exc}") from exc

    for info in infos:
        addr = info[4][0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            raise UnsafeURLError(f"unparseable address {addr}")
        if _is_disallowed(ip):
            raise UnsafeURLError(f"host resolves to disallowed address {addr}")

    return url
