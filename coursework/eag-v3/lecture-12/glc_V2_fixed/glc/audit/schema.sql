-- glc_v1 audit log. Append-only; the application layer never issues
-- UPDATE or DELETE against this table.
--
-- v2 (Leak 2 hardening): every row also carries `prev_hash` (the row_hash of
-- the previous row, "" for the first) and `row_hash` (sha256 of prev_hash +
-- this row's own fields). This doesn't stop someone with raw file access to
-- the Volume from editing sqlite bytes directly -- nothing at the SQL layer
-- can -- but it means any such edit, or any row deleted/reordered outside
-- append(), breaks the chain and is detected by verify_chain() on read.
-- Application code still never issues UPDATE/DELETE; this is a second,
-- independent line of defense against exactly the "gateway-side bug (or
-- gateway-side compromise) silently rewrites history" scenario that
-- restricting Volume access alone doesn't cover.

CREATE TABLE IF NOT EXISTS audit_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ts              REAL    NOT NULL,
    session_id      TEXT,
    channel         TEXT    NOT NULL,
    channel_user_id TEXT    NOT NULL,
    trust_level     TEXT    NOT NULL,
    event_type      TEXT    NOT NULL,
    tool            TEXT,
    policy_verdict  TEXT,
    params_json     TEXT,
    result_json     TEXT,
    prev_hash       TEXT,
    row_hash        TEXT    NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_log(ts DESC);
CREATE INDEX IF NOT EXISTS idx_audit_session ON audit_log(session_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_audit_channel ON audit_log(channel, ts DESC);

-- Schema version table: any change to the columns above requires a
-- documented version bump. Migrations are not automatic.
CREATE TABLE IF NOT EXISTS audit_schema (
    version INTEGER PRIMARY KEY,
    applied_at REAL NOT NULL
);
INSERT OR IGNORE INTO audit_schema (version, applied_at) VALUES (2, strftime('%s','now'));
