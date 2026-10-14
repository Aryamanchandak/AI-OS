"""SQLite storage layer. All writes are idempotent (INSERT OR IGNORE)."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import aiosqlite

from .contracts import LogicalSource, RunRecord

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id     TEXT PRIMARY KEY,
    mode       TEXT NOT NULL,
    input      TEXT NOT NULL,
    status     TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL,
    finished_at TEXT,
    cost_usd   REAL NOT NULL DEFAULT 0.0
);

CREATE TABLE IF NOT EXISTS model_calls (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp  TEXT NOT NULL,
    model      TEXT NOT NULL,
    stage      TEXT NOT NULL,
    tokens_in  INTEGER NOT NULL DEFAULT 0,
    tokens_out INTEGER NOT NULL DEFAULT 0,
    cost_usd   REAL NOT NULL DEFAULT 0.0,
    run_id     TEXT NOT NULL,
    status     TEXT NOT NULL DEFAULT 'success',
    FOREIGN KEY (run_id) REFERENCES runs(run_id)
);

CREATE TABLE IF NOT EXISTS logical_sources (
    id          TEXT PRIMARY KEY,
    fingerprint TEXT UNIQUE NOT NULL,
    title       TEXT NOT NULL,
    authors     TEXT NOT NULL DEFAULT '[]',
    published   TEXT,
    url         TEXT,
    raw_excerpt TEXT NOT NULL DEFAULT '',
    provenance  TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS source_ids (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    logical_source_id  TEXT NOT NULL,
    source             TEXT NOT NULL,
    external_id        TEXT NOT NULL,
    UNIQUE(source, external_id),
    FOREIGN KEY (logical_source_id) REFERENCES logical_sources(id)
);

CREATE TABLE IF NOT EXISTS run_sources (
    run_id            TEXT NOT NULL,
    logical_source_id TEXT NOT NULL,
    PRIMARY KEY (run_id, logical_source_id),
    FOREIGN KEY (run_id) REFERENCES runs(run_id),
    FOREIGN KEY (logical_source_id) REFERENCES logical_sources(id)
);

CREATE TABLE IF NOT EXISTS annotations (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    logical_source_id TEXT NOT NULL,
    run_id            TEXT NOT NULL,
    relevance         REAL NOT NULL DEFAULT 0.0,
    key_findings      TEXT NOT NULL DEFAULT '[]',
    credibility_tier  TEXT NOT NULL DEFAULT 'open_web',
    FOREIGN KEY (logical_source_id) REFERENCES logical_sources(id),
    FOREIGN KEY (run_id) REFERENCES runs(run_id)
);

CREATE TABLE IF NOT EXISTS silent_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    claim_text  TEXT NOT NULL,
    correctness TEXT NOT NULL,
    effort      TEXT NOT NULL,
    confidence  REAL NOT NULL,
    rationale   TEXT NOT NULL,
    run_id      TEXT NOT NULL,
    timestamp   TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES runs(run_id)
);
"""


async def init_db(path: str | Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(str(path)) as db:
        await db.executescript(_SCHEMA)
        await db.commit()


async def insert_run(db_path: str, run: RunRecord) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "INSERT OR IGNORE INTO runs (run_id, mode, input, status, created_at, cost_usd) VALUES (?,?,?,?,?,?)",
            (run.run_id, run.mode, run.input, run.status, run.created_at.isoformat(), run.cost_usd),
        )
        await db.commit()


async def update_run_status(db_path: str, run_id: str, status: str, finished_at: datetime | None = None) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "UPDATE runs SET status = ?, finished_at = ? WHERE run_id = ?",
            (status, finished_at.isoformat() if finished_at else None, run_id),
        )
        await db.commit()


async def get_run(db_path: str, run_id: str) -> dict[str, Any] | None:
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def upsert_logical_source(db_path: str, src: LogicalSource) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """INSERT INTO logical_sources (id, fingerprint, title, authors, published, url, raw_excerpt, provenance)
               VALUES (?,?,?,?,?,?,?,?)
               ON CONFLICT(fingerprint) DO UPDATE SET
                 raw_excerpt = CASE WHEN excluded.raw_excerpt != '' THEN excluded.raw_excerpt ELSE raw_excerpt END,
                 url = COALESCE(excluded.url, url)""",
            (
                src.id,
                src.fingerprint,
                src.title,
                json.dumps(src.authors),
                src.published,
                src.url,
                src.raw_excerpt,
                json.dumps([p.model_dump() for p in src.provenance]),
            ),
        )
        # After upsert, resolve the actual stored id — src.id is a new UUID each call;
        # if the fingerprint already existed the DB kept the original id.
        async with db.execute(
            "SELECT id FROM logical_sources WHERE fingerprint = ?", (src.fingerprint,)
        ) as cursor:
            row = await cursor.fetchone()
            actual_id = row[0] if row else src.id

        for source_name, ext_id in src.external_ids.items():
            await db.execute(
                "INSERT OR IGNORE INTO source_ids (logical_source_id, source, external_id) VALUES (?,?,?)",
                (actual_id, source_name, ext_id),
            )
        await db.commit()


async def link_source_to_run(db_path: str, run_id: str, logical_source_id: str) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "INSERT OR IGNORE INTO run_sources (run_id, logical_source_id) VALUES (?,?)",
            (run_id, logical_source_id),
        )
        await db.commit()


async def get_logical_sources_for_run(db_path: str, run_id: str) -> list[dict[str, Any]]:
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT ls.* FROM logical_sources ls
               JOIN run_sources rs ON rs.logical_source_id = ls.id
               WHERE rs.run_id = ?""",
            (run_id,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def get_existing_fingerprints(db_path: str, fingerprints: list[str]) -> dict[str, str]:
    """Return {fingerprint: logical_source_id} for fingerprints already in DB."""
    if not fingerprints:
        return {}
    placeholders = ",".join("?" * len(fingerprints))
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            f"SELECT id, fingerprint FROM logical_sources WHERE fingerprint IN ({placeholders})",
            fingerprints,
        ) as cursor:
            rows = await cursor.fetchall()
            return {r["fingerprint"]: r["id"] for r in rows}


async def get_annotations_for_source_ids(db_path: str, source_ids: list[str]) -> list[dict[str, Any]]:
    """Return the most recent annotation row for each logical_source_id."""
    if not source_ids:
        return []
    placeholders = ",".join("?" * len(source_ids))
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            f"""SELECT a.* FROM annotations a
                INNER JOIN (
                    SELECT logical_source_id, MAX(id) AS max_id
                    FROM annotations
                    WHERE logical_source_id IN ({placeholders})
                    GROUP BY logical_source_id
                ) latest ON a.id = latest.max_id""",
            source_ids,
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def log_silent_item(
    db_path: str,
    claim_text: str,
    correctness: str,
    effort: str,
    confidence: float,
    rationale: str,
    run_id: str,
) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """INSERT INTO silent_log (claim_text, correctness, effort, confidence, rationale, run_id, timestamp)
               VALUES (?,?,?,?,?,?,?)""",
            (claim_text, correctness, effort, confidence, rationale, run_id, datetime.utcnow().isoformat()),
        )
        await db.commit()


async def save_annotation(
    db_path: str,
    logical_source_id: str,
    run_id: str,
    relevance: float,
    key_findings: list[str],
    credibility_tier: str,
) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """INSERT OR REPLACE INTO annotations
               (logical_source_id, run_id, relevance, key_findings, credibility_tier)
               VALUES (?,?,?,?,?)""",
            (logical_source_id, run_id, relevance, json.dumps(key_findings), credibility_tier),
        )
        await db.commit()
