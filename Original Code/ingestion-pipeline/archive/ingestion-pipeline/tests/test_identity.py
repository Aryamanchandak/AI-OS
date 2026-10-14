from __future__ import annotations

from datetime import datetime, timedelta
import unittest

from pipeline.kg.extraction import _concept_id
from pipeline.kg.identity import external_id_key, normalize_label
from pipeline.kg.kg_store import KGStore
from pipeline.kg.models import (
    Claim,
    IdentityLink,
    IdentityProposal,
    IdentityRelation,
    ReviewStatus,
)


class FakeDriver:
    def __init__(self, responder=None):
        self.calls = []
        self.responder = responder or (lambda _query, _params: [])

    def execute_query(self, query, **params):
        self.calls.append((query, params))
        return self.responder(query, params), None, None


def store_with(driver: FakeDriver) -> KGStore:
    store = KGStore()
    store._driver = driver
    store._available = True
    store._constraints_ready = True
    return store


class IdentityTests(unittest.TestCase):
    def test_label_and_identifier_normalization_is_lexical_only(self):
        self.assertEqual(normalize_label("  Café—RATE (APR)  "), "café rate apr")
        self.assertEqual(external_id_key(" DOI ", " 10.1000/ABC "), "doi:10.1000/abc")
        with self.assertRaises(ValueError):
            external_id_key("", "123")

    def test_concept_ids_are_stable_within_source_but_do_not_collapse_sources(self):
        self.assertEqual(_concept_id("Duration", "hash-a"), _concept_id("duration", "hash-a"))
        self.assertNotEqual(_concept_id("Duration", "hash-a"), _concept_id("Duration", "hash-b"))

    def test_resolver_only_marks_stable_identifiers_deterministic(self):
        def respond(query, _params):
            if "AS match_type" in query:
                return [
                    {"id": "n1", "name": "APR", "domain": "finance", "fields": ["finance"], "match_type": "external_id"},
                    {"id": "n2", "name": "APR", "domain": "medicine", "fields": ["medicine"], "match_type": "normalized_label"},
                ]
            return [{"id": "n1", "name": "APR", "domain": "finance"}]

        store = store_with(FakeDriver(respond))
        candidates = store.find_identity_candidates(
            "APR", domain="finance", external_ids={"standard": "APR"}
        )
        self.assertTrue(candidates[0].deterministic)
        self.assertEqual(candidates[0].match_type, "external_id")
        self.assertFalse(candidates[1].deterministic)
        self.assertIn("review", candidates[1].explanation.lower())

    def test_proposal_is_inert_until_review_and_rejection_creates_no_link(self):
        driver = FakeDriver()
        store = store_with(driver)
        proposal = IdentityProposal(
            id="p1", source_id="x", target_id="y",
            relation=IdentityRelation.ALIAS_OF,
            rationale="User confirmed the historic abbreviation.",
            provenance=["conversation:abc:turn:4"],
        )
        store.submit_identity_proposal(proposal)
        submit_query, submit_params = driver.calls[-1]
        self.assertIn("IdentityProposal", submit_query)
        self.assertNotIn("ALIAS_OF", submit_query)
        self.assertEqual(submit_params["status"], "pending")

        store.review_identity_proposal("p1", ReviewStatus.REJECTED, "reviewer-1")
        review_query, review_params = driver.calls[-1]
        self.assertEqual(review_params["status"], "rejected")
        self.assertIn("WHEN $status = 'approved'", review_query)
        with self.assertRaises(ValueError):
            store.review_identity_proposal("p1", ReviewStatus.PENDING, "reviewer-1")

    def test_claim_write_preserves_temporal_and_provenance_fields(self):
        driver = FakeDriver()
        store = store_with(driver)
        observed = datetime(2026, 1, 2, 3, 4, 5)
        claim = Claim(
            id="claim-1", subject_id="x", predicate="HAS_RATE",
            object_text="4.5%", source="bronze:hash", source_version="v2",
            observed_at=observed, confidence=0.8, evidence_quality="primary",
        )
        store.upsert_claim(claim)
        query, params = driver.calls[-1]
        self.assertIn("MERGE (c:Claim", query)
        self.assertEqual(params["observed_at"], observed.isoformat())
        self.assertEqual(params["source"], "bronze:hash")
        self.assertEqual(params["status"], "current")

    def test_approved_link_requires_auditable_review(self):
        store = store_with(FakeDriver())
        link = IdentityLink(
            id="link-1", source_id="x", target_id="y",
            relation=IdentityRelation.SAME_AS, status=ReviewStatus.APPROVED,
        )
        with self.assertRaises(ValueError):
            store.upsert_identity_link(link)

    def test_identity_expansion_terms_are_available_for_vector_queries(self):
        driver = FakeDriver(lambda _query, _params: [
            {"label": "Annual percentage rate"}, {"label": "APR"}
        ])
        store = store_with(driver)
        terms = store.identity_expansion_terms("x")
        self.assertEqual(terms, ["Annual percentage rate", "APR"])
        query, _ = driver.calls[-1]
        self.assertIn("ALIAS_OF|SAME_AS", query)
        self.assertIn("r.status = 'approved'", query)

    def test_identity_cluster_filters_review_status_and_validity(self):
        driver = FakeDriver(lambda _query, _params: [
            {"id": "x", "name": "Current name", "domain": "general"},
            {"id": "y", "name": "Historic name", "domain": "general"},
        ])
        store = store_with(driver)
        at = datetime.utcnow() - timedelta(days=1)
        hits = store.identity_cluster("x", as_of=at)
        query, params = driver.calls[-1]
        self.assertEqual([hit.id for hit in hits], ["x", "y"])
        self.assertIn("r.status = 'approved'", query)
        self.assertIn("r.valid_from", query)
        self.assertIn("r.valid_to", query)
        self.assertEqual(params["as_of"], at.isoformat())


if __name__ == "__main__":
    unittest.main()
