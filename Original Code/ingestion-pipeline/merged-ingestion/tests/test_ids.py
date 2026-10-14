"""Tests for deterministic, domain-scoped ids (PLAN Phase 2 / decision 4)."""

from __future__ import annotations

import unittest

from ingestion.ids import concept_id_for, highlight_id_for_highlight
from ingestion.kg.kg_store import KGStore


class ConceptIdTests(unittest.TestCase):
    def test_same_label_and_domain_is_stable(self) -> None:
        self.assertEqual(
            concept_id_for("Duration", "finance"),
            concept_id_for("Duration", "finance"),
        )

    def test_normalization_makes_casing_and_spacing_irrelevant(self) -> None:
        self.assertEqual(
            concept_id_for("  DURATION  ", "Finance"),
            concept_id_for("duration", "finance"),
        )

    def test_different_domain_is_a_different_concept(self) -> None:
        # The core "same word != same concept" guarantee.
        self.assertNotEqual(
            concept_id_for("duration", "economics"),
            concept_id_for("duration", "physics"),
        )

    def test_specific_domain_differs_from_general(self) -> None:
        self.assertNotEqual(
            concept_id_for("duration", "finance"),
            concept_id_for("duration", "general"),
        )

    def test_different_label_is_a_different_concept(self) -> None:
        self.assertNotEqual(
            concept_id_for("duration", "finance"),
            concept_id_for("convexity", "finance"),
        )

    def test_highlight_id_is_deterministic(self) -> None:
        self.assertEqual(highlight_id_for_highlight("rec-1", 0), highlight_id_for_highlight("rec-1", 0))
        self.assertNotEqual(highlight_id_for_highlight("rec-1", 0), highlight_id_for_highlight("rec-2", 0))


class FakeDriver:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def execute_query(self, query, **params):  # noqa: ANN001, ANN003
        self.calls.append((query, params))
        return [], None, None  # no existing candidates -> force a create


def _store_with(driver: FakeDriver) -> KGStore:
    store = KGStore()
    store._driver = driver  # noqa: SLF001
    store._available = True
    store._constraints_ready = True
    return store


class ResolveOrCreateDeterminismTests(unittest.TestCase):
    def test_new_concept_gets_deterministic_domain_scoped_id(self) -> None:
        node, _candidates, created = _store_with(FakeDriver()).resolve_or_create_node(
            "Duration", domain="finance"
        )
        self.assertTrue(created)
        self.assertEqual(node.id, concept_id_for("Duration", "finance"))

    def test_retry_recomputes_the_same_id(self) -> None:
        first, _, _ = _store_with(FakeDriver()).resolve_or_create_node("Duration", domain="finance")
        second, _, _ = _store_with(FakeDriver()).resolve_or_create_node("Duration", domain="finance")
        self.assertEqual(first.id, second.id)

    def test_two_domains_same_word_get_distinct_ids(self) -> None:
        econ, _, _ = _store_with(FakeDriver()).resolve_or_create_node("duration", domain="economics")
        phys, _, _ = _store_with(FakeDriver()).resolve_or_create_node("duration", domain="physics")
        self.assertNotEqual(econ.id, phys.id)


if __name__ == "__main__":
    unittest.main()
