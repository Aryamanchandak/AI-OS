"""
state.py — SQLite state management for episode tracking and dedup.
"""

import sqlite3
from pathlib import Path
from .config import DATA_DIR, ensure_dirs


def _db_path() -> Path:
    return DATA_DIR / "state.db"


def get_connection() -> sqlite3.Connection:
    ensure_dirs()
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create tables if they don't exist. Safe to call repeatedly."""
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS episodes (
            id              TEXT PRIMARY KEY,
            show_name       TEXT NOT NULL,
            title           TEXT,
            source_url      TEXT,
            audio_path      TEXT,
            transcript_path TEXT,
            brief_path      TEXT,
            reader_url      TEXT,
            profile         TEXT,
            status          TEXT DEFAULT 'pending',
            error           TEXT,
            created_at      TEXT DEFAULT (datetime('now')),
            completed_at    TEXT
        );

        CREATE TABLE IF NOT EXISTS runs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            episode_id  TEXT,
            stage       TEXT,
            status      TEXT,
            message     TEXT,
            started_at  TEXT DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_episodes_status ON episodes(status);
        CREATE INDEX IF NOT EXISTS idx_runs_episode ON runs(episode_id);
    """)
    conn.commit()

    # Safe migration: add research_run_id column if it doesn't exist yet
    try:
        conn.execute("ALTER TABLE episodes ADD COLUMN research_run_id TEXT")
        conn.commit()
    except sqlite3.OperationalError:
        pass  # column already exists

    conn.close()


def episode_exists(episode_id: str) -> bool:
    """True if this episode has already been processed successfully."""
    conn = get_connection()
    row = conn.execute(
        "SELECT id FROM episodes WHERE id = ? AND status = 'completed'",
        (episode_id,),
    ).fetchone()
    conn.close()
    return row is not None


def create_episode(episode_id: str, show_name: str, title: str,
                   source_url: str, profile: str):
    conn = get_connection()
    conn.execute(
        """INSERT OR REPLACE INTO episodes
           (id, show_name, title, source_url, profile, status)
           VALUES (?, ?, ?, ?, ?, 'pending')""",
        (episode_id, show_name, title, source_url, profile),
    )
    conn.commit()
    conn.close()


def update_episode(episode_id: str, **kwargs):
    if not kwargs:
        return
    fields = ", ".join(f"{k} = ?" for k in kwargs)
    values = list(kwargs.values()) + [episode_id]
    conn = get_connection()
    conn.execute(f"UPDATE episodes SET {fields} WHERE id = ?", values)
    conn.commit()
    conn.close()


def mark_completed(episode_id: str, reader_url: str, brief_path: str):
    conn = get_connection()
    conn.execute(
        """UPDATE episodes
           SET status = 'completed',
               reader_url = ?,
               brief_path = ?,
               completed_at = datetime('now')
           WHERE id = ?""",
        (reader_url, brief_path, episode_id),
    )
    conn.commit()
    conn.close()


def mark_failed(episode_id: str, error: str):
    conn = get_connection()
    conn.execute(
        "UPDATE episodes SET status = 'error', error = ? WHERE id = ?",
        (error[:1000], episode_id),
    )
    conn.commit()
    conn.close()


def log_run(episode_id: str, stage: str, status: str, message: str = ""):
    conn = get_connection()
    conn.execute(
        "INSERT INTO runs (episode_id, stage, status, message) VALUES (?, ?, ?, ?)",
        (episode_id, stage, status, message[:500]),
    )
    conn.commit()
    conn.close()


def get_recent_episodes(limit: int = 20) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM episodes ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_episode(episode_id: str) -> dict | None:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM episodes WHERE id = ?", (episode_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_runs(episode_id: str) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM runs WHERE episode_id = ? ORDER BY id ASC", (episode_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
