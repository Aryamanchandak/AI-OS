# Version: V2
"""
Queue manager for the planner action queue.

queue.md lives at the project root. Format:

  # Planner Action Queue

  ## evt_001
  ```json
  { ... }
  ```

Rules:
  - JSON blocks are the single source of truth; headings are cosmetic.
  - One file lock (fcntl) for all writes — executor and app.py write concurrently.
  - Self-trigger guard: executor filters by status == "confirmed" before acting;
    status-only updates (done/failed) produce no confirmed items → no loop.
"""

from __future__ import annotations

import fcntl
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import TypeAdapter

from models import (
    QueueItem,
    QueueItemBase,
    CreateEventItem,
    CreateReminderItem,
    MoveEventItem,
    EditEventItem,
    UpdateReminderItem,
    EditReminderItem,
    DeleteEventItem,
    DeleteReminderItem,
)

QUEUE_PATH = Path(__file__).parent / "queue.md"

_ITEM_ADAPTER: TypeAdapter[QueueItem] = TypeAdapter(QueueItem)

# ── ID generation ─────────────────────────────────────────────────────────────

_PREFIX_MAP = {
    "create_event": "evt",
    "create_reminder": "rem",
    "move_event": "act",
    "edit_event": "act",
    "update_reminder_date": "act",
    "edit_reminder": "act",
    "delete_event": "act",
    "delete_reminder": "act",
}


def _current_max_ids() -> dict[str, int]:
    """Scan queue.md and return the highest numeric suffix per prefix."""
    maxes: dict[str, int] = {"evt": 0, "rem": 0, "act": 0}
    if not QUEUE_PATH.exists():
        return maxes
    pattern = re.compile(r"^## (evt|rem|act)_(\d+)$", re.MULTILINE)
    text = QUEUE_PATH.read_text(encoding="utf-8")
    for prefix, num in pattern.findall(text):
        maxes[prefix] = max(maxes[prefix], int(num))
    return maxes


_id_counters: dict[str, int] = {}


def next_id(item_type: str) -> str:
    """Return the next sequential ID for the given item type."""
    global _id_counters
    if not _id_counters:
        _id_counters = _current_max_ids()
    prefix = _PREFIX_MAP[item_type]
    _id_counters[prefix] += 1
    return f"{prefix}_{_id_counters[prefix]:03d}"


# ── Low-level read / write ────────────────────────────────────────────────────

_JSON_BLOCK = re.compile(r"## (\w+)\n```json\n(.*?)\n```", re.DOTALL)


def _read_all() -> list[dict]:
    """Read all JSON blocks from queue.md, unparsed."""
    if not QUEUE_PATH.exists():
        return []
    text = QUEUE_PATH.read_text(encoding="utf-8")
    return [json.loads(m.group(2)) for m in _JSON_BLOCK.finditer(text)]


def _write_all(items: list[dict]) -> None:
    """Overwrite queue.md with the given list of raw dicts (file must be locked by caller)."""
    lines = ["# Planner Action Queue\n"]
    for item in items:
        lines.append(f"\n## {item['id']}\n```json\n{json.dumps(item, indent=2, default=str)}\n```\n")
    QUEUE_PATH.write_text("".join(lines), encoding="utf-8")


def _with_lock(fn):
    """Decorator: acquire an exclusive fcntl lock before calling fn."""
    def wrapper(*args, **kwargs):
        QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
        if not QUEUE_PATH.exists():
            QUEUE_PATH.write_text("# Planner Action Queue\n", encoding="utf-8")
        with open(QUEUE_PATH, "r+", encoding="utf-8") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)
            try:
                return fn(*args, **kwargs)
            finally:
                fcntl.flock(fh, fcntl.LOCK_UN)
    return wrapper


# ── Public API ────────────────────────────────────────────────────────────────

@_with_lock
def append_item(item: QueueItemBase) -> None:
    """Append a new proposed item to queue.md."""
    raw = _read_all()
    raw.append(json.loads(item.model_dump_json()))
    _write_all(raw)


@_with_lock
def confirm_all_proposed() -> list[str]:
    """Flip all proposed items to confirmed. Returns list of confirmed IDs."""
    raw = _read_all()
    confirmed_ids = []
    now = datetime.now().isoformat()
    for item in raw:
        if item.get("status") == "proposed":
            item["status"] = "confirmed"
            item["confirmed_at"] = now
            confirmed_ids.append(item["id"])
    _write_all(raw)
    return confirmed_ids


@_with_lock
def remove_proposed() -> list[str]:
    """Remove all proposed items from queue.md (cancel). Returns removed IDs."""
    raw = _read_all()
    removed = [i["id"] for i in raw if i.get("status") == "proposed"]
    kept = [i for i in raw if i.get("status") != "proposed"]
    _write_all(kept)
    return removed


@_with_lock
def update_item_status(
    item_id: str,
    status: Literal["done", "failed"],
    error: str | None = None,
) -> None:
    """Update a single item's status (called by executor)."""
    raw = _read_all()
    now = datetime.now().isoformat()
    for item in raw:
        if item["id"] == item_id:
            item["status"] = status
            item["executed_at"] = now
            if error:
                item["error"] = error
            break
    _write_all(raw)


def list_by_status(status: str) -> list[QueueItem]:
    """Return all queue items matching the given status, parsed and validated."""
    raw = _read_all()
    result = []
    for r in raw:
        if r.get("status") == status:
            result.append(_ITEM_ADAPTER.validate_python(r))
    return result


def list_all() -> list[dict]:
    """Return all raw items (for /queue_status endpoint)."""
    return _read_all()


def has_confirmed() -> bool:
    """Quick check: are there any confirmed items pending execution?"""
    return any(i.get("status") == "confirmed" for i in _read_all())
