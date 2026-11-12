"""SSRF-safe URL validation and bounded fetching with DNS pinning."""

from __future__ import annotations

from dataclasses import dataclass
import ipaddress
import socket
from urllib.parse import urlparse
from typing import Any, cast

from fastapi import HTTPException
import httpcore
from httpcore._backends.auto import AutoBackend
import httpx

MAX_REDIRECTS = 4
MAX_IMAGE_BYTES = 12 * 1024 * 1024


def _forbidden(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if any(
        (
            address.is_private,
            address.is_loopback,
            address.is_link_local,
            address.is_reserved,
            address.is_multicast,
            address.is_unspecified,
        )
    ):
        return True
    if isinstance(address, ipaddress.IPv6Address):
        embedded = address.ipv4_mapped or address.sixtofour
        return bool(embedded is not None and _forbidden(embedded))
    return False


def _resolve(host: str) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    try:
        return [ipaddress.ip_address(host)]
    except ValueError:
        pass
    try:
        records = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise HTTPException(400, f"cannot resolve host {host!r}: {exc}") from exc
    addresses = {
        ipaddress.ip_address(cast(str, item[4][0]).split("%")[0]) for item in records
    }
    if not addresses:
        raise HTTPException(400, f"cannot resolve host {host!r}")
    return list(addresses)


@dataclass(frozen=True, slots=True)
class SafeTarget:
    url: str
    hostname: str
    pinned_ip: str


def prepare_safe_target(url: str) -> SafeTarget:
    if not isinstance(url, str):
        raise HTTPException(400, "url must be a string")
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(400, f"unsupported url scheme {parsed.scheme!r}; only http/https allowed")
    if parsed.username is not None or parsed.password is not None:
        raise HTTPException(400, "userinfo is not allowed in fetched URLs")
    if not parsed.hostname:
        raise HTTPException(400, "url has no host")
    addresses = _resolve(parsed.hostname)
    if any(_forbidden(address) for address in addresses):
        raise HTTPException(400, "url resolves to a disallowed (private/loopback/reserved) address")
    return SafeTarget(url, parsed.hostname, str(addresses[0]))


def assert_safe_url(url: str) -> str:
    prepare_safe_target(url)
    return url


class _PinnedBackend(AutoBackend):
    def __init__(self, hostname: str, address: str) -> None:
        super().__init__()
        self.hostname = hostname.casefold().rstrip(".")
        self.address = address

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Any = None,
    ) -> httpcore.AsyncNetworkStream:
        logical = host.decode() if isinstance(host, bytes) else str(host)
        dial = self.address if logical.casefold().rstrip(".") == self.hostname else logical
        return await super().connect_tcp(dial, port, timeout, local_address, socket_options)


def _transport(target: SafeTarget) -> httpx.AsyncHTTPTransport:
    from httpx._config import DEFAULT_LIMITS, create_ssl_context

    transport = httpx.AsyncHTTPTransport()
    transport._pool = httpcore.AsyncConnectionPool(
        ssl_context=create_ssl_context(verify=True, cert=None, trust_env=True),
        max_connections=DEFAULT_LIMITS.max_connections,
        max_keepalive_connections=DEFAULT_LIMITS.max_keepalive_connections,
        keepalive_expiry=DEFAULT_LIMITS.keepalive_expiry,
        network_backend=_PinnedBackend(target.hostname, target.pinned_ip),
    )
    return transport


async def fetch_bytes(url: str) -> tuple[bytes, str]:
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        target = prepare_safe_target(current)
        try:
            async with httpx.AsyncClient(transport=_transport(target), follow_redirects=False, timeout=30) as client:
                async with client.stream("GET", target.url) as response:
                    if response.is_redirect:
                        location = response.headers.get("location")
                        if not location:
                            raise HTTPException(400, "redirect without location header")
                        current = str(httpx.URL(current).join(location))
                        continue
                    response.raise_for_status()
                    declared = response.headers.get("content-length")
                    if declared and declared.isdigit() and int(declared) > MAX_IMAGE_BYTES:
                        raise HTTPException(400, "fetched resource exceeds size cap")
                    chunks: list[bytes] = []
                    size = 0
                    async for chunk in response.aiter_bytes():
                        size += len(chunk)
                        if size > MAX_IMAGE_BYTES:
                            raise HTTPException(400, "fetched resource exceeds size cap")
                        chunks.append(chunk)
                    media_type = response.headers.get("content-type", "image/png").split(";", 1)[0]
                    return b"".join(chunks), media_type.strip()
        except httpx.HTTPError as exc:
            raise HTTPException(400, f"failed to fetch url: {exc}") from exc
    raise HTTPException(400, "too many redirects")
