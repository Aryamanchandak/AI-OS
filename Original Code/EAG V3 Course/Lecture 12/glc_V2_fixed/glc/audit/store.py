"""Append-only, hash-chained SQLite audit log.

Every channel message, agent decision, policy verdict, and tool dispatch
lands here. Append-only is enforced at the application layer: only
`append()` is exposed; there is no update or delete function. The schema
ships at `audit_schema` version 2; bumping it requires a documented
migration step (see schema.sql, and `_migrate_v1_to_v2` below).

Application-layer append-only isn't the only line of defense (Leak 2):
each row also stores `row_hash = sha256(prev_hash || row fields)`, chaining
it to the row before it. Restricting who can reach the Volume (Phase 1)
stops adapters from touching this file at all, but it doesn't stop a bug —
or a compromise — *inside* the gateway process from doing a raw
`sqlite3.connect(...).execute("UPDATE/DELETE ...")`. The hash chain doesn't
prevent that (nothing at the SQL layer can, against someone with the file);
it makes it detectable: `verify_chain()` recomputes the chain from scratch
and reports the first row where it breaks.

Post-audit hardening: an in-table hash chain alone only catches *mid-chain*
tampering — a row whose neighbours still exist to disagree with it. It does
NOT catch truncation: `DELETE FROM audit_log` (removing everything) or
`DELETE ... WHERE id = (SELECT MAX(id) ...)` (removing just the tail)
leaves whatever rows remain perfectly self-consistent, because there's
nothing left in the table that references the missing rows. Confirmed by
direct repro: both shapes returned `ok: True` from the pre-fix
`verify_chain()`. The fix is an external anchor — a small checkpoint file
written next to (not inside) `audit_log` on every successful `append()`,
recording the current row count and tip hash. `verify_chain()` now cross-
checks the table's actual tip/count against that checkpoint; either DELETE
shape now changes the count and/or the tip hash, which no longer matches
what was last legitimately checkpointed. An attacker with filesystem access
can still delete or edit the checkpoint file too, but now has to keep TWO
independent files consistent instead of one — same "detectable, not
unconditionally preventable" posture as the row-level chain, extended to
cover the tail. `verify_chain()` also now runs automatically at
`init_store()` (startup), instead of only on-demand.

Each append commits immediately so writes survive a hard kill.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any

DEFAULT_DIR = Path(os.path.expanduser("~/.glc"))


def _default_dir() -> Path:
    """The base directory for the audit DB when GLC_AUDIT_DB is unset.

    Follows GLC_CONFIG_DIR (the same knob glc.config honors) so the DB lands
    on the persistent Modal Volume (/data/glc) rather than the gateway
    container's ephemeral ~/.glc, which is wiped on every redeploy/restart —
    silently truncating the Phase 2/6 hash-chained audit log. Resolved at
    call time to match GLC_AUDIT_DB's own semantics."""
    return Path(os.getenv("GLC_CONFIG_DIR", str(DEFAULT_DIR)))


def _resolve_path() -> str:
    """Resolve at call time, not import time, so tests that swap the env
    var see the change."""
    return os.getenv("GLC_AUDIT_DB", str(_default_dir() / "audit.sqlite"))


@contextmanager
def _conn():
    p = _resolve_path()
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(p, isolation_level=None)  # autocommit; each insert flushes
    c.row_factory = sqlite3.Row
    try:
        yield c
    finally:
        c.close()


_SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def _checkpoint_path() -> str:
    """External anchor file, deliberately NOT inside audit_log's own table
    or even the same file — a `DELETE FROM audit_log` never touches this."""
    return str(Path(_resolve_path()).parent / "audit_chain_checkpoint.json")


def _write_checkpoint(*, row_count: int, last_id: int | None, tip_hash: str) -> None:
    data = {"row_count": row_count, "last_id": last_id, "tip_hash": tip_hash}
    p = _checkpoint_path()
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f)
    os.replace(tmp, p)  # atomic on POSIX -- no half-written checkpoint on crash


