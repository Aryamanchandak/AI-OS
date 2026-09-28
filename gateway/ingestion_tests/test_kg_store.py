from __future__ import annotations

import sys
import types
import unittest
from unittest.mock import patch

from gateway.ingestion.kg.errors import KGReadError, KGUnavailableError
from gateway.ingestion.kg.kg_store import CycleDetected, KGStore
from gateway.ingestion.kg.models import Claim, ClaimStatus, CycleConflict, KGEdge, KGNode

# `neo4j` is an optional extra, deliberately not installed in the test env
# (see test_kg_preflight.py) so the "package missing" fail path is exercised
# for real. Tests that need to get past the `from neo4j import RoutingControl`
# inside `_check_cycle` inject a minimal fake module instead of installing it.
_FAKE_NEO4J_MODULE = types.SimpleNamespace(RoutingControl=types.SimpleNamespace(READ="READ"))


class FakeDriver:
    """Mirrors the FakeDriver used for IP's kg_store tests: records every call
    and returns whatever `responder(query, params)` decides."""

    def __init__(self, responder=None, *, raises: Exception | None = None):
        self.calls: list[tuple[str, dict]] = []
        self.responder = responder or (lambda _query, _params: [])
        self.raises = raises

    def execute_query(self, query, **params):
        self.calls.append((query, params))
        if self.raises is not None:
            raise self.raises
        return self.responder(query, params), None, None


def store_with(driver: FakeDriver) -> KGStore:
    store = KGStore()
    store._driver = driver
    store._available = True
    store._constraints_ready = True
    return store


class UpsertNodeContributionTests(unittest.TestCase):
    def test_upsert_node_passes_highlight_id_param(self):
        driver = FakeDriver()
        store = store_with(driver)
        node = KGNode(id="n1", canonical_name="Duration", domain="finance")

        store.upsert_node(node, highlight_id="hl-1")

        self.assertEqual(len(driver.calls), 1)
        _, params = driver.calls[0]
        self.assertEqual(params["highlight_id"], "hl-1")
        self.assertEqual(params["id"], "n1")

    def test_upsert_node_without_highlight_id_passes_none(self):
        driver = FakeDriver()
        store = store_with(driver)
        node = KGNode(id="n1", canonical_name="Duration")

        store.upsert_node(node)

        _, params = driver.calls[0]
        self.assertIsNone(params["highlight_id"])

    def test_get_node_reads_back_contributing_highlight_ids(self):
        def respond(_query, _params):
            return [
                {
                    "id": "n1",
                    "name": "Duration",
                    "domain": "finance",
                    "fields": ["finance"],
                    "external_ids": [],
                    "contributing_highlight_ids": ["hl-1", "hl-2"],
                    "created_at": None,
                }
            ]

        store = store_with(FakeDriver(respond))
        node = store.get_node("n1")

        self.assertIsNotNone(node)
        self.assertEqual(node.contributing_highlight_ids, ["hl-1", "hl-2"])


class UpsertClaimTests(unittest.TestCase):
    def test_upsert_claim_writes_highlight_id_and_evidence_text(self):
        driver = FakeDriver()
        store = store_with(driver)
        claim = Claim(
            id="c1",
            subject_id="n1",
            predicate="ASSERTS",
            object_text="Duration measures rate sensitivity.",
            source="record-1",
            highlight_id="hl-1",
            evidence_text="Duration measures rate sensitivity.",
        )

        store.upsert_claim(claim)

        _, params = driver.calls[0]
        self.assertEqual(params["highlight_id"], "hl-1")
        self.assertEqual(params["evidence_text"], "Duration measures rate sensitivity.")

    def test_upsert_claim_raises_on_write_failure(self):
        store = store_with(FakeDriver(raises=RuntimeError("boom")))
        claim = Claim(
            id="c1",
            subject_id="n1",
            predicate="ASSERTS",
            object_text="text",
            source="record-1",
            highlight_id="hl-1",
            evidence_text="text",
        )

        with self.assertRaises(RuntimeError):
            store.upsert_claim(claim)

    def test_claim_requires_evidence_pointer(self):
        with self.assertRaises(Exception):
            Claim(
                id="c1",
                subject_id="n1",
                predicate="ASSERTS",
                object_text="text",
                source="record-1",
                highlight_id="hl-1",
                evidence_text="",  # min_length=1
            )

    def test_claims_for_identity_reconstructs_evidence_pointer(self):
        def respond(query, _params):
            if "ALIAS_OF|SAME_AS" in query and "ASSERTS" in query:
                return [
                    {
                        "id": "c1",
                        "subject_id": "n1",
                        "predicate": "ASSERTS",
                        "object_id": None,
                        "object_text": "Duration measures rate sensitivity.",
                        "source": "record-1",
                        "source_version": "1",
                        "fields": [],
                        "observed_at": None,
                        "ingested_at": "2026-07-23T00:00:00",
                        "valid_from": None,
                        "valid_to": None,
                        "confidence": 0.9,
                        "evidence_quality": None,
                        "status": "current",
                        "highlight_id": "hl-1",
                        "evidence_text": "Duration measures rate sensitivity.",
                    }
                ]
            return []

        store = store_with(FakeDriver(respond))
        claims = store.claims_for_identity("n1")

        self.assertEqual(len(claims), 1)
        self.assertEqual(claims[0].highlight_id, "hl-1")
        self.assertEqual(claims[0].status, ClaimStatus.CURRENT)


