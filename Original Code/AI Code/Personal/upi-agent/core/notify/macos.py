"""
macOS notification helper.

Calls `osascript -e 'display notification ...'` for severity ≥ 2 events.
Silently no-ops on non-Mac systems and on osascript errors. Notifications
are best-effort decoration on top of the agent_events table — never the
source of truth.
"""

from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path

from core import config
from core.schema.db import connect


log = logging.getLogger("core.notify.macos")

NOTIFY_MIN_SEVERITY = 2


def _osascript(title: str, subtitle: str, body: str) -> bool:
    """Show a notification via osascript. Return True on success."""
    if sys.platform != "darwin":
        return False
    truncate = config.NOTIFIER_TRUNCATE_LEN

    def esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace('"', '\\"')[:truncate]

    script = (
        f'display notification "{esc(body)}" '
        f'with title "{esc(title)}" '
        f'subtitle "{esc(subtitle)}"'
    )
    try:
        r = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=5, check=False,
        )
        return r.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def notify_severe(db_path: Path | str | None = None) -> int:
    """
    Find unacknowledged events with severity ≥ NOTIFY_MIN_SEVERITY and
    surface them via macOS Notification Center.

    Returns the number of notifications shown.
    """
    shown = 0
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT id, kind, title, explanation, severity
            FROM agent_events
            WHERE severity >= ? AND acknowledged = 0
            ORDER BY created_at DESC
            LIMIT 5
            """,
            (NOTIFY_MIN_SEVERITY,),
        ).fetchall()

    for r in rows:
        ok = _osascript(
            title="UPI Agent",
            subtitle=r["kind"].replace("_", " ").title(),
            body=r["title"],
        )
        if ok:
            shown += 1
    return shown
