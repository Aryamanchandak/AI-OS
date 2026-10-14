"""Tests for the seven-table SQLite content store (PLAN Phase 5)."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from ingestion.content_store import CONTENT_TABLES, ContentStore, source_type_for_origin
from ingestion.ids import highlight_id_for_highlight
from ingestion.models import (
    AccessPolicy,
    ClaimProposal,
    EvidenceRef,
    IngestionEnvelope,
    RelationProposal,
    SemanticExtraction,
)


def make_envelope(
    *,
    source_record_id: str = "rec-1",
    supersedes: str | None = None,
    relations: list[RelationProposal] | None = None,
    claims: list[ClaimProposal] | None = None,
    field_tags: list[str] | None = None,
) -> IngestionEnvelope:
    return IngestionEnvelope(
        envelope_id=f"env-{source_record_id}",
        source_record_id=source_record_id,
        canonical_record_id="canon-1",
        source_type="obsidian_note",
        origin="vault/note.md",
        normalized_origin="vault/note.md",
        captured_at=datetime(2026, 7, 25, tzinfo=timezone.utc),
        observed_at=None,
        raw_content_ref="bronze/rec-1.md",
        raw_content_hash="rawhash",
        normalized_content_hash="normhash",
        highlight_index=0,
        highlight_text="Duration measures rate sensitivity.",
        highlight_context_text=None,
        highlight_start_char=0,
        highlight_end_char=36,
        version=1,
        supersedes_record_id=supersedes,
        access_policy=AccessPolicy(),
        extraction_version="semantic_extraction_v1",
        semantic=SemanticExtraction(
            relations=relations or [],
            claims=claims or [],
            field_tags=field_tags or [],
        ),
        model_confidence=0.9,
        review_status="approved",
    )


def approved_relation(pid: str = "rel-1") -> RelationProposal:
    return RelationProposal(
        proposal_id=pid,
        subject="Duration",
        predicate="MEASURES",
        object="Rate sensitivity",
        model_confidence=0.9,
        status="approved",
        source_record_id="rec-1",
        domain="finance",
        evidence=[EvidenceRef(source_record_id="rec-1", quote="duration measures rate sensitivity")],
    )


def current_claim(pid: str = "clm-1") -> ClaimProposal:
    return ClaimProposal(
        proposal_id=pid,
        text="Duration is a risk measure.",
        concept_labels=["Duration"],
        model_confidence=0.8,
        status="current",
        source_record_id="rec-1",
        evidence=[EvidenceRef(source_record_id="rec-1", quote="duration is a risk measure")],
    )


class ContentStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self._dir = tempfile.TemporaryDirectory()
        self.path = Path(self._dir.name) / "content.db"
        self.store = ContentStore(self.path)

    def tearDown(self) -> None:
        self.store.close()
        self._dir.cleanup()

    def test_fresh_db_creates_exactly_seven_content_tables(self) -> None:
        self.assertEqual(self.store.table_names(), set(CONTENT_TABLES))
        self.assertEqual(len(CONTENT_TABLES), 7)

    def test_project_envelope_writes_source_acquisition_highlight(self) -> None:
        self.store.project_envelope(make_envelope(relations=[approved_relation()]))
        self.assertEqual(self.store.count("source"), 1)
        self.assertEqual(self.store.count("acquisition"), 1)
        self.assertEqual(self.store.count("highlight"), 1)
        self.assertEqual(self.store.count("transformation"), 1)

    def test_highlight_row_is_real_and_carries_its_text_context_and_position(self) -> None:
        self.store.project_envelope(make_envelope(relations=[approved_relation()]))
        row = list(self.store.rows("highlight"))[0]
        self.assertEqual(row["is_temporary_stand_in"], 0)
        self.assertEqual(row["text"], "Duration measures rate sensitivity.")
        self.assertEqual(row["order_index"], 0)
        self.assertEqual(row["location_type"], "char_range")
        self.assertEqual(row["location_value"], "0:36")
        self.assertEqual(row["highlight_id"], highlight_id_for_highlight("rec-1", 0))
        # The highlight's own hash, not the parent document's.
        self.assertNotEqual(row["content_hash"], "normhash")

    def test_relation_becomes_claim_pointing_to_highlight_and_transformation(self) -> None:
        self.store.project_envelope(make_envelope(relations=[approved_relation()]))
        claim = list(self.store.rows("claim"))[0]
        self.assertEqual(claim["highlight_id"], highlight_id_for_highlight("rec-1", 0))
        self.assertEqual(claim["evidence_text"], "duration measures rate sensitivity")
        self.assertIsNotNone(claim["transformation_id"])
        self.assertEqual(claim["subject"], "Duration")

    def test_claim_proposal_becomes_asserts_claim(self) -> None:
        self.store.project_envelope(make_envelope(claims=[current_claim()]))
        claim = list(self.store.rows("claim"))[0]
        self.assertEqual(claim["predicate"], "ASSERTS")
        self.assertEqual(claim["subject"], "Duration")
        self.assertEqual(claim["object"], "Duration is a risk measure.")

    def test_field_tags_stored_as_system_provenance(self) -> None:
        self.store.project_envelope(make_envelope(field_tags=["finance", "risk"]))
        tags = list(self.store.rows("tag"))
        self.assertEqual({t["tag"] for t in tags}, {"finance", "risk"})
        self.assertTrue(all(t["provenance"] == "system" for t in tags))

    def test_comment_table_stays_empty(self) -> None:
        self.store.project_envelope(make_envelope(relations=[approved_relation()]))
        self.assertEqual(self.store.count("comment"), 0)

    def test_reprojecting_same_envelope_creates_no_duplicates(self) -> None:
        env = make_envelope(relations=[approved_relation()], claims=[current_claim()], field_tags=["finance"])
        self.store.project_envelope(env)
        self.store.project_envelope(env)
        self.assertEqual(self.store.count("source"), 1)
        self.assertEqual(self.store.count("acquisition"), 1)
        self.assertEqual(self.store.count("highlight"), 1)
        self.assertEqual(self.store.count("claim"), 2)  # one relation + one claim
        self.assertEqual(self.store.count("tag"), 1)

    def test_claim_without_evidence_text_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.store.insert_claim(
                claim_id="c1",
                highlight_id="h1",
                subject="A",
                predicate="P",
                object="B",
                evidence_text="   ",
                created_at="now",
            )

    def test_claim_without_highlight_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.store.insert_claim(
                claim_id="c1",
                highlight_id="",
                subject="A",
                predicate="P",
                object="B",
                evidence_text="some evidence",
                created_at="now",
            )

    def test_foreign_keys_block_orphan_claim(self) -> None:
        # A claim whose highlight does not exist violates the FK.
        with self.assertRaises(sqlite3.IntegrityError):
            with self.store._conn:  # noqa: SLF001 - deliberate FK probe
                self.store.insert_claim(
                    claim_id="c1",
                    highlight_id="missing-highlight",
                    subject="A",
                    predicate="P",
                    object="B",
                    evidence_text="some evidence",
                    created_at="now",
                    transformation_id=None,
                )

    def test_failed_projection_leaves_no_partial_rows(self) -> None:
        # Force a mid-transaction failure: a relation whose evidence quote is
        # blank would raise inside project_envelope's transaction. We build it by
        # bypassing the model guard is not possible (EvidenceRef requires
        # min_length=1), so instead simulate by monkeypatching insert_tag to fail
        # after claims are written.
        env = make_envelope(relations=[approved_relation()], field_tags=["finance"])

        def boom(**_kwargs: object) -> None:
            raise RuntimeError("simulated tag failure")

        self.store.insert_tag = boom  # type: ignore[method-assign]
        with self.assertRaises(RuntimeError):
            self.store.project_envelope(env)
        # Whole transaction rolled back — nothing persisted.
        for table in CONTENT_TABLES:
            self.assertEqual(self.store.count(table), 0, f"{table} should be empty after rollback")

    def test_source_type_is_mapped_from_origin_not_the_raw_channel(self) -> None:
        # T38: Source.source_type is the intellectual type (schema enum), not
        # the capture channel — those are different fields (Acquisition.origin_system).
        self.store.project_envelope(make_envelope())
        source = list(self.store.rows("source"))[0]
        acquisition = list(self.store.rows("acquisition"))[0]
        self.assertEqual(source["source_type"], "note")
        self.assertEqual(acquisition["origin_system"], "obsidian_note")

    def test_unmapped_origin_system_fails_loud(self) -> None:
        with self.assertRaises(ValueError):
            source_type_for_origin("some_future_channel")

    def test_invalid_location_type_fails_loud_in_python(self) -> None:
        # INSERT OR IGNORE (needed for idempotent redispatch) would otherwise
        # silently swallow a CHECK violation, so this must be raised before SQL.
        with self.assertRaises(ValueError):
            self.store.insert_highlight(
                highlight_id="h1",
                acquisition_id="a1",
                source_id=None,
                text="t",
                content_hash="h",
                location_type="not_a_real_location_type",
                ingested_at="now",
            )

    def test_invalid_tag_provenance_fails_loud_in_python(self) -> None:
        with self.assertRaises(ValueError):
            self.store.insert_tag(
                tag_id="t1", highlight_id="h1", tag="x", provenance="bogus"
            )

    def test_check_constraint_is_still_a_db_level_backstop(self) -> None:
        # Bypass the Python-level guard to prove the CHECK constraint itself
        # exists (defense in depth for any writer that isn't insert_highlight).
        with self.assertRaises(sqlite3.IntegrityError):
            with self.store._conn:  # noqa: SLF001 - deliberate CHECK probe
                self.store._conn.execute(
                    "INSERT INTO highlight (highlight_id,acquisition_id,location_type,ingested_at) "
                    "VALUES (?,?,?,?)",
                    ("h1", "a1", "not_a_real_location_type", "now"),
                )

    def test_supersede_replaces_predecessor_highlight_rows(self) -> None:
        first = make_envelope(source_record_id="rec-1", relations=[approved_relation("rel-1")])
        self.store.project_envelope(first)
        self.assertEqual(self.store.count("claim"), 1)

        # A new record supersedes rec-1: its claims replace the old ones.
        second = make_envelope(
            source_record_id="rec-2",
            supersedes="rec-1",
            relations=[
                RelationProposal(
                    proposal_id="rel-2",
                    subject="Duration",
                    predicate="MEASURES",
                    object="Interest rate risk",
                    model_confidence=0.9,
                    status="approved",
                    source_record_id="rec-2",
                    domain="finance",
                    evidence=[EvidenceRef(source_record_id="rec-2", quote="new evidence")],
                )
            ],
        )
        self.store.project_envelope(second)
        # Old highlight's claim gone; new highlight's claim present.
        highlights = {h["highlight_id"] for h in self.store.rows("highlight")}
        self.assertIn(highlight_id_for_highlight("rec-2", 0), highlights)
        self.assertNotIn(highlight_id_for_highlight("rec-1", 0), highlights)
        claims = list(self.store.rows("claim"))
        self.assertEqual(len(claims), 1)
        self.assertEqual(claims[0]["evidence_text"], "new evidence")


if __name__ == "__main__":
    unittest.main()
