from __future__ import annotations
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from .config import RAW_DATA_ROOT, ROUTING
from .paths import triplets_dir

_DB_PATH = RAW_DATA_ROOT.parent / "sqlite" / "ledger.db"


@dataclass
class Item:
    content_hash: str
    item_id: str
    source: str
    captured_at: str
    bronze_path: str
    authored: bool
    metadata: dict

    def bronze_abs(self) -> Path:
        return RAW_DATA_ROOT / self.bronze_path

    def triplets_abs(self) -> Path:
        parts = Path(self.bronze_path).parts
        date = parts[1]
        return triplets_dir(self.source, date) / f"{self.item_id}.jsonl"


def _conn() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(str(_DB_PATH))


def init_ledger() -> None:
    sql = (Path(__file__).parent / "ledger.sql").read_text(encoding="utf-8")
    with _conn() as conn:
        conn.executescript(sql)


def register_item(item: Item) -> bool:
    try:
        with _conn() as conn:
            conn.execute(
                "INSERT INTO items VALUES (?,?,?,?,?,?,?)",
                (
                    item.content_hash,
                    item.item_id,
                    item.source,
                    item.captured_at,
                    item.bronze_path,
                    int(item.authored),
                    json.dumps(item.metadata),
                ),
            )
        return True
    except sqlite3.IntegrityError:
        return False


def get_item(content_hash: str):
    with _conn() as conn:
        row = conn.execute("SELECT * FROM items WHERE content_hash=?", (content_hash,)).fetchone()
    if not row:
        return None
    return Item(row[0], row[1], row[2], row[3], row[4], bool(row[5]), json.loads(row[6] or "{}"))


def is_done(content_hash: str, target: str, stage: str) -> bool:
    with _conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM processing WHERE content_hash=? AND target=? AND stage=? AND status='done'",
            (content_hash, target, stage),
        ).fetchone()
    return row is not None


def mark(content_hash: str, target: str, stage: str, status: str, artifact_path: str | None = None, error: str | None = None) -> None:
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).isoformat()
    with _conn() as conn:
        conn.execute(
            """INSERT INTO processing(content_hash,target,stage,status,artifact_path,attempted_at,error)
               VALUES(?,?,?,?,?,?,?)
               ON CONFLICT(content_hash,target,stage) DO UPDATE
               SET status=excluded.status, artifact_path=excluded.artifact_path,
                   attempted_at=excluded.attempted_at, error=excluded.error""",
            (content_hash, target, stage, status, artifact_path, now, error),
        )


def pending(target: str, stage: str) -> list[Item]:
    with _conn() as conn:
        rows = conn.execute(
            """SELECT i.* FROM items i
               WHERE NOT EXISTS (
                   SELECT 1 FROM processing p
                   WHERE p.content_hash=i.content_hash
                     AND p.target=? AND p.stage=? AND p.status='done'
               )""",
            (target, stage),
        ).fetchall()
    result = []
    for row in rows:
        item = Item(row[0], row[1], row[2], row[3], row[4], bool(row[5]), json.loads(row[6] or "{}"))
        if target in ROUTING.get(item.source, set()):
            result.append(item)
    return result
