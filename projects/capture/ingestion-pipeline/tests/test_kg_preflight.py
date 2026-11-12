"""Tests for KG preflight and strict fail-closed writes (PLAN Phase 1)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from ingestion.kg.errors import (
    KGConfigurationError,
    KGReadError,
    KGSchemaError,
    KGUnavailableError,
    KGWriteError,
)
from ingestion.consumers.kg_consumer import KGConsumer
from ingestion.dispatch import Dispatcher
from ingestion.kg.kg_store import KGStore
from ingestion.kg.models import KGNode
from ingestion.models import (
    AccessPolicy,
    EvidenceRef,
    IngestionEnvelope,
    RelationProposal,
    SemanticExtraction,
)
from datetime import datetime, timezone


class SelectiveFakeDriver:
    """Fake Neo4j driver that succeeds by default but can fail a chosen stage.

    `fail_on` is a substring; any execute_query whose Cypher contains it raises.
    `read_back` is what a `RETURN 1 AS ok` read returns.
    """

    def __init__(
        self,
        *,
        fail_on: str | None = None,
        read_back_ok: bool = True,
        data_root: str = "data",
        neo4j_home: str = "/opt/neo4j",
    ):
        self.calls: list[str] = []
        self.fail_on = fail_on
        self.read_back_ok = read_back_ok
        self.data_root = data_root
        self.neo4j_home = neo4j_home

    def execute_query(self, query, **params):  # noqa: ANN001, ANN003
        self.calls.append(query)
        if self.fail_on is not None and self.fail_on in query:
            raise RuntimeError(f"boom on {self.fail_on}")
        if "SHOW SETTINGS" in query:
            return (
                [
                    {
                        "name": "server.directories.data",
                        "value": self.data_root,
                    },
                    {
                        "name": "server.directories.neo4j_home",
                        "value": self.neo4j_home,
                    },
                ],
                None,
                None,
            )
        if "RETURN 1 AS ok" in query:
            return ([{"ok": 1 if self.read_back_ok else 0}], None, None)
        return ([], None, None)


def _store(driver=None, *, strict: bool = False) -> KGStore:
    store = KGStore(strict=strict)
    if driver is not None:
        store._driver = driver  # noqa: SLF001
        store._available = True
    return store


def _neo4j_import_unavailable():
    """Make lazy Neo4j imports fail without depending on the host environment."""
    return patch.dict(sys.modules, {"neo4j": None})


class PreflightTests(unittest.TestCase):
    def test_preflight_passes_when_all_checks_ok(self) -> None:
        driver = SelectiveFakeDriver()
        _store(driver).preflight()  # should not raise
        self.assertTrue(any("__PreflightProbe" in c for c in driver.calls))
        self.assertTrue(any("RETURN 1 AS ok" in c for c in driver.calls))

    def test_missing_neo4j_package_raises_unavailable(self) -> None:
        with _neo4j_import_unavailable(), self.assertRaises(KGUnavailableError) as ctx:
            _store().preflight()
        self.assertIn("neo4j", str(ctx.exception).lower())

    def test_missing_constraint_raises_schema_error(self) -> None:
        driver = SelectiveFakeDriver(fail_on="CONSTRAINT")
        with self.assertRaises(KGSchemaError):
            _store(driver).preflight()

    def test_failed_write_probe_raises_write_error(self) -> None:
        driver = SelectiveFakeDriver(fail_on="__PreflightProbe")
        with self.assertRaises(KGWriteError):
            _store(driver).preflight()

    def test_failed_read_back_raises_read_error(self) -> None:
        driver = SelectiveFakeDriver(read_back_ok=False)
        with self.assertRaises(KGReadError):
            _store(driver).preflight()

    def test_preflight_does_not_leave_probe_data(self) -> None:
        # The probe create-and-deletes in one statement; assert the delete is there.
        driver = SelectiveFakeDriver()
        _store(driver).preflight()
        probe_calls = [c for c in driver.calls if "__PreflightProbe" in c]
        self.assertTrue(probe_calls)
        self.assertTrue(all("DELETE n" in c for c in probe_calls))

    def test_preflight_accepts_approved_relative_data_root(self) -> None:
        driver = SelectiveFakeDriver(
            data_root="data",
            neo4j_home="/approved/neo4j",
        )
        store = KGStore(expected_data_root=Path("/approved/neo4j/data"))

        store._driver = driver  # noqa: SLF001
        store.preflight()

        self.assertTrue(any("SHOW SETTINGS" in call for call in driver.calls))

    def test_preflight_rejects_unapproved_data_root_before_writes(self) -> None:
        driver = SelectiveFakeDriver(data_root="/elsewhere/neo4j")
        store = KGStore(expected_data_root=Path("/approved/neo4j"))
        store._driver = driver  # noqa: SLF001

        with self.assertRaises(KGConfigurationError):
            store.preflight()

        self.assertFalse(any("CONSTRAINT" in call for call in driver.calls))
        self.assertFalse(any("__PreflightProbe" in call for call in driver.calls))


class StrictWriteTests(unittest.TestCase):
    def test_strict_write_raises_when_unavailable(self) -> None:
        store = _store(strict=True)
        with _neo4j_import_unavailable(), self.assertRaises(KGUnavailableError):
            store.upsert_node(KGNode(id="n1", canonical_name="Duration", domain="finance"))

    def test_non_strict_write_is_graceful_when_unavailable(self) -> None:
        store = _store(strict=False)
        # Should not raise — preserves user-facing graceful degradation.
        with _neo4j_import_unavailable():
            store.upsert_node(KGNode(id="n1", canonical_name="Duration", domain="finance"))

    def test_strict_identity_lookup_raises_instead_of_empty(self) -> None:
        # The core rule: an unavailable lookup must not read as "nothing found".
        store = _store(strict=True)
        with _neo4j_import_unavailable(), self.assertRaises(KGUnavailableError):
            store.find_identity_candidates("Duration", domain="finance")

    def test_non_strict_identity_lookup_returns_empty_when_unavailable(self) -> None:
        store = _store(strict=False)
        with _neo4j_import_unavailable():
            self.assertEqual(store.find_identity_candidates("Duration", domain="finance"), [])

    def test_strict_write_raises_on_driver_error(self) -> None:
        driver = SelectiveFakeDriver(fail_on="MERGE")
        store = _store(driver, strict=True)
        with self.assertRaises(KGWriteError):
            store.upsert_node(KGNode(id="n1", canonical_name="Duration", domain="finance"))


class _FakeDispatchStore:
    """Minimal store for the Dispatcher: only the two methods it calls."""

    def __init__(self) -> None:
        self.records: list[dict] = []

    def dispatch_status(self, envelope_id, target, version):  # noqa: ANN001
        return None

    def record_dispatch(self, **kwargs):  # noqa: ANN003
        self.records.append(kwargs)


def _envelope_with_relation() -> IngestionEnvelope:
    return IngestionEnvelope(
        envelope_id="env-fc-1",
        source_record_id="rec-fc-1",
        canonical_record_id="rec-fc-1",
        source_type="obsidian",
        origin="vault/n.md",
        normalized_origin="vault/n.md",
        captured_at=datetime(2026, 7, 26, tzinfo=timezone.utc),
        observed_at=None,
        raw_content_ref="bronze/rec-fc-1.md",
        raw_content_hash="rawhash",
        normalized_content_hash="normhash",
        highlight_index=0,
        highlight_text="duration measures rate sensitivity",
        highlight_start_char=0,
        highlight_end_char=34,
        version=1,
        access_policy=AccessPolicy(allowed_consumers=["kg"]),
        extraction_version="semantic_extraction_v1",
        semantic=SemanticExtraction(
            relations=[
                RelationProposal(
                    proposal_id="rel-fc-1",
                    subject="Duration",
                    predicate="MEASURES",
                    object="Rate sensitivity",
                    model_confidence=0.9,
                    status="approved",
                    source_record_id="rec-fc-1",
                    domain="finance",
                    evidence=[EvidenceRef(source_record_id="rec-fc-1", quote="duration measures rate sensitivity")],
                )
            ]
        ),
        model_confidence=0.9,
        review_status="approved",
    )


class FailClosedDispatchTests(unittest.TestCase):
    """Phase 1 exit criterion (§5.6): no KG failure can become a successful dispatch."""

    def test_unavailable_kg_yields_failed_never_done(self) -> None:
        # Force the lazy dependency import to fail so this can never touch a
        # host's live graph, even when the production driver is installed.
        strict_store = KGStore(strict=True)
        consumer = KGConsumer(strict_store)
        store = _FakeDispatchStore()
        with _neo4j_import_unavailable():
            results = Dispatcher(store, [consumer]).dispatch(_envelope_with_relation())

        kg_results = [r for r in results if r.target == "kg"]
        self.assertEqual(len(kg_results), 1)
        self.assertEqual(kg_results[0].status, "failed")
        self.assertNotEqual(kg_results[0].status, "done")
        # And the ledger recorded failed, not done.
        self.assertTrue(store.records)
        self.assertTrue(all(rec["status"] == "failed" for rec in store.records))

    def test_non_strict_kg_does_not_raise_out_of_consume(self) -> None:
        # Contrast: a non-strict store degrades gracefully and reports done
        # (the old behavior) — this is exactly what strict mode fixes.
        graceful_store = KGStore(strict=False)
        consumer = KGConsumer(graceful_store)
        store = _FakeDispatchStore()
        with _neo4j_import_unavailable():
            results = Dispatcher(store, [consumer]).dispatch(_envelope_with_relation())
        kg_results = [r for r in results if r.target == "kg"]
        self.assertEqual(kg_results[0].status, "done")


if __name__ == "__main__":
    unittest.main()
