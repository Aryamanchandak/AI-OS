"""
Thread-safe API usage tracker with monthly rollover.
Written to usage.json next to mcp_server.py.
Tracks DuckDuckGo fallback calls (informational).
"""
from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path

USAGE_PATH = Path(__file__).parent / "usage.json"
_usage_lock = threading.Lock()


def _empty_usage(month: str) -> dict:
    return {"month": month, "duckduckgo": {"count": 0, "errors": 0}}


def _load_usage() -> dict:
    month = datetime.now().strftime("%Y-%m")
    if not USAGE_PATH.exists():
        return _empty_usage(month)
    try:
        data = json.loads(USAGE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return _empty_usage(month)
    if data.get("month") != month:
        return _empty_usage(month)
    data.setdefault("duckduckgo", {"count": 0, "errors": 0})
    return data


def _save_usage(data: dict) -> None:
    USAGE_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def bump(provider: str, field: str = "count") -> None:
    with _usage_lock:
        data = _load_usage()
        data.setdefault(provider, {"count": 0, "errors": 0})
        data[provider][field] = data[provider].get(field, 0) + 1
        _save_usage(data)
