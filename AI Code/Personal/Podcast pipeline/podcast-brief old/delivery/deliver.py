"""
deliver.py — Push briefs to Readwise Reader via the Reader API.
"""

import os
import requests

from core.config import require_env


READER_SAVE_URL = "https://readwise.io/api/v3/save/"


def push_to_reader(
    html: str,
    title: str,
    source_url: str,
    author: str = "",
    tags: list[str] = None,
    location: str = "new",
    summary: str = "",
) -> dict:
    """
    Save a document to Readwise Reader.

    Args:
        html: The HTML content of the document.
        title: Document title.
        source_url: Original source URL (Reader uses this for attribution).
        author: Optional author/show name.
        tags: List of tags (e.g. ["podcast", "podcast/lex", "profile/academic"]).
        location: "new" | "later" | "archive" | "feed". "new" = inbox.
        summary: Optional short summary shown in the Reader list view.

    Returns:
        dict with keys 'id', 'url' (the read.readwise.io link).
    """
    require_env("READWISE_TOKEN")

    payload = {
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

    headers = {
        "Authorization": f"Token {os.getenv('READWISE_TOKEN')}",
        "Content-Type": "application/json",
    }

    resp = requests.post(READER_SAVE_URL, json=payload, headers=headers, timeout=60)

    if resp.status_code not in (200, 201):
        raise RuntimeError(
            f"Reader API error {resp.status_code}: {resp.text[:300]}"
        )

    data = resp.json()
    return {
        "id": data.get("id"),
        "url": data.get("url"),
    }


def verify_token() -> bool:
    """Check that the Readwise token is valid. Useful for diagnostics."""
    token = os.getenv("READWISE_TOKEN")
    if not token:
        return False
    try:
        resp = requests.get(
            "https://readwise.io/api/v2/auth/",
            headers={"Authorization": f"Token {token}"},
            timeout=10,
        )
        return resp.status_code == 204
    except Exception:
        return False
