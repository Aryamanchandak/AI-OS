"""
Best-effort usage event log.
Written to usage.md next to mcp_server.py.
Tracks lightweight provider/tool counters without adding a runtime dependency.
"""
from __future__ import annotations

import threading
from datetime import datetime, timezone
from pathlib import Path

USAGE_PATH = Path(__file__).parent / "usage.md"
_usage_lock = threading.Lock()


def _ensure_header() -> None:
    if USAGE_PATH.exists():
        return
    USAGE_PATH.write_text(
        "# MCP Usage Log\n\n"
        "Best-effort local usage events. This file is intentionally simple so "
        "nightly plumbing can parse and move it into a real store later.\n\n"
        "| timestamp_utc | provider | field |\n"
        "|---|---|---|\n",
        encoding="utf-8",
    )


def _clean_cell(value: str) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ").strip()


def bump(provider: str, field: str = "count") -> None:
    """Append a usage event. Logging is best-effort and never breaks callers."""
    try:
        timestamp = datetime.now(timezone.utc).isoformat()
        row = f"| {timestamp} | {_clean_cell(provider)} | {_clean_cell(field)} |\n"
        with _usage_lock:
            _ensure_header()
            with USAGE_PATH.open("a", encoding="utf-8") as f:
                f.write(row)
    except Exception:
        return
