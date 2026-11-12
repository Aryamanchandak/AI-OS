"""Shared SQLite connection and migration primitives.

Schemas remain owned by their domains; this module only centralizes safe
connection setup and transaction boundaries.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
import sqlite3


class SQLiteDatabase:
    def __init__(self, path: Path) -> None:
        self.path = path

    @contextmanager
    def connect(self, *, autocommit: bool = False) -> Iterator[sqlite3.Connection]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(
            self.path,
            isolation_level=None if autocommit else "DEFERRED",
            check_same_thread=False,
        )
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            if not autocommit:
                connection.commit()
        except BaseException:
            if not autocommit:
                connection.rollback()
            raise
        finally:
            connection.close()

    def migrate(self, statements: Sequence[str], *, autocommit: bool = False) -> None:
        with self.connect(autocommit=autocommit) as connection:
            for statement in statements:
                connection.executescript(statement)
