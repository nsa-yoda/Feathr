"""Safe client identity extraction for rate limiting."""

from __future__ import annotations

import ipaddress
from collections.abc import Mapping


def normalize_client_identity(scope: Mapping[str, object], *, trusted_proxy_hops: int = 0) -> str:
    """Return a canonical peer identity without trusting forwarding by default."""

    peer = _normalize_ip(_peer_host(scope)) or "unknown"
    if trusted_proxy_hops <= 0:
        return peer
    headers = scope.get("headers")
    if not isinstance(headers, list | tuple):
        return peer
    forwarded = None
    try:
        for item in headers:
            if not isinstance(item, tuple) or len(item) != 2:
                return peer
            key, value = item
            if not isinstance(key, bytes) or not isinstance(value, bytes):
                return peer
            if key.lower() == b"x-forwarded-for":
                forwarded = value
                break
    except (TypeError, ValueError):
        return peer
    if not isinstance(forwarded, bytes):
        return peer
    try:
        chain = [_normalize_ip(item.decode("ascii").strip()) for item in forwarded.split(b",")]
    except (UnicodeDecodeError, ValueError):
        return peer
    if not chain or any(item is None for item in chain) or len(chain) != trusted_proxy_hops + 1:
        return peer
    if chain[-1] != peer:
        return peer
    return chain[0] or peer


def _peer_host(scope: Mapping[str, object]) -> str | None:
    client = scope.get("client")
    if isinstance(client, tuple) and client and isinstance(client[0], str):
        return client[0]
    return None


def _normalize_ip(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        return None
