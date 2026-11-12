"""
history_manager.py — append-only daily Truth Log.

Each successfully executed write action is recorded in /history/YYYY-MM-DD.md.
One file per calendar day, never deleted. File locking via a shared .write.lock
so concurrent executor calls are safe.
"""
from __future__ import annotations

import fcntl
from datetime import date, datetime
from pathlib import Path

from models import QueueItem

HISTORY_DIR = Path(__file__).parent / "history"

_SECTIONS = [
    "Calendar — Added",
    "Calendar — Changed",
    "Calendar — Deleted",
    "Reminders — Added",
    "Reminders — Changed",
    "Reminders — Deleted",
]

_SECTION_MAP: dict[str, str] = {
    "create_event":         "Calendar — Added",
    "move_event":           "Calendar — Changed",
    "edit_event":           "Calendar — Changed",
    "delete_event":         "Calendar — Deleted",
    "create_reminder":      "Reminders — Added",
    "update_reminder_date": "Reminders — Changed",
    "edit_reminder":        "Reminders — Changed",
    "delete_reminder":      "Reminders — Deleted",
}


def _make_header() -> str:
    lines = [f"# Truth Log — {date.today().isoformat()}\n"]
    for s in _SECTIONS:
        lines.append(f"\n## {s}\n")
    return "".join(lines)


def _format_entry(item: QueueItem, ts: str) -> str:
    t = item.type

    if t == "create_event":
        time_str = item.time.strftime("%H:%M") if item.time else "all-day"
        if item.time:
            total = item.time.hour * 60 + item.time.minute + item.duration_minutes
            end_str = f"{total // 60:02d}:{total % 60:02d}"
            slot = f"{time_str}–{end_str}"
        else:
            slot = time_str
        return f'- [{ts}] "{item.title}" → {item.date.strftime("%a %b %d")} {slot}'

    if t == "create_reminder":
        return f'- [{ts}] "{item.title}" → due {item.date.strftime("%a %b %d")} at {item.time.strftime("%H:%M")}'

    if t == "move_event":
        orig = f'{item.original_date.strftime("%a %b %d")} {item.original_start.strftime("%H:%M")}'
        new = f'{item.new_date.strftime("%a %b %d")} {item.new_start.strftime("%H:%M")}'
        return f'- [{ts}] "{item.original_title}" moved {orig} → {new}'

    if t == "edit_event":
        changes = []
        if item.new_title:
            changes.append(f'renamed to "{item.new_title}"')
        if item.new_duration_minutes:
            changes.append(f"duration → {item.new_duration_minutes}min")
        if item.new_description:
            changes.append("description updated")
        detail = ", ".join(changes) or "edited"
        return f'- [{ts}] "{item.title}" on {item.date.strftime("%a %b %d")} — {detail}'

    if t == "update_reminder_date":
        suffix = f" at {item.new_time.strftime('%H:%M')}" if item.new_time else ""
        return f'- [{ts}] "{item.title}" rescheduled → {item.new_date.strftime("%a %b %d")}{suffix}'

    if t == "edit_reminder":
        detail = f'renamed to "{item.new_title}"' if item.new_title else "edited"
        return f'- [{ts}] "{item.title}" ({item.list_name}) — {detail}'

    if t == "delete_event":
        return f'- [{ts}] "{item.title}" on {item.date.strftime("%a %b %d")} — deleted'

    if t == "delete_reminder":
        return f'- [{ts}] "{item.title}" ({item.list_name}) — deleted'

    return f'- [{ts}] {item.id} ({t})'


def _insert_under_section(content: str, section: str, entry: str) -> str:
    """Insert an entry line under the given section header."""
    header = f"## {section}"
    idx = content.find(header)
    if idx == -1:
        return content.rstrip() + f"\n\n## {section}\n{entry}\n"

    after_header = idx + len(header)
    next_sec = content.find("\n## ", after_header)
    if next_sec == -1:
        return content.rstrip() + f"\n{entry}\n"
    else:
        before = content[:next_sec].rstrip()
        after = content[next_sec:]
        return before + f"\n{entry}" + after


def record_action(item: QueueItem) -> None:
    """Record a successfully executed action in today's Truth Log."""
    section = _SECTION_MAP.get(item.type)
    if not section:
        return

    HISTORY_DIR.mkdir(exist_ok=True)
    path = HISTORY_DIR / f"{date.today().isoformat()}.md"
    ts = datetime.now().strftime("%H:%M")
    entry = _format_entry(item, ts)

    lock_path = HISTORY_DIR / ".write.lock"
    with open(lock_path, "w", encoding="utf-8") as lock_fh:
        fcntl.flock(lock_fh, fcntl.LOCK_EX)
        try:
            content = path.read_text(encoding="utf-8") if path.exists() else _make_header()
            content = _insert_under_section(content, section, entry)
            path.write_text(content, encoding="utf-8")
        finally:
            fcntl.flock(lock_fh, fcntl.LOCK_UN)
