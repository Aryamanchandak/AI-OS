from __future__ import annotations

import ipaddress
import re
import socket
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

import httpx
import trafilatura

from ...config import Settings

TRACKING = {"gclid", "fbclid", "mc_cid", "mc_eid", "ref", "source"}
ALLOWED_TYPES = {"text/html", "text/plain", "application/xhtml+xml"}


class UnsafeUrl(ValueError):
    pass


def normalize_url(value: str) -> str:
    # urlsplit defers parsing, so a malformed authority surfaces as a bare
    # ValueError from .hostname or .port, and an empty or over-long IDNA label
    # surfaces as UnicodeError.  Both are rejections of a supplied URL, so they
    # are reported as UnsafeUrl rather than escaping as an opaque internal error
    # that fails the whole run from normalize_batch.
    try:
        parsed = urlsplit(value.strip())
        hostname, port = parsed.hostname, parsed.port
    except ValueError as exc:
        raise UnsafeUrl(f"malformed URL: {exc}") from exc
    if parsed.scheme.lower() not in {"http", "https"} or not hostname:
        raise UnsafeUrl("only absolute HTTP(S) URLs are accepted")
    try:
        host = hostname.encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise UnsafeUrl(f"malformed host name: {exc}") from exc
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
        raise UnsafeUrl("local destinations are forbidden")
    try: address = ipaddress.ip_address(host)
    except ValueError: address = None
    if address is not None and not address.is_global:
        raise UnsafeUrl("private, loopback, link-local, and reserved destinations are forbidden")
    netloc = host
    if port and not ((parsed.scheme == "http" and port == 80) or (parsed.scheme == "https" and port == 443)):
        netloc += f":{port}"
    query = urlencode([(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True) if not k.lower().startswith("utm_") and k.lower() not in TRACKING], doseq=True)
    path = re.sub(r"/{2,}", "/", parsed.path or "/")
    return urlunsplit((parsed.scheme.lower(), netloc, path.rstrip("/") or "/", query, ""))


def assert_public_url(value: str, resolver=socket.getaddrinfo) -> str:
    canonical = normalize_url(value)
    host = urlsplit(canonical).hostname or ""
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
        raise UnsafeUrl("local destinations are forbidden")
    try:
        addresses = resolver(host, None)
    except OSError as exc:
        raise UnsafeUrl(f"host resolution failed: {exc}") from exc
    for item in addresses:
        address = ipaddress.ip_address(item[4][0])
        if not address.is_global:
            raise UnsafeUrl("private, loopback, link-local, and reserved destinations are forbidden")
    return canonical


@dataclass(frozen=True)
class FetchResult:
    url: str
    final_url: str
    title: str
    text: str
    content_type: str
    retrieved_at: datetime


class PageFetcher:
    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None):
        self.settings, self.transport = settings, transport

    def fetch(self, url: str) -> FetchResult:
        current = assert_public_url(url)
        headers = {"User-Agent": "ConsequenceRadar/0.1 (+research)", "Accept": "text/html,text/plain;q=0.9"}
        with httpx.Client(timeout=self.settings.fetch_timeout_seconds, follow_redirects=False, transport=self.transport) as client:
            for _ in range(self.settings.fetch_redirect_limit + 1):
                last_error = None
                for attempt in range(self.settings.fetch_retry_limit + 1):
                    try:
                        with client.stream("GET", current, headers=headers) as response:
                            if response.is_redirect:
                                target = urljoin(current, response.headers.get("location", ""))
                                current = assert_public_url(target)
                                break
                            response.raise_for_status()
                            ctype = response.headers.get("content-type", "").split(";", 1)[0].lower()
                            if ctype not in ALLOWED_TYPES: raise ValueError(f"unsupported content type: {ctype or 'missing'}")
                            # A malformed Content-Length is not a reason to abort
                            # differently from any other oversized body; the
                            # streaming counter below is the real bound.
                            try: length = int(response.headers.get("content-length", "") or 0)
                            except ValueError: length = 0
                            if length > self.settings.fetch_max_bytes: raise ValueError("response exceeds configured size limit")
                            chunks, total = [], 0
                            for chunk in response.iter_bytes():
                                total += len(chunk)
                                if total > self.settings.fetch_max_bytes: raise ValueError("response exceeds configured size limit")
                                chunks.append(chunk)
                            raw = b"".join(chunks).decode(response.encoding or "utf-8", errors="replace")
                            text = raw if ctype == "text/plain" else (trafilatura.extract(raw, include_comments=False, include_tables=False, favor_precision=True) or "")
                            title_match = re.search(r"<title[^>]*>(.*?)</title>", raw, re.I | re.S)
                            title = re.sub(r"\s+", " ", title_match.group(1)).strip() if title_match else ""
                            return FetchResult(normalize_url(url), normalize_url(current), title, text[:80_000], ctype, datetime.now(timezone.utc))
                    except (httpx.TimeoutException, httpx.TransportError) as exc:
                        last_error = exc
                        if attempt >= self.settings.fetch_retry_limit: raise
                else:
                    if last_error: raise last_error
        raise ValueError("redirect limit exceeded")
