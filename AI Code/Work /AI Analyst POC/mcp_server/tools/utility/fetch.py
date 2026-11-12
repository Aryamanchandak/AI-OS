"""
URL fetching via crawl4ai (headless Chromium → clean markdown).

The fd-level stdout redirect is intentional: crawl4ai uses Rich which writes
directly to the stdout file descriptor, bypassing Python-level redirects.
Without this, [FETCH]/[SCRAPE] banners corrupt the MCP stdio JSON-RPC stream.
"""
from __future__ import annotations

import os

from tool_registry import register


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
async def fetch_url(url: str, timeout: int = 20) -> dict:
    """Fetch clean markdown from a URL via crawl4ai (headless Chromium). Example: fetch_url("https://example.com")."""
    return await _crawl4ai_fetch(url)
