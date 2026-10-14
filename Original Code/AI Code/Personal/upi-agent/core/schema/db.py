"""
Database connection helper.

Usage:
    from core.schema.db import connect
    with connect() as conn:
        rows = conn.execute("SELECT ...").fetchall()

Migrations run lazily once per process. Override the path via connect(path)
in tests.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from core import config
from core.schema import migrate as _migrate


_MIGRATED: set[str] = set()


@contextmanager
def connect(db_path: Path | str | None = None) -> Iterator[sqlite3.Connection]:
    """
    Yield a SQLite connection with row_factory = sqlite3.Row.
    Auto-commits on successful exit, rolls back on exception.
    Runs migrations the first time a path is used in this process.
    """
    path = Path(db_path) if db_path else config.DB_PATH
    path_str = str(path)

    if path_str not in _MIGRATED:
        path.parent.mkdir(parents=True, exist_ok=True)
        _migrate.migrate(path)
        _MIGRATED.add(path_str)

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def reset_migration_cache() -> None:
    """Test helper: forget which paths have been migrated."""
    _MIGRATED.clear()
