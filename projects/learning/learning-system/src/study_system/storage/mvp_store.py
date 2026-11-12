"""MVP SQLite store with the four tables approved by the resolved plan."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any, cast

from study_system.types.card import FSRSState
from study_system.types.mvp import GeneratedCard


SCHEMA_SQL = """
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

"""


class MVPStore:
    def __init__(self, db_path: Path) -> None:
        self.path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(SCHEMA_SQL)
        self._migrate_unapproved_auxiliary_tables()
        self._conn.commit()

    def _migrate_unapproved_auxiliary_tables(self) -> None:
        """Fold prototype auxiliary data into ``generation_runs`` and remove it.

        The reviewed architecture permits exactly four tables. Earlier prototype
        builds briefly created ``idempotency_keys`` and ``practice_attempts``.
        Completed practice evidence is preserved as an audit row; retry entries
        are preserved as internal audit rows before the old tables are dropped.
        """
        tables = self.table_names()
        if "idempotency_keys" in tables:
            rows = self._conn.execute(
                "SELECT key, tool, result_json, created_at FROM idempotency_keys"
            ).fetchall()
            for row in rows:
                self._write_audit_row(
                    row_id=self._idempotency_row_id(str(row["key"])),
                    operation=f"idempotency:{row['tool']}",
                    selection_code="idempotency",
                    details_json=str(row["result_json"]),
                    concept_ids=[],
                    started_at=str(row["created_at"]),
                )
            self._conn.execute("DROP TABLE idempotency_keys")
        if "practice_attempts" in tables:
            columns = {
                str(row["name"])
                for row in self._conn.execute("PRAGMA table_info(practice_attempts)").fetchall()
            }
            if "evaluation_json" in columns:
                rows = self._conn.execute(
                    "SELECT * FROM practice_attempts WHERE evaluation_json IS NOT NULL"
                ).fetchall()
                for row in rows:
                    details = {
                        "student_input": row["student_input"],
                        "grading_prompt": row["grading_prompt"],
                        "evaluation": json.loads(row["evaluation_json"]),
                        "source_refs": (
                            json.loads(row["source_refs_json"])
                            if "source_refs_json" in columns else []
                        ),
                        "model": row["model"] if "model" in columns else None,
                        "prompt_version": (
                            row["prompt_version"] if "prompt_version" in columns else None
                        ),
                    }
                    self._write_audit_row(
                        row_id=str(row["id"]),
                        operation=f"{row['mode']}_evaluation",
                        selection_code="practice_evidence",
                        details_json=json.dumps(details, sort_keys=True, default=str),
                        concept_ids=[str(row["concept_id"])],
                        started_at=str(row["created_at"]),
                        completed_at=str(row["evaluated_at"] or row["created_at"]),
                    )
            self._conn.execute("DROP TABLE practice_attempts")

    @property
    def connection(self) -> sqlite3.Connection:
        return self._conn

    def table_names(self) -> set[str]:
        cur = self._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
        return {str(row[0]) for row in cur.fetchall()}

    # ------------------------------------------------------------------
    # Cards / review state
    # ------------------------------------------------------------------

    def insert_cards(self, cards: list[GeneratedCard]) -> int:
        inserted = 0
        with self._conn:
            for card in cards:
                cur = self._conn.execute(
                    """
                    INSERT OR IGNORE INTO cards
                        (id, concept_id, card_type, front, back, source_refs_json,
                         source_version, created_at, model, prompt_version)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        card.id,
                        card.concept_id,
                        card.card_type,
                        card.front,
                        card.back,
                        json.dumps(card.source_refs, sort_keys=True),
                        card.source_version,
                        card.created_at.isoformat(),
                        card.model,
                        card.prompt_version,
                    ),
                )
                if cur.rowcount:
                    inserted += 1
                    self._conn.execute(
                        "INSERT OR IGNORE INTO review_state (card_id) VALUES (?)",
                        (card.id,),
                    )
        return inserted

    def concept_ids_with_cards(self) -> set[str]:
        cur = self._conn.execute(
            "SELECT DISTINCT concept_id FROM cards WHERE deleted_at IS NULL"
        )
        return {str(row[0]) for row in cur.fetchall()}

    def get_due_cards(
        self,
        limit: int = 50,
        now: datetime | None = None,
        card_types: tuple[str, ...] | None = ("flashcard",),
    ) -> list[sqlite3.Row]:
        now_iso = (now or datetime.utcnow()).isoformat()
        query = """
            SELECT c.*, rs.stability, rs.difficulty, rs.elapsed_days,
                   rs.scheduled_days, rs.reps, rs.lapses, rs.state,
                   rs.due_at, rs.last_reviewed_at, rs.evidence_json
            FROM cards c
            JOIN review_state rs ON rs.card_id = c.id
            WHERE c.deleted_at IS NULL
              AND (rs.due_at IS NULL OR rs.due_at <= ?)
        """
        params: list[Any] = [now_iso]
        if card_types is not None:
            placeholders = ",".join("?" for _ in card_types)
            query += f" AND c.card_type IN ({placeholders})"
            params.extend(card_types)
        query += " ORDER BY COALESCE(rs.due_at, '0001-01-01'), c.created_at LIMIT ?"
        params.append(limit)
        cur = self._conn.execute(query, params)
        return cur.fetchall()

    def get_card_with_state(self, card_id: str) -> sqlite3.Row | None:
        cur = self._conn.execute(
            """
            SELECT c.*, rs.stability, rs.difficulty, rs.elapsed_days,
                   rs.scheduled_days, rs.reps, rs.lapses, rs.state,
                   rs.due_at, rs.last_reviewed_at, rs.evidence_json
            FROM cards c
            JOIN review_state rs ON rs.card_id = c.id
            WHERE c.id = ? AND c.deleted_at IS NULL
            """,
            (card_id,),
        )
        return cast(sqlite3.Row | None, cur.fetchone())

    def _write_review_state(
        self,
        card_id: str,
        fsrs: FSRSState,
        *,
        reviewed_at: datetime | None = None,
        evidence: dict[str, Any] | None = None,
    ) -> None:
        """Apply a review-state update without committing (see callers)."""
        existing = self.get_card_with_state(card_id)
        if existing is None:
            raise KeyError(f"Card not found: {card_id}")
        merged_evidence: dict[str, Any] = json.loads(existing["evidence_json"] or "{}")
        if evidence:
            merged_evidence.update(evidence)
        self._conn.execute(
            """
            UPDATE review_state
            SET stability=?, difficulty=?, elapsed_days=?, scheduled_days=?,
                reps=?, lapses=?, state=?, due_at=?, last_reviewed_at=?,
                evidence_json=?
            WHERE card_id=?
            """,
            (
                fsrs.stability,
                fsrs.difficulty,
                fsrs.elapsed_days,
                fsrs.scheduled_days,
                fsrs.reps,
                fsrs.lapses,
                fsrs.state,
                fsrs.next_due_at.isoformat() if fsrs.next_due_at else None,
                (reviewed_at or datetime.utcnow()).isoformat(),
                json.dumps(merged_evidence, sort_keys=True),
                card_id,
            ),
        )

    def update_review_state(
        self,
        card_id: str,
        fsrs: FSRSState,
        *,
        reviewed_at: datetime | None = None,
        evidence: dict[str, Any] | None = None,
    ) -> None:
        self._write_review_state(card_id, fsrs, reviewed_at=reviewed_at, evidence=evidence)
        self._conn.commit()

    def apply_review_and_record(
        self,
        card_id: str,
        fsrs: FSRSState,
        *,
        reviewed_at: datetime | None = None,
        evidence: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
        idempotent_result: dict[str, Any] | None = None,
    ) -> None:
        """Apply a review-state update and record its idempotency result in one commit.

        Prevents the crash-between-writes window where a rating is applied
        but the idempotency key never gets recorded, which would let a retry
        double-apply the same rating (plan 02 §10).
        """
        self._write_review_state(card_id, fsrs, reviewed_at=reviewed_at, evidence=evidence)
        if idempotency_key:
            self._write_idempotent_result(idempotency_key, "submit_card_rating", idempotent_result or {})
        self._conn.commit()

    def record_learning_evidence(self, card_id: str, key: str, value: Any) -> None:
        row = self.get_card_with_state(card_id)
        if row is None:
            raise KeyError(f"Card not found: {card_id}")
        evidence = json.loads(row["evidence_json"] or "{}")
        evidence[key] = value
        self._conn.execute(
            "UPDATE review_state SET evidence_json=? WHERE card_id=?",
            (json.dumps(evidence, sort_keys=True), card_id),
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Generation audit
    # ------------------------------------------------------------------

    def start_generation_run(
        self,
        *,
        effective_config_json: str,
        selected_concept_ids: list[str],
        operation: str = "generate_unseen_cards",
        selection_code: str = "unseen_coverage",
    ) -> str:
        run_id = str(uuid.uuid4())
        self._conn.execute(
            """
            INSERT INTO generation_runs
                (id, started_at, operation, selection_code, effective_config_json,
                 selected_concept_ids_json, outcome)
            VALUES (?, ?, ?, ?, ?, ?, 'started')
            """,
            (
                run_id,
                datetime.utcnow().isoformat(),
                operation,
                selection_code,
                effective_config_json,
                json.dumps(selected_concept_ids),
            ),
        )
        self._conn.commit()
        return run_id

    def _write_audit_row(
        self,
        *,
        row_id: str,
        operation: str,
        selection_code: str,
        details_json: str,
        concept_ids: list[str],
        started_at: str | None = None,
        completed_at: str | None = None,
        outcome: str = "success",
        error: str | None = None,
    ) -> None:
        timestamp = started_at or datetime.utcnow().isoformat()
        self._conn.execute(
            """
            INSERT OR IGNORE INTO generation_runs
                (id, started_at, completed_at, operation, selection_code,
                 effective_config_json, selected_concept_ids_json, outcome, error)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row_id,
                timestamp,
                completed_at or timestamp,
                operation,
                selection_code,
                details_json,
                json.dumps(concept_ids),
                outcome,
                error,
            ),
        )

    def record_practice_outcome(
        self,
        *,
        mode: str,
        concept_id: str,
        student_input: str,
        grading_prompt: str,
        evaluation: dict[str, Any],
        source_refs: list[dict[str, Any]],
        model: str,
        prompt_version: str,
        outcome_id: str | None = None,
    ) -> str:
        """Persist only a completed stateless practice outcome as an audit row."""
        if mode not in {"feynman", "challenger"}:
            raise ValueError("mode must be feynman or challenger")
        outcome_id = outcome_id or str(uuid.uuid4())
        details = {
            "student_input": student_input,
            "grading_prompt": grading_prompt,
            "evaluation": evaluation,
            "source_refs": source_refs,
            "model": model,
            "prompt_version": prompt_version,
        }
        self._write_audit_row(
            row_id=outcome_id,
            operation=f"{mode}_evaluation",
            selection_code="practice_evidence",
            details_json=json.dumps(details, sort_keys=True, default=str),
            concept_ids=[concept_id],
        )
        self._conn.commit()
        return outcome_id

    def finish_generation_run(self, run_id: str, outcome: str, error: str | None = None) -> None:
        self._conn.execute(
            """
            UPDATE generation_runs
            SET completed_at=?, outcome=?, error=?
            WHERE id=?
            """,
            (datetime.utcnow().isoformat(), outcome, error, run_id),
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Overrides
    # ------------------------------------------------------------------

    def create_override(
        self,
        *,
        setting: str,
        value: Any,
        starts_on: date,
        expires_on: date,
        reason: str,
        created_by: str,
        override_id: str | None = None,
    ) -> str:
        if expires_on < starts_on:
            raise ValueError("expires_on must be on or after starts_on")
        override_id = override_id or str(uuid.uuid4())
        existing = self._conn.execute(
            "SELECT setting, value_json FROM overrides WHERE id = ?", (override_id,)
        ).fetchone()
        if existing is not None:
            if existing["setting"] != setting or json.loads(existing["value_json"]) != value:
                raise ValueError(f"Override id {override_id} already belongs to another request")
            return override_id
        self._conn.execute(
            """
            INSERT OR IGNORE INTO overrides
                (id, setting, value_json, starts_on, expires_on, reason,
                 created_by, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                override_id,
                setting,
                json.dumps(value),
                starts_on.isoformat(),
                expires_on.isoformat(),
                reason,
                created_by,
                datetime.utcnow().isoformat(),
            ),
        )
        self._conn.commit()
        return override_id

    def cancel_override(self, override_id: str) -> bool:
        cur = self._conn.execute(
            "UPDATE overrides SET cancelled_at=? WHERE id=? AND cancelled_at IS NULL",
            (datetime.utcnow().isoformat(), override_id),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def active_overrides(self, on_date: date | None = None) -> dict[str, Any]:
        today = (on_date or date.today()).isoformat()
        cur = self._conn.execute(
            """
            SELECT setting, value_json
            FROM overrides
            WHERE cancelled_at IS NULL
              AND starts_on <= ?
              AND expires_on >= ?
            ORDER BY created_at
            """,
            (today, today),
        )
        active: dict[str, Any] = {}
        for row in cur.fetchall():
            active[str(row["setting"])] = json.loads(row["value_json"])
        return active

    def active_override_records(self, on_date: date | None = None) -> list[dict[str, Any]]:
        today = (on_date or date.today()).isoformat()
        rows = self._conn.execute(
            """
            SELECT id, setting, value_json, starts_on, expires_on, reason,
                   created_by, created_at
            FROM overrides
            WHERE cancelled_at IS NULL AND starts_on <= ? AND expires_on >= ?
            ORDER BY created_at
            """,
            (today, today),
        ).fetchall()
        return [
            {
                **{key: row[key] for key in row.keys() if key != "value_json"},
                "value": json.loads(row["value_json"]),
            }
            for row in rows
        ]

    # ------------------------------------------------------------------
    # Progress
    # ------------------------------------------------------------------

    def progress_counts(self) -> dict[str, int]:
        cards = self._conn.execute(
            "SELECT COUNT(*) FROM cards WHERE deleted_at IS NULL"
        ).fetchone()[0]
        concepts = self._conn.execute(
            "SELECT COUNT(DISTINCT concept_id) FROM cards WHERE deleted_at IS NULL"
        ).fetchone()[0]
        due = self._conn.execute(
            """
            SELECT COUNT(*)
            FROM cards c JOIN review_state rs ON rs.card_id = c.id
            WHERE c.deleted_at IS NULL
              AND (rs.due_at IS NULL OR rs.due_at <= ?)
            """,
            (datetime.utcnow().isoformat(),),
        ).fetchone()[0]
        runs = self._conn.execute(
            "SELECT COUNT(*) FROM generation_runs WHERE operation = 'generate_unseen_cards'"
        ).fetchone()[0]
        return {
            "cards": int(cards),
            "concepts_with_cards": int(concepts),
            "due_cards": int(due),
            "generation_runs": int(runs),
        }

    def recent_activity(self, limit: int = 20) -> list[dict[str, Any]]:
        """Return a compact cross-workflow activity feed for chat/status views.

        This is intentionally read-only and derived from the existing audit
        tables. It does not introduce a second event log or duplicate state.
        """
        if limit < 1 or limit > 200:
            raise ValueError("recent activity limit must be between 1 and 200")
        rows = self._conn.execute(
            """
            SELECT occurred_at, activity_type, entity_id, detail_json
            FROM (
                SELECT started_at AS occurred_at,
                       CASE
                           WHEN operation = 'feynman_evaluation' THEN 'feynman_evaluated'
                           WHEN operation = 'challenger_evaluation' THEN 'challenger_evaluated'
                           ELSE 'generation_run'
                       END AS activity_type,
                       id AS entity_id,
                       json_object(
                           'outcome', outcome,
                           'operation', operation,
                           'selected_concept_ids', json(selected_concept_ids_json)
                       ) AS detail_json
                FROM generation_runs
                WHERE operation NOT LIKE 'idempotency:%'

                UNION ALL

                SELECT last_reviewed_at AS occurred_at,
                       'card_review' AS activity_type,
                       card_id AS entity_id,
                       json_object(
                           'state', state,
                           'scheduled_days', scheduled_days,
                           'evidence', json(evidence_json)
                       ) AS detail_json
                FROM review_state
                WHERE last_reviewed_at IS NOT NULL
            )
            ORDER BY occurred_at DESC, activity_type, entity_id
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [
            {
                "occurred_at": str(row["occurred_at"]),
                "type": str(row["activity_type"]),
                "entity_id": str(row["entity_id"]),
                "details": json.loads(row["detail_json"] or "{}"),
            }
            for row in rows
        ]

    # ------------------------------------------------------------------
    # Idempotency (plan 02 §10: "Each write tool accepts or creates an
    # idempotency key"). Retry results use internal generation_runs audit rows
    # so the approved four-table contract remains exact.
    # ------------------------------------------------------------------

    @staticmethod
    def _idempotency_row_id(key: str) -> str:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"study-idempotency:{key}"))

    def get_idempotent_result(self, key: str, tool: str | None = None) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT operation, effective_config_json FROM generation_runs WHERE id = ?",
            (self._idempotency_row_id(key),),
        ).fetchone()
        stored_tool = str(row["operation"]).removeprefix("idempotency:") if row else None
        if row and tool is not None and stored_tool != tool:
            raise ValueError(
                f"Idempotency key {key!r} was already used for {stored_tool!r}, not {tool!r}"
            )
        return json.loads(row["effective_config_json"]) if row else None

    def _write_idempotent_result(self, key: str, tool: str, result: dict[str, Any]) -> None:
        """Record an idempotency result without committing (see callers)."""
        self._write_audit_row(
            row_id=self._idempotency_row_id(key),
            operation=f"idempotency:{tool}",
            selection_code="idempotency",
            details_json=json.dumps(result, sort_keys=True, default=str),
            concept_ids=[],
        )

    def save_idempotent_result(self, key: str, tool: str, result: dict[str, Any]) -> None:
        self._write_idempotent_result(key, tool, result)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()
