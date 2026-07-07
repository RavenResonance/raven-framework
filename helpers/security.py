# ================================================================
# Raven Framework — security helpers
# ================================================================

"""Shared validation helpers for app IDs, paths, and media URLs."""

from __future__ import annotations

import ipaddress
import re
import socket
from urllib.parse import urlparse

_SAFE_APP_ID_RE = re.compile(r"^[a-zA-Z0-9_-]+$")

_BLOCKED_HOSTNAMES = frozenset(
    {
        "localhost",
        "localhost.localdomain",
        "metadata.google.internal",
    }
)


def is_valid_app_id(app_id: str) -> bool:
    """Return True if app_id is safe for use in filesystem paths."""
    return bool(app_id and _SAFE_APP_ID_RE.fullmatch(app_id))


def resolve_under_root(root, subpath: str):
    """
    Resolve root / subpath and verify the result stays under root.

    Raises ValueError when app_id is invalid or escapes root.
    """
    from pathlib import Path

    root_path = Path(root).resolve()
    if not is_valid_app_id(subpath):
        raise ValueError(f"invalid app_id: {subpath!r}")
    resolved = (root_path / subpath).resolve()
    try:
        resolved.relative_to(root_path)
    except ValueError as exc:
        raise ValueError(f"app_id escapes sandbox: {subpath!r}") from exc
    return resolved


def _ip_blocked(addr: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return (
        addr.is_loopback
        or addr.is_private
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
    )


def _hostname_blocked(hostname: str) -> bool:
    host = hostname.strip().lower().rstrip(".")
    if not host:
        return True
    if host in _BLOCKED_HOSTNAMES:
        return True
    if host.endswith(".localhost"):
        return True
    return False


def _resolve_host_ips(hostname: str) -> list:
    ips = []
    try:
        for family, _, _, _, sockaddr in socket.getaddrinfo(hostname, None):
            if family == socket.AF_INET:
                ips.append(ipaddress.ip_address(sockaddr[0]))
            elif family == socket.AF_INET6:
                ips.append(ipaddress.ip_address(sockaddr[0]))
    except OSError:
        return []
    return ips


def is_safe_media_url(url: str) -> bool:
    """
    Return True if url is an http(s) URL that does not target private/local hosts.

    Used by MediaViewer before downloading remote media.
    """
    if not url or not isinstance(url, str):
        return False
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https"):
        return False
    hostname = parsed.hostname
    if not hostname:
        return False
    if _hostname_blocked(hostname):
        return False
    # Literal IP in URL
    try:
        addr = ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        return not _ip_blocked(addr)
    # Resolve hostname and reject if any address is private/local. Fail
    # closed (blocked) if resolution returns nothing — an unresolvable host
    # must not be treated as safe.
    resolved_ips = _resolve_host_ips(hostname)
    if not resolved_ips:
        return False
    for addr in resolved_ips:
        if _ip_blocked(addr):
            return False
    return True
