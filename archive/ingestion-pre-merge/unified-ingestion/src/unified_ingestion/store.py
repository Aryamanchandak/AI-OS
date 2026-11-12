from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Literal, cast

from unified_ingestion.models import IngestionEnvelope


SCHEMA = """
CREATE TABLE IF NOT EXISTS source_records (
    id TEXT PRIMARY KEY,
    raw_hash TEXT NOT NULL UNIQUE,
    normalized_hash TEXT NOT NULL,
    canonical_record_id TEXT NOT NULL,
    source_type TEXT NOT NULL,
    origin TEXT NOT NULL,
    normalized_origin TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    observed_at TEXT,
    raw_content_ref TEXT NOT NULL UNIQUE,
    version INTEGER NOT NULL,
    supersedes_record_id TEXT,
    source_status TEXT NOT NULL DEFAULT 'current',
    metadata_json TEXT NOT NULL,
    extracted_metadata_json TEXT NOT NULL,
    access_policy_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(supersedes_record_id) REFERENCES source_records(id)
);
CREATE INDEX IF NOT EXISTS idx_sources_normalized_hash ON source_records(normalized_hash);
CREATE INDEX IF NOT EXISTS idx_sources_origin ON source_records(source_type, normalized_origin, version);

CREATE TABLE IF NOT EXISTS captures (
    id TEXT PRIMARY KEY,
    source_record_id TEXT NOT NULL,
    source_type TEXT NOT NULL,
    origin TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    exact_duplicate INTEGER NOT NULL,
    normalized_duplicate INTEGER NOT NULL,
    metadata_json TEXT NOT NULL,
    FOREIGN KEY(source_record_id) REFERENCES source_records(id)
);

CREATE TABLE IF NOT EXISTS envelopes (
    id TEXT PRIMARY KEY,
    source_record_id TEXT NOT NULL,
    extraction_version TEXT NOT NULL,
    review_status TEXT NOT NULL,
    envelope_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(source_record_id) REFERENCES source_records(id),
    UNIQUE(source_record_id, extraction_version)
);

CREATE TABLE IF NOT EXISTS review_queue (
    id TEXT PRIMARY KEY,
    envelope_id TEXT NOT NULL UNIQUE,
    reason_json TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    resolved_at TEXT,
    resolver TEXT,
    resolution_note TEXT,
    FOREIGN KEY(envelope_id) REFERENCES envelopes(id)
);

CREATE TABLE IF NOT EXISTS dispatches (
    envelope_id TEXT NOT NULL,
    target TEXT NOT NULL,
    extraction_version TEXT NOT NULL,
    status TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    artifact_ref TEXT,
    error TEXT,
    attempted_at TEXT NOT NULL,
    PRIMARY KEY(envelope_id, target, extraction_version),
    FOREIGN KEY(envelope_id) REFERENCES envelopes(id)
);

CREATE TABLE IF NOT EXISTS quarantine (
    id TEXT PRIMARY KEY,
    request_json TEXT NOT NULL,
    error TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS legacy_references (
    legacy_source_id TEXT PRIMARY KEY,
    source_record_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(source_record_id) REFERENCES source_records(id)
);
"""


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class IngestionStore:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._conn = sqlite3.connect(str(path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def table_names(self) -> set[str]:
        rows = self._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        return {str(row[0]) for row in rows}

    def find_by_raw_hash(self, raw_hash: str) -> sqlite3.Row | None:
        return cast(
            sqlite3.Row | None,
            self._conn.execute("SELECT * FROM source_records WHERE raw_hash=?", (raw_hash,)).fetchone(),
        )

    def find_by_normalized_hash(self, normalized_hash: str) -> sqlite3.Row | None:
        return cast(
            sqlite3.Row | None,
            self._conn.execute(
                "SELECT * FROM source_records WHERE normalized_hash=? ORDER BY created_at LIMIT 1",
                (normalized_hash,),
            ).fetchone(),
        )

    def latest_for_origin(self, source_type: str, normalized_origin: str) -> sqlite3.Row | None:
        return cast(
            sqlite3.Row | None,
            self._conn.execute(
                """SELECT * FROM source_records
                   WHERE source_type=? AND normalized_origin=? AND id=canonical_record_id
                   ORDER BY version DESC LIMIT 1""",
                (source_type, normalized_origin),
            ).fetchone(),
        )

    def get_source(self, source_record_id: str) -> sqlite3.Row | None:
        return cast(
            sqlite3.Row | None,
            self._conn.execute("SELECT * FROM source_records WHERE id=?", (source_record_id,)).fetchone(),
        )

    def insert_source(
        self,
        *,
        source_record_id: str,
        raw_hash: str,
        normalized_hash: str,
        canonical_record_id: str,
        source_type: str,
        origin: str,
        normalized_origin: str,
        captured_at: str,
        observed_at: str | None,
        raw_content_ref: str,
        version: int,
        supersedes_record_id: str | None,
        metadata: dict[str, Any],
        extracted_metadata: dict[str, Any],
        access_policy: dict[str, Any],
        capture_id: str,
        capture_source_type: str,
        normalized_duplicate: bool,
        mark_superseded: bool,
    ) -> None:
        with self._conn:
            self._conn.execute(
                """INSERT INTO source_records
                   (id,raw_hash,normalized_hash,canonical_record_id,source_type,origin,
                    normalized_origin,captured_at,observed_at,raw_content_ref,version,
                    supersedes_record_id,metadata_json,extracted_metadata_json,
                    access_policy_json,created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    source_record_id,
                    raw_hash,
                    normalized_hash,
                    canonical_record_id,
                    source_type,
                    origin,
                    normalized_origin,
                    captured_at,
                    observed_at,
                    raw_content_ref,
                    version,
                    supersedes_record_id,
                    json.dumps(metadata, sort_keys=True, default=str),
                    json.dumps(extracted_metadata, sort_keys=True, default=str),
                    json.dumps(access_policy, sort_keys=True),
                    _utc_iso(),
                ),
            )
            self._conn.execute(
                """INSERT INTO captures
                   (id,source_record_id,source_type,origin,captured_at,exact_duplicate,
                    normalized_duplicate,metadata_json)
                   VALUES (?,?,?,?,?,0,?,?)""",
                (
                    capture_id,
                    source_record_id,
                    capture_source_type,
                    origin,
                    captured_at,
                    int(normalized_duplicate),
                    json.dumps(metadata, sort_keys=True, default=str),
                ),
            )
            if supersedes_record_id and mark_superseded:
                self._conn.execute(
                    "UPDATE source_records SET source_status='superseded' WHERE id=?",
                    (supersedes_record_id,),
                )
                prior_envelopes = self._conn.execute(
                    "SELECT id,envelope_json FROM envelopes WHERE source_record_id=?",
                    (supersedes_record_id,),
                ).fetchall()
                for prior in prior_envelopes:
                    envelope = IngestionEnvelope.model_validate_json(prior["envelope_json"])
                    envelope.source_status = "superseded"
                    for claim in envelope.semantic.claims:
                        claim.status = "superseded"
                    self._conn.execute(
                        "UPDATE envelopes SET envelope_json=? WHERE id=?",
                        (envelope.model_dump_json(), prior["id"]),
                    )

    def add_duplicate_capture(
        self,
        *,
        capture_id: str,
        source_record_id: str,
        source_type: str,
        origin: str,
        captured_at: str,
        metadata: dict[str, Any],
    ) -> None:
        with self._conn:
            self._conn.execute(
                """INSERT INTO captures
                   (id,source_record_id,source_type,origin,captured_at,exact_duplicate,
                    normalized_duplicate,metadata_json)
                   VALUES (?,?,?,?,?,1,0,?)""",
                (
                    capture_id,
                    source_record_id,
                    source_type,
                    origin,
                    captured_at,
                    json.dumps(metadata, sort_keys=True, default=str),
                ),
            )

    def pending_sources(self, extraction_version: str, limit: int = 100) -> list[sqlite3.Row]:
        return self._conn.execute(
            """SELECT s.* FROM source_records s
               WHERE s.id=s.canonical_record_id
                 AND NOT EXISTS (
                     SELECT 1 FROM envelopes e
                     WHERE e.source_record_id=s.id AND e.extraction_version=?
                 )
               ORDER BY s.captured_at, s.id LIMIT ?""",
            (extraction_version, limit),
        ).fetchall()

    def save_envelope(self, envelope: IngestionEnvelope) -> None:
        with self._conn:
            self._conn.execute(
                """INSERT OR IGNORE INTO envelopes
                   (id,source_record_id,extraction_version,review_status,envelope_json,created_at)
                   VALUES (?,?,?,?,?,?)""",
                (
                    envelope.envelope_id,
                    envelope.source_record_id,
                    envelope.extraction_version,
                    envelope.review_status,
                    envelope.model_dump_json(),
                    envelope.created_at.isoformat(),
                ),
            )

    def get_envelope(self, envelope_id: str) -> IngestionEnvelope | None:
        row = self._conn.execute("SELECT envelope_json FROM envelopes WHERE id=?", (envelope_id,)).fetchone()
        return IngestionEnvelope.model_validate_json(row[0]) if row else None

    def get_envelope_for_source(
        self, source_record_id: str, extraction_version: str
    ) -> IngestionEnvelope | None:
        row = self._conn.execute(
            """SELECT envelope_json FROM envelopes
               WHERE source_record_id=? AND extraction_version=?""",
            (source_record_id, extraction_version),
        ).fetchone()
        return IngestionEnvelope.model_validate_json(row[0]) if row else None

    def queue_review(self, envelope_id: str, reasons: list[str]) -> str:
        review_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"ingestion-review:{envelope_id}"))
        with self._conn:
            self._conn.execute(
                """INSERT OR IGNORE INTO review_queue
                   (id,envelope_id,reason_json,status,created_at)
                   VALUES (?,?,?,'pending',?)""",
                (review_id, envelope_id, json.dumps(reasons), _utc_iso()),
            )
        return review_id

    def resolve_review(
        self, envelope_id: str, *, approved: bool, resolver: str, note: str = ""
    ) -> IngestionEnvelope:
        envelope = self.get_envelope(envelope_id)
        if envelope is None:
            raise KeyError(f"Envelope not found: {envelope_id}")
        new_status: Literal["approved", "rejected"] = "approved" if approved else "rejected"
        envelope.review_status = new_status
        for concept in envelope.semantic.concepts:
            concept.status = "approved" if approved else "rejected"
        for relation in envelope.semantic.relations:
            relation.status = "approved" if approved else "rejected"
        for claim in envelope.semantic.claims:
            claim.status = "current" if approved else "disputed"
        with self._conn:
            cur = self._conn.execute(
                """UPDATE review_queue SET status=?,resolved_at=?,resolver=?,resolution_note=?
                   WHERE envelope_id=? AND status='pending'""",
                (new_status, _utc_iso(), resolver, note, envelope_id),
            )
            if cur.rowcount == 0:
                existing = self._conn.execute(
                    "SELECT status FROM review_queue WHERE envelope_id=?", (envelope_id,)
                ).fetchone()
                if existing is None or existing[0] != new_status:
                    raise ValueError("Review is missing or was already resolved differently")
            self._conn.execute(
                "UPDATE envelopes SET review_status=?,envelope_json=? WHERE id=?",
                (new_status, envelope.model_dump_json(), envelope_id),
            )
        return envelope

    def pending_reviews(self) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """SELECT r.id,r.envelope_id,r.reason_json,r.created_at,
                      e.source_record_id,e.envelope_json
               FROM review_queue r
               JOIN envelopes e ON e.id=r.envelope_id
               WHERE r.status='pending'
               ORDER BY r.created_at"""
        ).fetchall()
        return [
            {
                "review_id": row["id"],
                "envelope_id": row["envelope_id"],
                "source_record_id": row["source_record_id"],
                "reasons": json.loads(row["reason_json"]),
                "created_at": row["created_at"],
                "envelope": json.loads(row["envelope_json"]),
            }
            for row in rows
        ]

    def dispatch_status(self, envelope_id: str, target: str, version: str) -> sqlite3.Row | None:
        return cast(
            sqlite3.Row | None,
            self._conn.execute(
                "SELECT * FROM dispatches WHERE envelope_id=? AND target=? AND extraction_version=?",
                (envelope_id, target, version),
            ).fetchone(),
        )

    def record_dispatch(
        self,
        *,
        envelope_id: str,
        target: str,
        extraction_version: str,
        status: str,
        artifact_ref: str | None = None,
        error: str | None = None,
    ) -> None:
        with self._conn:
            self._conn.execute(
                """INSERT INTO dispatches
                   (envelope_id,target,extraction_version,status,attempts,
                    artifact_ref,error,attempted_at)
                   VALUES (?,?,?,?,1,?,?,?)
                   ON CONFLICT(envelope_id,target,extraction_version) DO UPDATE SET
                     status=excluded.status,
                     attempts=dispatches.attempts+1,
                     artifact_ref=excluded.artifact_ref,
                     error=excluded.error,
                     attempted_at=excluded.attempted_at""",
                (
                    envelope_id,
                    target,
                    extraction_version,
                    status,
                    artifact_ref,
                    error,
                    _utc_iso(),
                ),
            )

    def pending_approved_envelopes(self) -> list[IngestionEnvelope]:
        rows = self._conn.execute(
            "SELECT envelope_json FROM envelopes WHERE review_status IN ('not_required','approved')"
        ).fetchall()
        return [IngestionEnvelope.model_validate_json(row[0]) for row in rows]

    def quarantine(self, request: dict[str, Any], error: str) -> str:
        quarantine_id = str(uuid.uuid4())
        with self._conn:
            self._conn.execute(
                "INSERT INTO quarantine VALUES (?,?,?,?)",
                (quarantine_id, json.dumps(request, sort_keys=True, default=str), error, _utc_iso()),
            )
        return quarantine_id

    def map_legacy_reference(self, legacy_source_id: str, source_record_id: str) -> None:
        with self._conn:
            self._conn.execute(
                """INSERT INTO legacy_references VALUES (?,?,?)
                   ON CONFLICT(legacy_source_id) DO UPDATE SET source_record_id=excluded.source_record_id""",
                (legacy_source_id, source_record_id, _utc_iso()),
            )

    def resolve_legacy_reference(self, legacy_source_id: str) -> str | None:
        row = self._conn.execute(
            "SELECT source_record_id FROM legacy_references WHERE legacy_source_id=?",
            (legacy_source_id,),
        ).fetchone()
        return str(row[0]) if row else None

    def rows(self, table: str) -> Iterable[sqlite3.Row]:
        allowed = {
            "source_records",
            "captures",
            "envelopes",
            "review_queue",
            "dispatches",
            "quarantine",
            "legacy_references",
        }
        if table not in allowed:
            raise ValueError(f"Unknown table: {table}")
        return self._conn.execute(f"SELECT * FROM {table}").fetchall()
