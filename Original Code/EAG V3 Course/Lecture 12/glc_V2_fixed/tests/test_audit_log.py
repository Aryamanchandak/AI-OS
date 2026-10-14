"""Append-only audit log — write correctness, restart survival,
no-update/no-delete surface."""

from __future__ import annotations

import sqlite3

from glc.audit import store
from glc.audit.store import AuditStore, append, init_store, query, schema_version, verify_chain


def test_init_then_append():
    init_store()
    rid = append(
        channel="telegram",
        channel_user_id="42",
        trust_level="owner_paired",
        event_type="inbound_message",
        session_id="s1",
        params={"text": "hi"},
    )
    assert rid > 0
    rows = query(limit=5)
    assert len(rows) == 1
    assert rows[0]["channel"] == "telegram"
    assert rows[0]["event_type"] == "inbound_message"


def test_write_survives_restart(monkeypatch, tmp_path):
    init_store()
    append(channel="x", channel_user_id="1", trust_level="owner_paired", event_type="boot")
    store._singleton = None  # simulate process restart
    rows = query(limit=10)
    assert len(rows) == 1


def test_store_exposes_no_update_or_delete():
    s = AuditStore()
    assert not hasattr(s, "update")
    assert not hasattr(s, "delete")
    public = [n for n in dir(s) if not n.startswith("_")]
    assert "append" in public
    assert len([n for n in public if n in ("update", "delete", "modify")]) == 0


def test_schema_version_is_two():
    init_store()
    assert schema_version() == 2


def test_query_filters_by_session_and_channel():
    init_store()
    append(
        channel="discord", channel_user_id="1", trust_level="owner_paired", event_type="x", session_id="s-A"
    )
    append(
        channel="telegram", channel_user_id="1", trust_level="owner_paired", event_type="x", session_id="s-B"
    )
    rows = query(session_id="s-A")
    assert len(rows) == 1
    assert rows[0]["channel"] == "discord"
    rows = query(channel="telegram")
    assert len(rows) == 1


def test_jsonifies_complex_params():
    init_store()
    append(
        channel="x",
        channel_user_id="1",
        trust_level="owner_paired",
        event_type="x",
        params={"nested": {"k": [1, 2, 3]}},
    )
    rows = query(limit=1)
    assert "nested" in rows[0]["params_json"]


# --- Leak 2: hash-chained rows -------------------------------------------
# Restricting Volume access (Phase 1) stops adapters from touching this
# file, but nothing at the SQL layer stops a raw sqlite3 UPDATE/DELETE run
# from inside the gateway process. These tests are the "before"/"after" for
# that: append() alone chains rows so tampering (from *any* in-process code,
# not just an adapter) is detectable, even though the row itself can still
# be physically edited on disk.


def test_hash_chain_links_sequential_rows():
    init_store()
    ids = [
        append(channel="x", channel_user_id="1", trust_level="owner_paired", event_type=f"e{i}")
        for i in range(5)
    ]
    assert len(ids) == 5
    assert verify_chain() == {"ok": True, "broken_at_id": None, "row_count": 5}


def test_hash_chain_first_row_has_empty_prev_hash():
    init_store()
    append(channel="x", channel_user_id="1", trust_level="owner_paired", event_type="first")
    rows = query(limit=1)
    assert rows[0]["prev_hash"] == ""
    assert rows[0]["row_hash"]


def test_hash_chain_detects_raw_sqlite_tamper():
    """Leak 2 repro: `sqlite3.connect(path).execute("UPDATE ...")` from any
    in-process code (the original exploit used DELETE) silently rewrites a
    row. Before this fix there was nothing to notice. After: verify_chain()
    flags the exact row where the recomputed hash stops matching."""
    init_store()
    append(channel="x", channel_user_id="1", trust_level="owner_paired", event_type="a")
    tampered_id = append(channel="x", channel_user_id="1", trust_level="owner_paired", event_type="b")
    append(channel="x", channel_user_id="1", trust_level="owner_paired", event_type="c")
    assert verify_chain()["ok"] is True

    path = store._resolve_path()
    conn = sqlite3.connect(path)
    conn.execute("UPDATE audit_log SET event_type='FORGED' WHERE id=?", (tampered_id,))
    conn.commit()
    conn.close()

    result = verify_chain()
    assert result["ok"] is False
    assert result["broken_at_id"] == tampered_id


def test_hash_chain_detects_raw_sqlite_delete():
    """Same exploit shape as the original Leak 2 repro
    (`DELETE FROM audit_log`), but targeting a single row instead of the
    whole table -- the more realistic "quietly remove one incriminating
    entry" attack. The gap breaks every subsequent row's prev_hash link."""
    init_store()
    append(channel="x", channel_user_id="1", trust_level="owner_paired", event_type="a")
    doomed_id = append(channel="x", channel_user_id="1", trust_level="owner_paired", event_type="b")
    append(channel="x", channel_user_id="1", trust_level="owner_paired", event_type="c")
    assert verify_chain()["ok"] is True

    path = store._resolve_path()
    conn = sqlite3.connect(path)
    conn.execute("DELETE FROM audit_log WHERE id=?", (doomed_id,))
    conn.commit()
    conn.close()

    result = verify_chain()
    assert result["ok"] is False


