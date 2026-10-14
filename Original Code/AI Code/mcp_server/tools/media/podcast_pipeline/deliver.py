"""Readwise Reader delivery backend for podcast briefs."""

from __future__ import annotations

import os

import httpx

READER_SAVE_URL = "https://readwise.io/api/v3/save/"


def push_to_reader(
    html: str,
    title: str,
    source_url: str,
    author: str = "",
    tags: list[str] | None = None,
    location: str = "new",
    summary: str = "",
) -> dict:
    """Save a document to Readwise Reader. Returns {"id": ..., "url": ...}."""
    token = os.getenv("READWISE_TOKEN", "")
    if not token:
        raise RuntimeError("Missing required environment variable: READWISE_TOKEN")

    payload: dict = {
        "url": source_url,
        "html": html,
        "title": title,
        "location": location,
        "category": "article",
        "saved_using": "podcast-brief",
        "should_clean_html": False,
        "tags": tags or [],
    }
    if author:
        payload["author"] = author
    if summary:
        payload["summary"] = summary[:500]

    resp = httpx.post(
        READER_SAVE_URL,
        json=payload,
        headers={"Authorization": f"Token {token}", "Content-Type": "application/json"},
        timeout=60,
    )
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"Reader API error {resp.status_code}: {resp.text[:300]}")

    data = resp.json()
    return {"id": data.get("id"), "url": data.get("url")}


def verify_readwise_token() -> bool:
    """Return True if READWISE_TOKEN env var is set and accepted by the Readwise API."""
    token = os.getenv("READWISE_TOKEN")
    if not token:
        return False
    try:
        resp = httpx.get(
            "https://readwise.io/api/v2/auth/",
            headers={"Authorization": f"Token {token}"},
            timeout=10,
        )
        return resp.status_code == 204
    except Exception:
        return False
