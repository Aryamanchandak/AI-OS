from __future__ import annotations

from pathlib import Path
import sqlite3

from steelman.models import (
    AnalysisRun, CalibrationSummary, DualAnalysis, ForensicAssessment,
    TrackerEntry, VerificationResult, stable_id,
)


SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS analyses (
    id TEXT PRIMARY KEY,
    claim_hash TEXT NOT NULL,
    canonical_claim TEXT NOT NULL,
    provider TEXT NOT NULL,
    created_at TEXT NOT NULL,
    payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_analyses_claim_hash ON analyses(claim_hash);
CREATE TABLE IF NOT EXISTS premise_nodes (
    analysis_id TEXT NOT NULL REFERENCES analyses(id) ON DELETE CASCADE,
    node_id TEXT NOT NULL,
    node_type TEXT NOT NULL,
    text TEXT NOT NULL,
    load_bearing INTEGER NOT NULL,
    strength TEXT NOT NULL,
    PRIMARY KEY (analysis_id, node_id)
);
CREATE TABLE IF NOT EXISTS premise_edges (
    analysis_id TEXT NOT NULL REFERENCES analyses(id) ON DELETE CASCADE,
    source_id TEXT NOT NULL,
    target_id TEXT NOT NULL,
    relation TEXT NOT NULL,
    PRIMARY KEY (analysis_id, source_id, target_id, relation)
);
CREATE TABLE IF NOT EXISTS sources (
    analysis_id TEXT NOT NULL REFERENCES analyses(id) ON DELETE CASCADE,
    source_id TEXT NOT NULL,
    title TEXT NOT NULL,
    tier TEXT NOT NULL,
    stance TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    PRIMARY KEY (analysis_id, source_id)
);
CREATE TABLE IF NOT EXISTS verifications (
    analysis_id TEXT NOT NULL REFERENCES analyses(id) ON DELETE CASCADE,
    node_id TEXT NOT NULL,
    grade TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    PRIMARY KEY (analysis_id, node_id)
);
CREATE TABLE IF NOT EXISTS forensic_assessments (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    company TEXT NOT NULL,
    flag_code TEXT NOT NULL,
    escalation_allowed INTEGER NOT NULL,
    payload_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS dual_analyses (
    id TEXT PRIMARY KEY, created_at TEXT NOT NULL, payload_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS verification_cache (
    node_hash TEXT PRIMARY KEY, payload_json TEXT NOT NULL, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS tracker_entries (
    prediction_id TEXT PRIMARY KEY, deadline TEXT NOT NULL, resolved INTEGER NOT NULL, payload_json TEXT NOT NULL
);
"""


class SQLiteStore:
    def __init__(self, path: str | Path = "steelman.db") -> None:
        self.path = str(path)
        self.initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(SCHEMA)

    def save_analysis(self, run: AnalysisRun) -> None:
        payload = run.model_dump_json()
        with self._connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO analyses VALUES (?, ?, ?, ?, ?, ?)",
                (
                    run.id,
                    run.claim_card.claim_hash,
                    run.claim_card.canonical_claim,
                    run.provider,
                    run.created_at.isoformat(),
                    payload,
                ),
            )
            for table in ("premise_nodes", "premise_edges", "sources", "verifications"):
                connection.execute(f"DELETE FROM {table} WHERE analysis_id = ?", (run.id,))
            connection.executemany(
                "INSERT INTO premise_nodes VALUES (?, ?, ?, ?, ?, ?)",
                [
                    (run.id, node.id, node.type.value, node.text, int(node.load_bearing), node.strength)
                    for node in run.graph.nodes
                ],
            )
            connection.executemany(
                "INSERT INTO premise_edges VALUES (?, ?, ?, ?)",
                [(run.id, edge.source_id, edge.target_id, edge.relation) for edge in run.graph.edges],
            )
            connection.executemany(
                "INSERT INTO sources VALUES (?, ?, ?, ?, ?, ?)",
                [
                    (run.id, source.id, source.title, source.tier.value, source.stance.value, source.model_dump_json())
                    for source in run.sources
                ],
            )
            connection.executemany(
                "INSERT INTO verifications VALUES (?, ?, ?, ?)",
                [
                    (run.id, result.node_id, result.grade.value, result.model_dump_json())
                    for result in run.graph.verifications
                ],
            )

    def get_analysis(self, run_id: str) -> AnalysisRun | None:
        with self._connect() as connection:
            row = connection.execute("SELECT payload_json FROM analyses WHERE id = ?", (run_id,)).fetchone()
        return AnalysisRun.model_validate_json(row["payload_json"]) if row else None

    def list_analyses(self, limit: int = 25) -> list[dict[str, str]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id, canonical_claim, provider, created_at FROM analyses ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def save_forensic_assessment(self, assessment: ForensicAssessment) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO forensic_assessments VALUES (?, ?, ?, ?, ?, ?)",
                (
                    assessment.id,
                    assessment.created_at.isoformat(),
                    assessment.company,
                    assessment.flag_code,
                    int(assessment.escalation_allowed),
                    assessment.model_dump_json(),
                ),
            )

    def list_forensic_assessments(self, limit: int = 25) -> list[ForensicAssessment]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload_json FROM forensic_assessments ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [ForensicAssessment.model_validate_json(row["payload_json"]) for row in rows]

    def save_dual_analysis(self, analysis: DualAnalysis) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO dual_analyses VALUES (?, ?, ?)",
                (analysis.id, analysis.created_at.isoformat(), analysis.model_dump_json()),
            )

    def cache_get(self, node_text: str) -> VerificationResult | None:
        node_hash = stable_id("verify", node_text.casefold())
        with self._connect() as connection:
            row = connection.execute("SELECT payload_json FROM verification_cache WHERE node_hash=?", (node_hash,)).fetchone()
        return VerificationResult.model_validate_json(row["payload_json"]) if row else None

    def cache_put(self, node_text: str, result: VerificationResult) -> None:
        node_hash = stable_id("verify", node_text.casefold())
        with self._connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO verification_cache(node_hash,payload_json) VALUES (?,?)",
                (node_hash, result.model_dump_json()),
            )

    def register_prediction(self, entry: TrackerEntry) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO tracker_entries VALUES (?, ?, ?, ?)",
                (entry.prediction.id, entry.prediction.deadline, int(entry.resolved), entry.model_dump_json()),
            )

    def resolve_prediction(self, prediction_id: str, observed_value: float) -> TrackerEntry:
        with self._connect() as connection:
            row = connection.execute("SELECT payload_json FROM tracker_entries WHERE prediction_id=?", (prediction_id,)).fetchone()
        if not row:
            raise ValueError(f"Unknown prediction: {prediction_id}")
        entry = TrackerEntry.model_validate_json(row["payload_json"])
        if entry.prediction.direction == "increase":
            outcome = observed_value > entry.prediction.threshold
        else:
            outcome = observed_value < entry.prediction.threshold
        entry = entry.model_copy(update={"resolved": True, "observed_value": observed_value, "outcome": outcome})
        self.register_prediction(entry)
        return entry

    def list_tracker_entries(self) -> list[TrackerEntry]:
        with self._connect() as connection:
            rows = connection.execute("SELECT payload_json FROM tracker_entries ORDER BY deadline").fetchall()
        return [TrackerEntry.model_validate_json(row["payload_json"]) for row in rows]

    def calibration(self) -> CalibrationSummary:
        resolved = [entry for entry in self.list_tracker_entries() if entry.resolved]
        if not resolved:
            return CalibrationSummary(resolved_count=0, brier_score=None, accuracy=None)
        outcomes = [1.0 if entry.outcome else 0.0 for entry in resolved]
        brier = sum((entry.confidence - outcome) ** 2 for entry, outcome in zip(resolved, outcomes)) / len(resolved)
        accuracy = sum((entry.confidence >= 0.5) == bool(outcome) for entry, outcome in zip(resolved, outcomes)) / len(resolved)
        return CalibrationSummary(resolved_count=len(resolved), brier_score=round(brier, 4), accuracy=round(accuracy, 4))