def _read_checkpoint() -> dict[str, Any] | None:
    p = _checkpoint_path()
    if not os.path.exists(p):
        return None
    try:
        with open(p) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def init_store() -> None:
    with _conn() as c:
        c.executescript(_SCHEMA_PATH.read_text())
        _migrate_v1_to_v2(c)
        if _read_checkpoint() is None:
            # Bootstrap the anchor to whatever the table's current tip
            # actually is (fresh DB: count=0, tip=""). Can't retroactively
            # protect history from before this code existed, same as
            # _migrate_v1_to_v2 grandfathering in pre-hash-chain rows.
            count_row = c.execute("SELECT COUNT(*) AS n FROM audit_log").fetchone()
            last = c.execute("SELECT id, row_hash FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
            _write_checkpoint(
                row_count=int(count_row["n"]),
                last_id=(last["id"] if last else None),
                tip_hash=(last["row_hash"] if last else ""),
            )

    result = verify_chain()
    if not result["ok"]:
        import logging

        logging.getLogger(__name__).error(
            "audit chain verification FAILED at startup: %s -- the audit log "
            "may have been tampered with or truncated outside append()",
            result,
        )
        try:
            # A permanent, visible record of the detection itself, chained
            # from the current (post-tamper) tip going forward. Uses
            # AuditStore directly, not get_store()/append() -- those call
            # init_store(), which is what's currently running.
            AuditStore().append(
                channel="_system",
                channel_user_id="_system",
                trust_level="owner_paired",
                event_type="audit_chain_verification_failed",
                result=result,
            )
        except Exception:
            pass


def _migrate_v1_to_v2(c: sqlite3.Connection) -> None:
    """Pre-existing v1 databases were created before `prev_hash`/`row_hash`
    existed. `CREATE TABLE IF NOT EXISTS` in schema.sql is a no-op against an
    already-existing table, so those columns have to be added and backfilled
    explicitly. No-op on a fresh v2 database (columns already present)."""
    cols = {row["name"] for row in c.execute("PRAGMA table_info(audit_log)")}
    if "row_hash" in cols:
        return
    c.execute("ALTER TABLE audit_log ADD COLUMN prev_hash TEXT")
    c.execute("ALTER TABLE audit_log ADD COLUMN row_hash TEXT NOT NULL DEFAULT ''")
    prev_hash = ""
    for row in c.execute("SELECT * FROM audit_log ORDER BY id ASC").fetchall():
        row_hash = _row_hash(prev_hash, row)
        c.execute(
            "UPDATE audit_log SET prev_hash=?, row_hash=? WHERE id=?",
            (prev_hash, row_hash, row["id"]),
        )
        prev_hash = row_hash
    c.execute("INSERT OR IGNORE INTO audit_schema (version, applied_at) VALUES (2, ?)", (time.time(),))


def _jsonify(v: Any) -> str | None:
    if v is None:
        return None
    if isinstance(v, str):
        return v
    try:
        return json.dumps(v, default=str)
    except Exception:
        return json.dumps({"_repr": repr(v)})


def _row_hash(prev_hash: str, row: Any) -> str:
    """sha256(prev_hash || this row's own fields). `row` is anything
    subscriptable by column name (sqlite3.Row or a plain dict of the same
    shape) -- id/prev_hash/row_hash themselves are excluded since row_hash
    is what we're computing and id/prev_hash aren't "this row's content"."""
    fields = (
        row["ts"], row["session_id"], row["channel"], row["channel_user_id"],
        row["trust_level"], row["event_type"], row["tool"], row["policy_verdict"],
        row["params_json"], row["result_json"],
    )
    payload = "|".join("" if f is None else str(f) for f in (prev_hash, *fields))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class AuditStore:
    """Application-layer write-once store. The class deliberately exposes
    no update or delete methods. Reads (for the replay viewer) live in
    query() which is read-only."""

    def append(
        self,
        *,
        channel: str,
        channel_user_id: str,
        trust_level: str,
        event_type: str,
        session_id: str | None = None,
        tool: str | None = None,
        policy_verdict: str | None = None,
        params: Any = None,
        result: Any = None,
    ) -> int:
        row = {
            "ts": time.time(),
            "session_id": session_id,
            "channel": channel,
            "channel_user_id": channel_user_id,
            "trust_level": trust_level,
            "event_type": event_type,
            "tool": tool,
            "policy_verdict": policy_verdict,
            "params_json": _jsonify(params),
            "result_json": _jsonify(result),
        }
        with _conn() as c:
            # BEGIN IMMEDIATE takes the write lock up front so the
            # read-last-hash + insert-next-hash pair can't race against a
            # concurrent writer and chain off a stale prev_hash.
            c.execute("BEGIN IMMEDIATE")
            try:
                last = c.execute("SELECT row_hash FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
                prev_hash = last["row_hash"] if last else ""
                row_hash = _row_hash(prev_hash, row)
                cur = c.execute(
                    """INSERT INTO audit_log
                       (ts, session_id, channel, channel_user_id, trust_level,
                        event_type, tool, policy_verdict, params_json, result_json,
                        prev_hash, row_hash)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        row["ts"], row["session_id"], row["channel"], row["channel_user_id"],
                        row["trust_level"], row["event_type"], row["tool"], row["policy_verdict"],
                        row["params_json"], row["result_json"], prev_hash, row_hash,
                    ),
                )
                c.execute("COMMIT")
                new_id = int(cur.lastrowid or 0)
                count_row = c.execute("SELECT COUNT(*) AS n FROM audit_log").fetchone()
                _write_checkpoint(row_count=int(count_row["n"]), last_id=new_id, tip_hash=row_hash)
                return new_id
            except Exception:
                c.execute("ROLLBACK")
                raise


_singleton: AuditStore | None = None


def get_store() -> AuditStore:
    global _singleton
    if _singleton is None:
        init_store()
        _singleton = AuditStore()
    return _singleton


def append(**kwargs: Any) -> int:
    return get_store().append(**kwargs)


def query(limit: int = 100, session_id: str | None = None, channel: str | None = None) -> list[dict]:
    q = "SELECT * FROM audit_log"
    where, args = [], []
    if session_id:
        where.append("session_id=?")
        args.append(session_id)
    if channel:
        where.append("channel=?")
        args.append(channel)
    if where:
        q += " WHERE " + " AND ".join(where)
    q += " ORDER BY ts DESC LIMIT ?"
    args.append(limit)
    with _conn() as c:
        return [dict(r) for r in c.execute(q, args).fetchall()]


def schema_version() -> int:
    with _conn() as c:
        row = c.execute("SELECT MAX(version) AS v FROM audit_schema").fetchone()
        return int(row["v"] or 0)


def verify_chain() -> dict[str, Any]:
    """Recompute the hash chain over the whole log in id order (oldest
    first) and report the first row, if any, whose stored `prev_hash` /
    `row_hash` doesn't match what its own fields actually hash to.

    A mismatch means that row (or one before it) was inserted, edited, or
    removed by something other than `append()` -- an UPDATE/DELETE run
    directly against the sqlite file, bypassing this module entirely. This
    is the detection half of Leak 2's fix: append-only-by-convention can't
    stop that kind of write, so this is what catches it after the fact.

    An in-table walk alone can't see *truncation* (deleting the tail, or
    everything) -- the remaining rows are still mutually consistent, there's
    just nothing left to disagree with the missing ones. After the in-table
    walk passes, this also cross-checks the external checkpoint (see
    `_write_checkpoint`); a mismatch there is reported as `ok: False` with
    `broken_at_id: None` and a `reason` explaining it's a truncation, not a
    mid-chain edit.
    """
    with _conn() as c:
        rows = c.execute("SELECT * FROM audit_log ORDER BY id ASC").fetchall()
    prev_hash = ""
    for row in rows:
        expected = _row_hash(prev_hash, row)
        if row["prev_hash"] != prev_hash or row["row_hash"] != expected:
            return {"ok": False, "broken_at_id": row["id"], "row_count": len(rows)}
        prev_hash = row["row_hash"]

    checkpoint = _read_checkpoint()
    if checkpoint is not None:
        actual_tip = rows[-1]["row_hash"] if rows else ""
        actual_count = len(rows)
        if checkpoint["row_count"] != actual_count or checkpoint["tip_hash"] != actual_tip:
            return {
                "ok": False,
                "broken_at_id": None,
                "row_count": actual_count,
                "reason": (
                    f"chain truncated: checkpoint expected {checkpoint['row_count']} row(s) "
                    f"ending at id={checkpoint.get('last_id')}, found {actual_count} row(s)"
                ),
            }

    return {"ok": True, "broken_at_id": None, "row_count": len(rows)}