# --- Post-audit fix: truncation detection (external checkpoint) --------
# Codex's exact repro against the pre-fix code: `DELETE FROM audit_log`
# (whole table) and deleting just the last row both returned `ok: True`,
# because the in-table hash chain has nothing left to disagree with rows
# that no longer exist. These tests reproduce both shapes and assert they
# are now caught via the external checkpoint file.


def test_hash_chain_detects_delete_all_rows():
    init_store()
    append(channel="x", channel_user_id="1", trust_level="owner_paired", event_type="a")
    append(channel="x", channel_user_id="1", trust_level="owner_paired", event_type="b")
    assert verify_chain()["ok"] is True

    path = store._resolve_path()
    conn = sqlite3.connect(path)
    conn.execute("DELETE FROM audit_log")
    conn.commit()
    conn.close()

    result = verify_chain()
    assert result["ok"] is False
    assert result["row_count"] == 0
    assert "truncated" in result.get("reason", "")


def test_hash_chain_detects_delete_last_row():
    init_store()
    append(channel="x", channel_user_id="1", trust_level="owner_paired", event_type="a")
    doomed_id = append(channel="x", channel_user_id="1", trust_level="owner_paired", event_type="b")
    assert verify_chain()["ok"] is True

    path = store._resolve_path()
    conn = sqlite3.connect(path)
    conn.execute("DELETE FROM audit_log WHERE id=?", (doomed_id,))
    conn.commit()
    conn.close()

    # The in-table walk alone would say ok (the one remaining row is
    # internally consistent) -- only the checkpoint cross-check catches this.
    result = verify_chain()
    assert result["ok"] is False
    assert result["broken_at_id"] is None
    assert "truncated" in result.get("reason", "")


def test_new_append_after_truncation_still_gets_recorded_and_resyncs_checkpoint():
    """A truncation is detected, but the log must keep working afterwards --
    the next legitimate append() re-syncs the checkpoint to the new (post-
    tamper) reality, and that new row is itself verifiable going forward."""
    init_store()
    append(channel="x", channel_user_id="1", trust_level="owner_paired", event_type="a")
    doomed_id = append(channel="x", channel_user_id="1", trust_level="owner_paired", event_type="b")

    path = store._resolve_path()
    conn = sqlite3.connect(path)
    conn.execute("DELETE FROM audit_log WHERE id=?", (doomed_id,))
    conn.commit()
    conn.close()
    assert verify_chain()["ok"] is False

    append(channel="x", channel_user_id="1", trust_level="owner_paired", event_type="c")
    assert verify_chain()["ok"] is True


def test_init_store_auto_verifies_and_records_detected_tampering_on_restart(monkeypatch, tmp_path):
    """verify_chain() must run automatically at startup (init_store()), not
    only when something remembers to call it by hand -- and a detected
    truncation should leave a visible record in the log itself."""
    db_path = tmp_path / "audit.sqlite"
    monkeypatch.setenv("GLC_AUDIT_DB", str(db_path))
    store._singleton = None
    init_store()
    append(channel="x", channel_user_id="1", trust_level="owner_paired", event_type="a")
    doomed_id = append(channel="x", channel_user_id="1", trust_level="owner_paired", event_type="b")

    conn = sqlite3.connect(str(db_path))
    conn.execute("DELETE FROM audit_log WHERE id=?", (doomed_id,))
    conn.commit()
    conn.close()

    store._singleton = None  # simulate a gateway restart
    init_store()  # must not raise; detection is logged + recorded, not fatal

    rows = query(limit=10)
    assert any(r["event_type"] == "audit_chain_verification_failed" for r in rows)


def test_v1_database_migrates_and_backfills_chain(tmp_path, monkeypatch):
    """A pre-existing v1 database (no prev_hash/row_hash columns) must be
    upgradable in place: init_store() adds the columns and backfills a valid
    chain over whatever rows already existed, rather than requiring a
    from-scratch database."""
    v1_path = tmp_path / "legacy_v1.sqlite"
    conn = sqlite3.connect(str(v1_path))
    conn.execute(
        """CREATE TABLE audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL, session_id TEXT,
            channel TEXT NOT NULL, channel_user_id TEXT NOT NULL, trust_level TEXT NOT NULL,
            event_type TEXT NOT NULL, tool TEXT, policy_verdict TEXT, params_json TEXT, result_json TEXT
        )"""
    )
    conn.execute(
        "INSERT INTO audit_log (ts, channel, channel_user_id, trust_level, event_type) VALUES (1.0,'x','1','owner_paired','legacy')"
    )
    conn.execute("CREATE TABLE audit_schema (version INTEGER PRIMARY KEY, applied_at REAL NOT NULL)")
    conn.execute("INSERT INTO audit_schema (version, applied_at) VALUES (1, 1.0)")
    conn.commit()
    conn.close()

    monkeypatch.setenv("GLC_AUDIT_DB", str(v1_path))
    store._singleton = None
    init_store()

    assert schema_version() == 2
    result = verify_chain()
    assert result["ok"] is True
    assert result["row_count"] == 1
