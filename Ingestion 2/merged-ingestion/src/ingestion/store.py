from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Literal, cast

from ingestion.models import (
    ClaimProposal,
    ConceptProposal,
    IngestionEnvelope,
    ProposalReviewDecision,
    RelationProposal,
)


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
    boundary_origin TEXT NOT NULL DEFAULT 'document_segment',
    user_selection_json TEXT,
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

-- One row per document that has cleared the parse step, whatever it produced
-- (including nothing). "Has this document been parsed?" is this table, not a
-- count of highlights: a document with no parseable content must not be
-- re-parsed on every run.
CREATE TABLE IF NOT EXISTS parses (
    source_record_id TEXT PRIMARY KEY,
    parser_version TEXT NOT NULL,
    normalized_content_hash TEXT NOT NULL,
    highlight_count INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(source_record_id) REFERENCES source_records(id)
);

-- The parse step's output, stored because it cannot be recomputed: the
-- segmenter is model-backed, so re-splitting the same document may draw
-- different boundaries. Highlight ids are derived from (source_record_id,
-- highlight_index), so these rows are what keeps KG/content/vector aligned.
CREATE TABLE IF NOT EXISTS highlights (
    source_record_id TEXT NOT NULL,
    highlight_index INTEGER NOT NULL,
    text TEXT NOT NULL,
    context_text TEXT,
    heading TEXT,
    start_char INTEGER NOT NULL,
    end_char INTEGER NOT NULL,
    start_word INTEGER NOT NULL,
    end_word INTEGER NOT NULL,
    segmentation_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY(source_record_id, highlight_index),
    FOREIGN KEY(source_record_id) REFERENCES source_records(id)
);

-- Failed segmentation never creates a parse/highlight row. Attempts remain
-- visible and retriable here until a later run successfully parses the source.
CREATE TABLE IF NOT EXISTS parse_failures (
    id TEXT PRIMARY KEY,
    source_record_id TEXT NOT NULL,
    failure_type TEXT NOT NULL,
    error TEXT NOT NULL,
    attempts_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    resolved_at TEXT,
    FOREIGN KEY(source_record_id) REFERENCES source_records(id)
);
CREATE INDEX IF NOT EXISTS idx_parse_failures_source
ON parse_failures(source_record_id, created_at);

