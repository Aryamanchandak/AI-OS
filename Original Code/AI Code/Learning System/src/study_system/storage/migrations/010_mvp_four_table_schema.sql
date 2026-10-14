-- MVP schema from plans/00_RESOLVED_MVP_AND_ARCHITECTURE.md.
-- This schema is intended for the central study SQLite database and contains
-- exactly the four study-owned tables: cards, review_state, generation_runs,
-- overrides.

CREATE TABLE IF NOT EXISTS cards (
    id TEXT PRIMARY KEY,
    concept_id TEXT NOT NULL,
    card_type TEXT NOT NULL,
    front TEXT NOT NULL,
    back TEXT NOT NULL,
    source_refs_json TEXT NOT NULL,
    source_version TEXT,
    created_at TEXT NOT NULL,
    model TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    deleted_at TEXT
);

CREATE TABLE IF NOT EXISTS review_state (
    card_id TEXT PRIMARY KEY,
    stability REAL NOT NULL DEFAULT 0,
    difficulty REAL NOT NULL DEFAULT 5,
    elapsed_days INTEGER NOT NULL DEFAULT 0,
    scheduled_days INTEGER NOT NULL DEFAULT 0,
    reps INTEGER NOT NULL DEFAULT 0,
    lapses INTEGER NOT NULL DEFAULT 0,
    state TEXT NOT NULL DEFAULT 'new',
    due_at TEXT,
    last_reviewed_at TEXT,
    evidence_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY(card_id) REFERENCES cards(id)
);

CREATE TABLE IF NOT EXISTS generation_runs (
    id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    operation TEXT NOT NULL,
    selection_code TEXT NOT NULL,
    effective_config_json TEXT NOT NULL,
    selected_concept_ids_json TEXT NOT NULL,
    outcome TEXT NOT NULL,
    error TEXT
);

CREATE TABLE IF NOT EXISTS overrides (
    id TEXT PRIMARY KEY,
    setting TEXT NOT NULL,
    value_json TEXT NOT NULL,
    starts_on TEXT NOT NULL,
    expires_on TEXT NOT NULL,
    reason TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    cancelled_at TEXT
);