class PurgeContributionsTests(unittest.TestCase):
    def test_purge_issues_four_scoped_writes(self):
        driver = FakeDriver()
        store = store_with(driver)

        store.purge_contributions("hl-1")

        self.assertEqual(len(driver.calls), 4)
        for query, params in driver.calls[:3]:
            self.assertEqual(params.get("highlight_id"), "hl-1")
        # Step 4 (orphan cleanup) is a global sweep — no highlight_id needed.
        self.assertNotIn("highlight_id", driver.calls[3][1])

    def test_purge_reraises_on_write_failure(self):
        store = store_with(FakeDriver(raises=RuntimeError("neo4j down")))

        with self.assertRaises(RuntimeError):
            store.purge_contributions("hl-1")

    def test_purge_skipped_quietly_when_neo4j_unavailable(self):
        store = KGStore()
        store._get_driver = lambda: None  # force the "unavailable" branch, no real network call
        # Should not raise even though nothing is connected.
        store.purge_contributions("hl-1")


class CycleConflictTests(unittest.TestCase):
    def test_submit_cycle_conflict_writes_expected_params(self):
        driver = FakeDriver()
        store = store_with(driver)
        conflict = CycleConflict(
            id="cc-1",
            subject_id="n1",
            subject_name="Duration",
            predicate="PREREQUISITE_OF",
            object_id="n2",
            object_name="Convexity",
            rationale="would close a cycle",
            provenance=["env-1"],
            proposed_by="kg_consumer",
        )

        store.submit_cycle_conflict(conflict)

        self.assertEqual(len(driver.calls), 1)
        _, params = driver.calls[0]
        self.assertEqual(params["id"], "cc-1")
        self.assertEqual(params["subject_id"], "n1")
        self.assertEqual(params["object_id"], "n2")
        self.assertEqual(params["status"], "pending")


class UpsertEdgeCheckCycleTests(unittest.TestCase):
    def _edge(self) -> KGEdge:
        return KGEdge(id="e1", subject_id="n1", relation="PREREQUISITE_OF", object_id="n2")

    def test_check_cycle_true_raises_when_path_exists(self):
        def respond(query, _params):
            if "shortestPath" in query:
                return [{"would_cycle": True}]
            return []

        store = store_with(FakeDriver(respond))

        with patch.dict(sys.modules, {"neo4j": _FAKE_NEO4J_MODULE}):
            with self.assertRaises(CycleDetected):
                store.upsert_edge(self._edge(), check_cycle=True)

    def test_check_cycle_false_skips_the_cycle_query_entirely(self):
        driver = FakeDriver()
        store = store_with(driver)

        store.upsert_edge(self._edge(), check_cycle=False)

        self.assertEqual(len(driver.calls), 1)  # only the edge upsert, no cycle query
        self.assertNotIn("shortestPath", driver.calls[0][0])

    def test_check_cycle_true_writes_edge_when_no_path_exists(self):
        driver = FakeDriver(lambda _q, _p: [{"would_cycle": False}])
        store = store_with(driver)

        with patch.dict(sys.modules, {"neo4j": _FAKE_NEO4J_MODULE}):
            store.upsert_edge(self._edge(), check_cycle=True)

        self.assertEqual(len(driver.calls), 2)  # cycle query, then the edge upsert


class CheckCycleFailLoudTests(unittest.TestCase):
    """T8: an unanswered cycle check is not 'no cycle exists' -- strict mode
    must raise rather than silently writing the edge through."""

    def test_strict_mode_raises_kgreaderror_on_query_failure(self):
        store = store_with(FakeDriver(raises=RuntimeError("neo4j down")))
        store._strict = True

        with self.assertRaises(KGReadError):
            store._check_cycle("n1", "n2")

    def test_strict_mode_raises_kgunavailable_when_driver_missing(self):
        store = KGStore(strict=True)
        store._get_driver = lambda: None

        with self.assertRaises(KGUnavailableError):
            store._check_cycle("n1", "n2")

    def test_non_strict_mode_degrades_quietly_on_query_failure(self):
        store = store_with(FakeDriver(raises=RuntimeError("neo4j down")))
        store._strict = False

        # Should not raise -- graceful-degrade callers keep prior behavior.
        store._check_cycle("n1", "n2")


if __name__ == "__main__":
    unittest.main()
