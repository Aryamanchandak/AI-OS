CREATE TABLE IF NOT EXISTS items (
    content_hash  TEXT PRIMARY KEY,
    item_id       TEXT NOT NULL,
    source        TEXT NOT NULL,
    captured_at   TEXT NOT NULL,
    bronze_path   TEXT NOT NULL,
    authored      INTEGER NOT NULL DEFAULT 0,
    metadata      TEXT
);
CREATE TABLE IF NOT EXISTS processing (
    content_hash  TEXT NOT NULL REFERENCES items(content_hash),
    target        TEXT NOT NULL,
    stage         TEXT NOT NULL,
    status        TEXT NOT NULL,
    artifact_path TEXT,
    attempted_at  TEXT,
    error         TEXT,
    PRIMARY KEY (content_hash, target, stage)
);
CREATE TABLE IF NOT EXISTS runs (
    run_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    target        TEXT,
    started_at    TEXT NOT NULL,
    finished_at   TEXT,
    items_seen    INTEGER DEFAULT 0,
    items_done    INTEGER DEFAULT 0,
    items_failed  INTEGER DEFAULT 0,
    status        TEXT
);
CREATE INDEX IF NOT EXISTS idx_proc_lookup ON processing(target, stage, status);
