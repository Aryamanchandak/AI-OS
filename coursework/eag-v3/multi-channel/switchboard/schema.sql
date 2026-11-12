-- Switchboard storage. SQLite + WAL, single user.
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------------------
-- Ingest
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS messages (
    id              TEXT PRIMARY KEY,
    channel         TEXT NOT NULL,
    channel_msg_id  TEXT NOT NULL,
    thread_id       TEXT,
    reply_anchor    TEXT NOT NULL DEFAULT '{}',   -- JSON
    sender_handle   TEXT NOT NULL,
    sender_name     TEXT,
    person_id       TEXT,   -- no FK: identities is keyed (channel, handle)
    subject         TEXT,
    body            TEXT NOT NULL DEFAULT '',
    attachments     TEXT NOT NULL DEFAULT '[]',   -- JSON
    sent_at         TEXT NOT NULL,                -- UTC ISO8601
    ingested_at     TEXT NOT NULL DEFAULT (datetime('now')),
    state           TEXT NOT NULL DEFAULT 'new',
    raw             TEXT NOT NULL DEFAULT '{}',   -- JSON

    -- The dedup guarantee. Re-ingest is a no-op, so restarts are safe.
    UNIQUE (channel, channel_msg_id)
);

CREATE INDEX IF NOT EXISTS idx_messages_state ON messages (state);
CREATE INDEX IF NOT EXISTS idx_messages_thread ON messages (channel, thread_id);
CREATE INDEX IF NOT EXISTS idx_messages_sent_at ON messages (sent_at);

-- Poll position per channel. Committed only AFTER successful ingest.
-- Without this, every restart re-triages the whole inbox.
CREATE TABLE IF NOT EXISTS channel_cursors (
    channel              TEXT PRIMARY KEY,
    cursor               TEXT,            -- gmail historyId / telegram update_id / slack ts
    last_successful_poll TEXT,            -- heartbeat: stale => poller is dead
    last_error           TEXT,
    updated_at           TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Same human across channels.
CREATE TABLE IF NOT EXISTS identities (
    person_id    TEXT NOT NULL,
    channel      TEXT NOT NULL,
    handle       TEXT NOT NULL,
    display_name TEXT,
    PRIMARY KEY (channel, handle)
);
CREATE INDEX IF NOT EXISTS idx_identities_person ON identities (person_id);

-- Senders to never triage (learned + manual).
CREATE TABLE IF NOT EXISTS mutes (
    channel    TEXT NOT NULL,
    handle     TEXT NOT NULL,
    reason     TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (channel, handle)
);

-- ---------------------------------------------------------------------------
-- Triage + drafting
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS triage (
    message_id  TEXT PRIMARY KEY REFERENCES messages(id) ON DELETE CASCADE,
    needs_reply INTEGER NOT NULL,
    urgency     TEXT NOT NULL,
    intent      TEXT NOT NULL,
    confidence  REAL NOT NULL,
    reasoning   TEXT,
    extracted   TEXT NOT NULL DEFAULT '{}',   -- JSON
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS drafts (
    id         TEXT PRIMARY KEY,
    message_id TEXT NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    version    INTEGER NOT NULL DEFAULT 1,
    subject    TEXT,
    body       TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (message_id, version)
);

-- Your edits become few-shot examples for later drafts. Highest-leverage
-- feedback loop in the system, and it costs nothing to collect.
CREATE TABLE IF NOT EXISTS draft_edits (
    id           TEXT PRIMARY KEY,
    draft_id     TEXT NOT NULL REFERENCES drafts(id) ON DELETE CASCADE,
    original     TEXT NOT NULL,
    edited       TEXT NOT NULL,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ---------------------------------------------------------------------------
-- Actions + approvals
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS actions (
    id              TEXT PRIMARY KEY,
    message_id      TEXT NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    action_type     TEXT NOT NULL,
    payload         TEXT NOT NULL,               -- JSON, schema-validated
    requires_approval INTEGER NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending',  -- pending|approved|rejected|executed|failed
    result          TEXT,
    attempts        INTEGER NOT NULL DEFAULT 0,
    last_error      TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    executed_at     TEXT,

    -- Replaying a plan cannot create the same event twice.
    UNIQUE (message_id, action_type)
);
CREATE INDEX IF NOT EXISTS idx_actions_status ON actions (status);

-- One row per approval prompt sent. The token is bound to a specific draft
-- version, so a stale button fails closed instead of double-sending.
CREATE TABLE IF NOT EXISTS approvals (
    token        TEXT PRIMARY KEY,
    action_id    TEXT NOT NULL REFERENCES actions(id) ON DELETE CASCADE,
    draft_id     TEXT REFERENCES drafts(id) ON DELETE CASCADE,
    surface      TEXT NOT NULL,          -- telegram | web
    decision     TEXT,                   -- approve|edit|reject|snooze
    decided_at   TEXT,
    snooze_until TEXT,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ---------------------------------------------------------------------------
-- Action outputs
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS tasks (
    id         TEXT PRIMARY KEY,
    message_id TEXT REFERENCES messages(id) ON DELETE SET NULL,
    title      TEXT NOT NULL,
    notes      TEXT,
    due_at     TEXT,
    done       INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS reminders (
    id         TEXT PRIMARY KEY,
    message_id TEXT REFERENCES messages(id) ON DELETE SET NULL,
    text       TEXT NOT NULL,
    remind_at  TEXT NOT NULL,
    fired      INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_reminders_due ON reminders (remind_at, fired);

CREATE TABLE IF NOT EXISTS documents (
    id         TEXT PRIMARY KEY,
    message_id TEXT REFERENCES messages(id) ON DELETE SET NULL,
    title      TEXT NOT NULL,
    body       TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ---------------------------------------------------------------------------
-- Observability
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS llm_calls (
    id            TEXT PRIMARY KEY,
    message_id    TEXT,
    purpose       TEXT NOT NULL,      -- triage | draft | document
    model         TEXT NOT NULL,
    input_tokens  INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_llm_calls_created ON llm_calls (created_at);

CREATE TABLE IF NOT EXISTS style_profile (
    id         TEXT PRIMARY KEY,
    person_id  TEXT,                 -- NULL = global default voice
    profile    TEXT NOT NULL,        -- JSON
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