CREATE TABLE IF NOT EXISTS envelopes (
    id TEXT PRIMARY KEY,
    source_record_id TEXT NOT NULL,
    highlight_index INTEGER NOT NULL,
    extraction_version TEXT NOT NULL,
    review_status TEXT NOT NULL,
    envelope_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(source_record_id) REFERENCES source_records(id),
    UNIQUE(source_record_id, highlight_index, extraction_version)
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

CREATE TABLE IF NOT EXISTS review_items (
    id TEXT PRIMARY KEY,
    review_id TEXT NOT NULL,
    envelope_id TEXT NOT NULL,
    proposal_id TEXT NOT NULL,
    proposal_type TEXT NOT NULL,
    original_proposal_json TEXT NOT NULL,
    reason_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    decision TEXT,
    final_proposal_json TEXT,
    resolved_at TEXT,
    resolver TEXT,
    resolution_note TEXT,
    FOREIGN KEY(review_id) REFERENCES review_queue(id),
    FOREIGN KEY(envelope_id) REFERENCES envelopes(id),
    UNIQUE(envelope_id, proposal_id)
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
        self._ensure_schema_compatibility()
        self._conn.commit()

    def _ensure_schema_compatibility(self) -> None:
        """Apply additive columns needed by pre-existing local ledgers."""
        columns = {
            str(row["name"])
            for row in self._conn.execute("PRAGMA table_info(source_records)")
        }
        if "boundary_origin" not in columns:
            self._conn.execute(
                "ALTER TABLE source_records ADD COLUMN boundary_origin "
                "TEXT NOT NULL DEFAULT 'document_segment'"
            )
        if "user_selection_json" not in columns:
            self._conn.execute(
                "ALTER TABLE source_records ADD COLUMN user_selection_json TEXT"
            )

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
        boundary_origin: str,
        user_selection: dict[str, Any] | None,
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
                    access_policy_json,boundary_origin,user_selection_json,created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
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
                    boundary_origin,
                    (
                        json.dumps(user_selection, sort_keys=True, default=str)
                        if user_selection is not None
                        else None
                    ),
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

    def sources_pending_parse(self, limit: int = 100) -> list[sqlite3.Row]:
        """Canonical documents that have never cleared the parse step."""
        return self._conn.execute(
            """SELECT s.* FROM source_records s
               WHERE s.id=s.canonical_record_id
                 AND NOT EXISTS (SELECT 1 FROM parses p WHERE p.source_record_id=s.id)
               ORDER BY s.captured_at, s.id LIMIT ?""",
            (limit,),
        ).fetchall()

    def save_parse(
        self,
        *,
        source_record_id: str,
        parser_version: str,
        normalized_content_hash: str,
        highlights: list[dict[str, Any]],
    ) -> None:
        """Record one document's parse and its highlights in one transaction.

        Atomic on purpose: a half-written parse would leave highlight indices
        with gaps, and every downstream id is derived from those indices.
        """
        now = _utc_iso()
        with self._conn:
            self._conn.execute(
                """INSERT OR IGNORE INTO parses
                   (source_record_id,parser_version,normalized_content_hash,
                    highlight_count,created_at)
                   VALUES (?,?,?,?,?)""",
                (
                    source_record_id,
                    parser_version,
                    normalized_content_hash,
                    len(highlights),
                    now,
                ),
            )
            for highlight in highlights:
                self._conn.execute(
                    """INSERT OR IGNORE INTO highlights
                       (source_record_id,highlight_index,text,context_text,heading,
                        start_char,end_char,start_word,end_word,segmentation_json,
                        created_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        source_record_id,
                        highlight["index"],
                        highlight["text"],
                        highlight["context_text"],
                        highlight["heading"],
                        highlight["start_char"],
                        highlight["end_char"],
                        highlight["start_word"],
                        highlight["end_word"],
                        json.dumps(highlight["segmentation"], sort_keys=True, default=str),
                        now,
                    ),
                )
            self._conn.execute(
                """UPDATE parse_failures SET resolved_at=?
                   WHERE source_record_id=? AND resolved_at IS NULL""",
                (now, source_record_id),
            )

    def record_parse_failure(
        self,
        *,
        source_record_id: str,
        failure_type: str,
        error: str,
        attempts: list[dict[str, Any]],
    ) -> str:
        failure_id = str(uuid.uuid4())
        with self._conn:
            self._conn.execute(
                """INSERT INTO parse_failures
                   (id,source_record_id,failure_type,error,attempts_json,created_at)
                   VALUES (?,?,?,?,?,?)""",
                (
                    failure_id,
                    source_record_id,
                    failure_type,
                    error,
                    json.dumps(attempts, sort_keys=True, default=str),
                    _utc_iso(),
                ),
            )
        return failure_id

    def parse_failures(self, source_record_id: str) -> list[sqlite3.Row]:
        return self._conn.execute(
            """SELECT * FROM parse_failures WHERE source_record_id=?
               ORDER BY created_at,id""",
            (source_record_id,),
        ).fetchall()

    def highlight_count(self, source_record_id: str) -> int | None:
        """How many highlights a document was parsed into; None if never parsed."""
        row = self._conn.execute(
            "SELECT highlight_count FROM parses WHERE source_record_id=?",
            (source_record_id,),
        ).fetchone()
        return int(row[0]) if row is not None else None

    def get_highlights(self, source_record_id: str) -> list[sqlite3.Row]:
        return self._conn.execute(
            """SELECT * FROM highlights WHERE source_record_id=?
               ORDER BY highlight_index""",
            (source_record_id,),
        ).fetchall()

    def highlights_pending_extraction(
        self,
        extraction_version: str,
        *,
        source_record_id: str | None = None,
        limit: int = 1000,
    ) -> list[sqlite3.Row]:
        """Parsed highlights that have no envelope yet at this extraction version.

        Joined onto their parent document, because building an envelope needs
        both. Ordered by document then position so a batch stays readable.
        Pass `source_record_id` to scope the backlog to one document.
        """
        return self._conn.execute(
            f"""SELECT h.*, s.raw_hash, s.normalized_hash,
                      s.canonical_record_id, s.source_type, s.origin,
                      s.normalized_origin, s.captured_at, s.observed_at,
                      s.raw_content_ref, s.version, s.supersedes_record_id,
                      s.source_status, s.metadata_json, s.extracted_metadata_json,
                      s.access_policy_json, s.boundary_origin,
                      s.user_selection_json
               FROM highlights h
               JOIN source_records s ON s.id=h.source_record_id
               WHERE {'h.source_record_id=? AND' if source_record_id else ''}
                     NOT EXISTS (
                     SELECT 1 FROM envelopes e
                     WHERE e.source_record_id=h.source_record_id
                       AND e.highlight_index=h.highlight_index
                       AND e.extraction_version=?
                 )
               ORDER BY s.captured_at, h.source_record_id, h.highlight_index
               LIMIT ?""",
            (
                (source_record_id, extraction_version, limit)
                if source_record_id
                else (extraction_version, limit)
            ),
        ).fetchall()

    def save_envelope(self, envelope: IngestionEnvelope) -> None:
        with self._conn:
            self._conn.execute(
                """INSERT OR IGNORE INTO envelopes
                   (id,source_record_id,highlight_index,extraction_version,
                    review_status,envelope_json,created_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (
                    envelope.envelope_id,
                    envelope.source_record_id,
                    envelope.highlight_index,
                    envelope.extraction_version,
                    envelope.review_status,
                    envelope.model_dump_json(),
                    envelope.created_at.isoformat(),
                ),
            )

    def get_envelope(self, envelope_id: str) -> IngestionEnvelope | None:
        row = self._conn.execute("SELECT envelope_json FROM envelopes WHERE id=?", (envelope_id,)).fetchone()
        return IngestionEnvelope.model_validate_json(row[0]) if row else None

    def get_envelopes_for_source(
        self, source_record_id: str, extraction_version: str
    ) -> list[IngestionEnvelope]:
        """Every highlight-envelope of one document, in document order."""
        rows = self._conn.execute(
            """SELECT envelope_json FROM envelopes
               WHERE source_record_id=? AND extraction_version=?
               ORDER BY highlight_index""",
            (source_record_id, extraction_version),
        ).fetchall()
        return [IngestionEnvelope.model_validate_json(row[0]) for row in rows]

    def queue_review(self, envelope: IngestionEnvelope) -> str:
        envelope_id = envelope.envelope_id
        reasons = sorted({signal.code for signal in envelope.review_signals})
        review_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"ingestion-review:{envelope_id}"))
        with self._conn:
            self._conn.execute(
                """INSERT OR IGNORE INTO review_queue
                   (id,envelope_id,reason_json,status,created_at)
                   VALUES (?,?,?,'pending',?)""",
                (review_id, envelope_id, json.dumps(reasons), _utc_iso()),
            )
            proposals = [
                *(("concept", proposal) for proposal in envelope.semantic.concepts),
                *(("claim", proposal) for proposal in envelope.semantic.claims),
                *(("relation", proposal) for proposal in envelope.semantic.relations),
            ]
            for proposal_type, proposal in proposals:
                item_id = str(
                    uuid.uuid5(
                        uuid.NAMESPACE_URL,
                        f"ingestion-review-item:{envelope_id}:{proposal.proposal_id}",
                    )
                )
                item_reasons = sorted(
                    {
                        signal.code
                        for signal in envelope.review_signals
                        if signal.proposal_id == proposal.proposal_id
                    }
                )
                self._conn.execute(
                    """INSERT OR IGNORE INTO review_items
                       (id,review_id,envelope_id,proposal_id,proposal_type,
                        original_proposal_json,reason_json,status)
                       VALUES (?,?,?,?,?,?,?,'pending')""",
                    (
                        item_id,
                        review_id,
                        envelope_id,
                        proposal.proposal_id,
                        proposal_type,
                        proposal.model_dump_json(),
                        json.dumps(item_reasons),
                    ),
                )
        return review_id

    @staticmethod
    def _proposal_locations(
        envelope: IngestionEnvelope,
    ) -> dict[str, tuple[str, int, ConceptProposal | ClaimProposal | RelationProposal]]:
        locations: dict[
            str, tuple[str, int, ConceptProposal | ClaimProposal | RelationProposal]
        ] = {}
        for proposal_type, proposals in (
            ("concept", envelope.semantic.concepts),
            ("claim", envelope.semantic.claims),
            ("relation", envelope.semantic.relations),
        ):
            for index, proposal in enumerate(proposals):
                if proposal.proposal_id in locations:
                    raise ValueError(f"Duplicate proposal id: {proposal.proposal_id}")
                locations[proposal.proposal_id] = (proposal_type, index, proposal)
        return locations

    @staticmethod
    def _apply_proposal_decision(
        envelope: IngestionEnvelope,
        *,
        proposal_type: str,
        index: int,
        original: ConceptProposal | ClaimProposal | RelationProposal,
        decision: ProposalReviewDecision,
    ) -> ConceptProposal | ClaimProposal | RelationProposal:
        proposal: ConceptProposal | ClaimProposal | RelationProposal = original
        if decision.action == "edit":
            model = {
                "concept": ConceptProposal,
                "claim": ClaimProposal,
                "relation": RelationProposal,
            }[proposal_type]
            proposal = model.model_validate(decision.edited_proposal)
            if proposal.proposal_id != original.proposal_id:
                raise ValueError("An edited proposal cannot change proposal_id")
            if proposal.source_record_id != original.source_record_id:
                raise ValueError("An edited proposal cannot change source_record_id")

        approved = decision.action in {"approve", "edit"}
        if proposal_type == "concept":
            assert isinstance(proposal, ConceptProposal)
            proposal.status = "approved" if approved else "rejected"
            envelope.semantic.concepts[index] = proposal
        elif proposal_type == "claim":
            assert isinstance(proposal, ClaimProposal)
            proposal.status = "current" if approved else "disputed"
            envelope.semantic.claims[index] = proposal
        else:
            assert isinstance(proposal, RelationProposal)
            proposal.status = "approved" if approved else "rejected"
            envelope.semantic.relations[index] = proposal
        return proposal

    def resolve_proposal_reviews(
        self,
        envelope_id: str,
        *,
        decisions: list[ProposalReviewDecision],
        resolver: str,
        note: str = "",
    ) -> IngestionEnvelope:
        if not decisions:
            raise ValueError("At least one proposal decision is required")
        decision_ids = [decision.proposal_id for decision in decisions]
        if len(decision_ids) != len(set(decision_ids)):
            raise ValueError("A proposal may be decided only once per request")

        envelope = self.get_envelope(envelope_id)
        if envelope is None:
            raise KeyError(f"Envelope not found: {envelope_id}")
        locations = self._proposal_locations(envelope)
        item_rows = {
            str(row["proposal_id"]): row
            for row in self._conn.execute(
                "SELECT * FROM review_items WHERE envelope_id=?", (envelope_id,)
            ).fetchall()
        }
        now = _utc_iso()
        resolved: list[
            tuple[ProposalReviewDecision, ConceptProposal | ClaimProposal | RelationProposal]
        ] = []
        for decision in decisions:
            if decision.proposal_id not in locations or decision.proposal_id not in item_rows:
                raise KeyError(f"Review proposal not found: {decision.proposal_id}")
            if item_rows[decision.proposal_id]["status"] != "pending":
                raise ValueError(f"Proposal review already resolved: {decision.proposal_id}")
            proposal_type, index, original = locations[decision.proposal_id]
            proposal = self._apply_proposal_decision(
                envelope,
                proposal_type=proposal_type,
                index=index,
                original=original,
                decision=decision,
            )
            resolved.append((decision, proposal))

        with self._conn:
            for decision, proposal in resolved:
                self._conn.execute(
                    """UPDATE review_items
                       SET status=?,decision=?,final_proposal_json=?,resolved_at=?,
                           resolver=?,resolution_note=?
                       WHERE envelope_id=? AND proposal_id=? AND status='pending'""",
                    (
                        "approved" if decision.action in {"approve", "edit"} else "rejected",
                        decision.action,
                        proposal.model_dump_json(),
                        now,
                        resolver,
                        decision.note or note,
                        envelope_id,
                        decision.proposal_id,
                    ),
                )
            pending_count = int(
                self._conn.execute(
                    """SELECT COUNT(*) FROM review_items
                       WHERE envelope_id=? AND status='pending'""",
                    (envelope_id,),
                ).fetchone()[0]
            )
            if pending_count == 0:
                approved_count = int(
                    self._conn.execute(
                        """SELECT COUNT(*) FROM review_items
                           WHERE envelope_id=? AND status='approved'""",
                        (envelope_id,),
                    ).fetchone()[0]
                )
                envelope.review_status = "approved" if approved_count else "rejected"
                self._conn.execute(
                    """UPDATE review_queue
                       SET status=?,resolved_at=?,resolver=?,resolution_note=?
                       WHERE envelope_id=?""",
                    (envelope.review_status, now, resolver, note, envelope_id),
                )
            else:
                envelope.review_status = "pending"
            self._conn.execute(
                "UPDATE envelopes SET review_status=?,envelope_json=? WHERE id=?",
                (envelope.review_status, envelope.model_dump_json(), envelope_id),
            )
        return envelope

    def resolve_review(
        self, envelope_id: str, *, approved: bool, resolver: str, note: str = ""
    ) -> IngestionEnvelope:
        envelope = self.get_envelope(envelope_id)
        if envelope is None:
            raise KeyError(f"Envelope not found: {envelope_id}")
        item_rows = self._conn.execute(
            "SELECT proposal_id,status FROM review_items WHERE envelope_id=?",
            (envelope_id,),
        ).fetchall()
        pending_item_ids = [
            str(row["proposal_id"]) for row in item_rows if row["status"] == "pending"
        ]
        if pending_item_ids:
            envelope = self.resolve_proposal_reviews(
                envelope_id,
                decisions=[
                    ProposalReviewDecision(
                        proposal_id=proposal_id,
                        action="approve" if approved else "reject",
                        note=note,
                    )
                    for proposal_id in pending_item_ids
                ],
                resolver=resolver,
                note=note,
            )
            return envelope
        if item_rows:
            expected = "approved" if approved else "rejected"
            if envelope.review_status != expected:
                raise ValueError("Review was already resolved differently")
            return envelope
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
        reviews = []
        for row in rows:
            items = self._conn.execute(
                """SELECT id,proposal_id,proposal_type,original_proposal_json,
                          reason_json,status,decision,final_proposal_json,
                          resolved_at,resolver,resolution_note
                   FROM review_items WHERE envelope_id=?
                   ORDER BY proposal_type,proposal_id""",
                (row["envelope_id"],),
            ).fetchall()
            reviews.append({
                "review_id": row["id"],
                "envelope_id": row["envelope_id"],
                "source_record_id": row["source_record_id"],
                "reasons": json.loads(row["reason_json"]),
                "created_at": row["created_at"],
                "envelope": json.loads(row["envelope_json"]),
                "items": [
                    {
                        **dict(item),
                        "original_proposal": json.loads(item["original_proposal_json"]),
                        "reasons": json.loads(item["reason_json"]),
                        "final_proposal": (
                            json.loads(item["final_proposal_json"])
                            if item["final_proposal_json"]
                            else None
                        ),
                    }
                    for item in items
                ],
            })
        return reviews

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

    def rows(self, table: str) -> Iterable[sqlite3.Row]:
        allowed = {
            "source_records",
            "captures",
            "parses",
            "highlights",
            "envelopes",
            "review_queue",
            "review_items",
            "dispatches",
            "quarantine",
        }
        if table not in allowed:
            raise ValueError(f"Unknown table: {table}")
        return self._conn.execute(f"SELECT * FROM {table}").fetchall()
