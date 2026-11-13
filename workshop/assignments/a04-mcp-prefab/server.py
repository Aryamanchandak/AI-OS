"""An MCP server with three tools.

    lookup_topic   the internet: finds a topic on Wikipedia and returns a summary
    notes_file     a local file: create, read, update or delete notes in data/notes.json
    show_notebook  a screen: a Prefab dashboard of those notes, rendered by the MCP host

Run over stdio (for Claude Desktop and other MCP hosts):
    uv run python server.py
"""

from __future__ import annotations

from typing import Literal

import httpx
from fastmcp import FastMCP
from prefab_ui.app import PrefabApp

import notes_store as store
from ui import build_notebook, chart_rows

mcp = FastMCP("research-notebook")

WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"
WIKIPEDIA_SUMMARY = "https://en.wikipedia.org/api/rest_v1/page/summary/"
HEADERS = {"User-Agent": "a04-mcp-prefab/0.1 (course assignment)"}
TIMEOUT_SECONDS = 20


def _snapshot() -> dict:
    """Everything the screen needs after a change."""
    counts = store.counts()
    return {
        "notes": [n.model_dump() for n in store.list_notes()],
        "counts": counts,
        "chart": chart_rows(counts),
    }


@mcp.tool
def lookup_topic(topic: str) -> dict:
    """Look a topic up on Wikipedia. Returns the best-matching page's title, a
    short summary and its link. Use this to gather facts before saving a note.
    Example: lookup_topic("Tata Sons")."""
    with httpx.Client(headers=HEADERS, timeout=TIMEOUT_SECONDS, follow_redirects=True) as client:
        search = client.get(WIKIPEDIA_API, params={
            "action": "query", "list": "search", "srsearch": topic,
            "srlimit": 1, "format": "json",
        })
        search.raise_for_status()
        hits = search.json()["query"]["search"]
        if not hits:
            return {"found": False, "topic": topic}
        title = hits[0]["title"]
        page = client.get(WIKIPEDIA_SUMMARY + title.replace(" ", "_"))
        page.raise_for_status()
        data = page.json()
    return {
        "found": True,
        "topic": topic,
        "title": data.get("title", title),
        "summary": data.get("extract", ""),
        "url": data.get("content_urls", {}).get("desktop", {}).get("page", ""),
    }


@mcp.tool
def notes_file(
    action: Literal["create", "read", "update", "delete", "list"],
    note_id: str = "",
    title: str = "",
    body: str = "",
    source_url: str = "",
    status: Literal["", "unverified", "verified"] = "",
) -> dict:
    """Create, read, update, delete or list notes in the local notes file.

    create needs `title` and `body` (and optionally `source_url`).
    read, update and delete need `note_id`. update changes only the fields you pass.
    Every reply includes the full list of notes and the counts.
    Example: notes_file("create", title="Tata Sons ownership", body="...", source_url="https://...")."""
    note = None
    if action == "create":
        note = store.create_note(title, body, source_url)
    elif action == "read":
        note = store.get_note(note_id)
    elif action == "update":
        note = store.update_note(
            note_id,
            title=title or None,
            body=body or None,
            source_url=source_url or None,
            status=status or None,
        )
    elif action == "delete":
        store.delete_note(note_id)
    return {"action": action, "note": note.model_dump() if note else None, **_snapshot()}


@mcp.tool(app=True)
def show_notebook(topic: str = "") -> PrefabApp:
    """Show the notes as a dashboard: counts, a searchable table, a chart, and
    buttons to verify, delete or add notes. Call this to show the user what
    has been saved. `topic` is an optional label for the header."""
    snap = _snapshot()
    return build_notebook(snap["notes"], snap["counts"], topic)


if __name__ == "__main__":
    mcp.run()
