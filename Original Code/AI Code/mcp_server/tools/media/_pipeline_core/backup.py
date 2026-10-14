"""Hot-copy backup utilities for the podcast provenance database."""

from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

from tools.media._pipeline_core.storage.client import get_store

_TIMESTAMP_FORMAT = "%Y%m%d_%H%M%S"
_RETENTION_DAYS = 30
_MIN_KEEP = 10


def backup_db(reason: str = "") -> Path:
    """Create a timestamped SQLite backup and prune stale snapshots."""
    store = get_store()
    store.ensure_database()

    db_path = Path(store.db_path)
    backup_dir = db_path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)

    backup_path = _next_backup_path(backup_dir)
    with sqlite3.connect(db_path) as source, sqlite3.connect(backup_path) as dest:
        source.backup(dest)

    _prune_backups(backup_dir, newest_path=backup_path)
    print(f"[backup] reason={reason} -> {backup_path}", file=sys.stderr)
    return backup_path


def _prune_backups(backup_dir: Path, newest_path: Path) -> None:
    backups = sorted(
        backup_dir.glob("podcast_pipeline_*.db"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    cutoff = datetime.now() - timedelta(days=_RETENTION_DAYS)

    for index, path in enumerate(backups):
        if path == newest_path:
            continue
        if index < _MIN_KEEP:
            continue
        if datetime.fromtimestamp(path.stat().st_mtime) < cutoff:
            path.unlink(missing_ok=True)


def _next_backup_path(backup_dir: Path) -> Path:
    timestamp = datetime.now().strftime(_TIMESTAMP_FORMAT)
    candidate = backup_dir / f"podcast_pipeline_{timestamp}.db"
    if not candidate.exists():
        return candidate

    index = 1
    while True:
        candidate = backup_dir / f"podcast_pipeline_{timestamp}_{index}.db"
        if not candidate.exists():
            return candidate
        index += 1
