"""
URL fetching via crawl4ai (headless Chromium → clean markdown).

The fd-level stdout redirect is intentional: crawl4ai uses Rich which writes
directly to the stdout file descriptor, bypassing Python-level redirects.
Without this, [FETCH]/[SCRAPE] banners corrupt the MCP stdio JSON-RPC stream.
"""
from __future__ import annotations

import asyncio
import ipaddress
import os
from urllib.parse import urlparse, urlunparse

from tool_registry import register

MAX_FETCH_TIMEOUT_SECONDS = 30


def _validated_url(url: str) -> str:
    clean_url = url.strip()
    if not clean_url:
        raise ValueError("url cannot be empty.")

    parsed = urlparse(clean_url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("url must start with http:// or https://.")
    if not parsed.hostname:
        raise ValueError("url must include a hostname.")
    if parsed.username or parsed.password:
        raise ValueError("url cannot include embedded credentials.")
    try:
        parsed.port
    except ValueError:
        raise ValueError("url must include a valid port.") from None

    hostname = parsed.hostname.rstrip(".").lower()
    if hostname in {"localhost", "127.0.0.1", "::1"} or hostname.endswith(".localhost"):
        raise ValueError("localhost URLs are not allowed.")

    try:
        host_ip = ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        if (
            host_ip.is_loopback
            or host_ip.is_private
            or host_ip.is_link_local
            or host_ip.is_multicast
            or host_ip.is_reserved
            or host_ip.is_unspecified
        ):
            raise ValueError("private, local, reserved, or multicast IP URLs are not allowed.")

    return urlunparse(parsed)


def _bounded_timeout(timeout: int) -> int:
    try:
        timeout_seconds = int(timeout)
    except (TypeError, ValueError):
        raise ValueError("timeout must be an integer number of seconds.") from None
    if timeout_seconds < 1:
        raise ValueError("timeout must be at least 1 second.")
    return min(timeout_seconds, MAX_FETCH_TIMEOUT_SECONDS)


async def _crawl4ai_fetch(url: str) -> dict:
    from crawl4ai import AsyncWebCrawler

    saved_fd = os.dup(1)
    os.dup2(2, 1)
    try:
        async with AsyncWebCrawler(verbose=False) as crawler:
            r = await crawler.arun(url=url)
    finally:
        os.dup2(saved_fd, 1)
        os.close(saved_fd)

    # r.markdown is a StringCompatibleMarkdown subclass that Pydantic serializes
    # as {} because its real field is private — pull the raw string out explicitly.
    md = r.markdown
    raw = (
        getattr(md, "raw_markdown", None)
        or getattr(md, "fit_markdown", None)
        or md
        or r.cleaned_html
        or r.html
        or ""
    )
    text = str(raw)
    return {
        "status": int(getattr(r, "status_code", None) or 200),
        "content_type": "text/markdown",
        "length_bytes": len(text.encode("utf-8")),
        "text": text,
    }


@register(group="utility")
async def fetch_url(url: str, timeout: int = MAX_FETCH_TIMEOUT_SECONDS) -> dict:
    """
    Fetch clean markdown from an http(s) URL via crawl4ai.

    The crawl is capped at 30 seconds. Localhost, embedded credentials, non-web
    schemes, and literal private/local/reserved IP URLs are rejected before
    launching the browser.
    """
    clean_url = _validated_url(url)
    timeout_seconds = _bounded_timeout(timeout)
    try:
        return await asyncio.wait_for(
            _crawl4ai_fetch(clean_url),
            timeout=timeout_seconds,
        )
    except asyncio.TimeoutError:
        raise TimeoutError(f"fetch_url timed out after {timeout_seconds} seconds.") from None
