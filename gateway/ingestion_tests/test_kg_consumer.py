from __future__ import annotations

import unittest
from datetime import datetime, timezone

from gateway.ingestion.consumers.kg_consumer import KGConsumer, highlight_id_for_highlight
from gateway.ingestion.kg.kg_store import CycleDetected
from gateway.ingestion.kg.models import CycleConflict, KGNode, MatchCandidate
from gateway.ingestion.models import (
    AccessPolicy,
    ClaimProposal,
    EvidenceRef,
    IngestionEnvelope,
    RelationProposal,
    SemanticExtraction,
)


class FakeKGStore:
    """Records every call so consumer behavior can be asserted in isolation
    from real Cypher/Neo4j -- that end-to-end path is T5's live smoke test."""

    def __init__(self, *, candidates_by_label: dict | None = None, cyclic_relations: set | None = None):
        self.candidates_by_label = candidates_by_label or {}
        self.cyclic_relations = cyclic_relations or set()
        self.resolved: list[tuple[str, str | None, str | None]] = []
        self.identity_proposals: list = []
        self.cycle_conflicts: list = []
        self.edges: list = []
        self.batched_edges: list = []
        self.claims: list = []
        self.purged: list[str] = []

    def resolve_or_create_node(self, label, *, domain="general", node_id=None, external_ids=None, fields=None, highlight_id=None):
        self.resolved.append((label, domain, highlight_id))
        node = KGNode(id=f"node:{label}", canonical_name=label, domain=domain)
        return node, self.candidates_by_label.get(label, []), True

    def submit_identity_proposal(self, proposal):
        self.identity_proposals.append(proposal)

    def submit_cycle_conflict(self, conflict):
        self.cycle_conflicts.append(conflict)

    def upsert_edge(self, edge, *, check_cycle=False):
        if check_cycle and edge.relation in self.cyclic_relations:
            raise CycleDetected("would cycle")
        self.edges.append(edge)

    def upsert_edge_batch(self, edges):
        self.batched_edges.extend(edges)

    def upsert_claim(self, claim):
        self.claims.append(claim)

    def purge_contributions(self, highlight_id):
        self.purged.append(highlight_id)


def _envelope(**overrides) -> IngestionEnvelope:
    defaults = dict(
        envelope_id="env-1",
        source_record_id="rec-1",
        canonical_record_id="rec-1",
        source_type="note",
        origin="obsidian://note",
        normalized_origin="obsidian://note",
        captured_at=datetime.now(timezone.utc),
        observed_at=None,
        raw_content_ref="bronze/rec-1.md",
        raw_content_hash="raw-hash",
        normalized_content_hash="norm-hash",
        highlight_index=0,
        highlight_text="Duration measures rate sensitivity.",
        highlight_context_text=None,
        highlight_start_char=0,
        highlight_end_char=35,
        version=1,
        access_policy=AccessPolicy(),
        extraction_version="v1",
        semantic=SemanticExtraction(),
        model_confidence=0.9,
        review_status="approved",
    )
    defaults.update(overrides)
    return IngestionEnvelope(**defaults)


def _relation(**overrides) -> RelationProposal:
    defaults = dict(
        proposal_id="rel-1",
        subject="Duration",
        predicate="RELATES_TO",
        object="Convexity",
        model_confidence=0.9,
        status="approved",
        source_record_id="rec-1",
        evidence=[EvidenceRef(source_record_id="rec-1", quote="q")],
    )
    defaults.update(overrides)
    return RelationProposal(**defaults)


def _claim(**overrides) -> ClaimProposal:
    defaults = dict(
        proposal_id="claim-1",
        text="Duration measures rate sensitivity.",
        concept_labels=["Duration"],
        model_confidence=0.9,
        status="current",
        source_record_id="rec-1",
        evidence=[EvidenceRef(source_record_id="rec-1", quote="Duration measures rate sensitivity.")],
    )
    defaults.update(overrides)
    return ClaimProposal(**defaults)


class RelationMappingTests(unittest.TestCase):
    def test_approved_relation_becomes_batched_edge(self):
        store = FakeKGStore()
        envelope = _envelope(semantic=SemanticExtraction(relations=[_relation()]))

        KGConsumer(store).consume(envelope)

        self.assertEqual(len(store.batched_edges), 1)
        edge = store.batched_edges[0]
        self.assertEqual(edge.subject_id, "node:Duration")
        self.assertEqual(edge.object_id, "node:Convexity")
        self.assertEqual(edge.highlight_id, highlight_id_for_highlight("rec-1", 0))

    def test_rejected_relation_is_not_written(self):
        store = FakeKGStore()
        envelope = _envelope(semantic=SemanticExtraction(relations=[_relation(status="rejected")]))

        KGConsumer(store).consume(envelope)

        self.assertEqual(store.batched_edges, [])
        self.assertEqual(store.edges, [])

    def test_relation_without_evidence_is_skipped(self):
        store = FakeKGStore()
        envelope = _envelope(semantic=SemanticExtraction(relations=[_relation(evidence=[])]))

        KGConsumer(store).consume(envelope)

        self.assertEqual(store.batched_edges, [])

    def test_hierarchical_relation_uses_singular_cycle_checked_path(self):
        store = FakeKGStore()
        envelope = _envelope(
            semantic=SemanticExtraction(relations=[_relation(predicate="PREREQUISITE_OF", hierarchical=True)])
        )

        KGConsumer(store).consume(envelope)

        self.assertEqual(len(store.edges), 1)
        self.assertEqual(store.batched_edges, [])

    def test_non_hierarchical_relation_skips_cycle_check_even_for_same_predicate(self):
        # T8: the trigger is the explicit per-instance flag, not the predicate
        # name -- the same predicate string is not hierarchical by default.
        store = FakeKGStore(cyclic_relations={"PREREQUISITE_OF"})
        envelope = _envelope(
            semantic=SemanticExtraction(relations=[_relation(predicate="PREREQUISITE_OF", hierarchical=False)])
        )

        KGConsumer(store).consume(envelope)

        self.assertEqual(len(store.batched_edges), 1)
        self.assertEqual(store.edges, [])
        self.assertEqual(store.cycle_conflicts, [])

    def test_cyclic_hierarchical_relation_is_diverted_and_filed_for_review(self):
        store = FakeKGStore(cyclic_relations={"PREREQUISITE_OF"})
        envelope = _envelope(
            semantic=SemanticExtraction(relations=[_relation(predicate="PREREQUISITE_OF", hierarchical=True)])
        )

        # Must not raise -- a cycle is diverted, not a hard failure (T8).
        KGConsumer(store).consume(envelope)

        self.assertEqual(store.edges, [])
        self.assertEqual(store.batched_edges, [])
        # Rejected, not lost: filed as a pending CycleConflict for review,
        # mirroring how T7 handles ambiguous identity instead of discarding.
        self.assertEqual(len(store.cycle_conflicts), 1)
        conflict = store.cycle_conflicts[0]
        self.assertIsInstance(conflict, CycleConflict)
        self.assertEqual(conflict.subject_id, "node:Duration")
        self.assertEqual(conflict.object_id, "node:Convexity")
        self.assertEqual(conflict.predicate, "PREREQUISITE_OF")
        self.assertEqual(conflict.status.value, "pending")
        self.assertEqual(conflict.provenance, ["env-1"])

    def test_ambiguous_candidate_files_identity_proposal_not_auto_merge(self):
        ambiguous = MatchCandidate(
            node=KGNode(id="node:existing", canonical_name="Duration"),
            match_type="lexical",
            score=0.6,
            deterministic=False,
            explanation="Partial lexical similarity.",
        )
        store = FakeKGStore(candidates_by_label={"Duration": [ambiguous]})
        envelope = _envelope(semantic=SemanticExtraction(relations=[_relation()]))

        KGConsumer(store).consume(envelope)

        self.assertEqual(len(store.identity_proposals), 1)
        proposal = store.identity_proposals[0]
        self.assertEqual(proposal.target_id, "node:existing")
        self.assertEqual(proposal.status.value, "pending")
        # The edge is still written using the resolved/created node -- review
        # doesn't block the write, it only flags the ambiguity (R4).
        self.assertEqual(len(store.batched_edges), 1)

    def test_deterministic_candidate_does_not_file_a_proposal(self):
        node = KGNode(id="node:Duration", canonical_name="Duration")
        deterministic = MatchCandidate(
            node=node, match_type="stable_id", score=1.0, deterministic=True, explanation="exact"
        )
        store = FakeKGStore(candidates_by_label={"Duration": [deterministic]})
        envelope = _envelope(semantic=SemanticExtraction(relations=[_relation()]))

        KGConsumer(store).consume(envelope)

        self.assertEqual(store.identity_proposals, [])


class ClaimMappingTests(unittest.TestCase):
    def test_current_claim_becomes_graph_claim_per_concept_label(self):
        store = FakeKGStore()
        envelope = _envelope(semantic=SemanticExtraction(claims=[_claim(concept_labels=["Duration", "Convexity"])]))

        KGConsumer(store).consume(envelope)

        self.assertEqual(len(store.claims), 2)
        subjects = {claim.subject_id for claim in store.claims}
        self.assertEqual(subjects, {"node:Duration", "node:Convexity"})
        for claim in store.claims:
            self.assertEqual(claim.highlight_id, highlight_id_for_highlight("rec-1", 0))
            self.assertEqual(claim.evidence_text, "Duration measures rate sensitivity.")
            self.assertEqual(claim.predicate, "ASSERTS")

    def test_disputed_claim_is_not_written(self):
        store = FakeKGStore()
        envelope = _envelope(semantic=SemanticExtraction(claims=[_claim(status="disputed")]))

        KGConsumer(store).consume(envelope)

        self.assertEqual(store.claims, [])

    def test_claim_without_concept_labels_is_skipped(self):
        store = FakeKGStore()
        envelope = _envelope(semantic=SemanticExtraction(claims=[_claim(concept_labels=[])]))

        KGConsumer(store).consume(envelope)

        self.assertEqual(store.claims, [])

    def test_claim_without_evidence_is_skipped(self):
        store = FakeKGStore()
        envelope = _envelope(semantic=SemanticExtraction(claims=[_claim(evidence=[])]))

        KGConsumer(store).consume(envelope)

        self.assertEqual(store.claims, [])


class PurgeOnSupersedeTests(unittest.TestCase):
    def test_supersede_purges_every_highlight_of_the_old_document(self):
        # The predecessor was parsed into 3 highlights, so all 3 stop vouching
        # -- purging only index 0 would orphan the other two in the graph.
        store = FakeKGStore()
        envelope = _envelope(
            supersedes_record_id="rec-0", supersedes_highlight_count=3, version=2
        )

        KGConsumer(store).consume(envelope)

        self.assertEqual(
            store.purged,
            [highlight_id_for_highlight("rec-0", index) for index in range(3)],
        )

    def test_purged_ids_never_collide_with_the_live_documents_highlights(self):
        # A sibling envelope repeats this purge, so it must not be able to
        # strip a contribution belonging to a highlight of the new document.
        old = {highlight_id_for_highlight("rec-0", index) for index in range(3)}
        new = {highlight_id_for_highlight("rec-1", index) for index in range(3)}

        self.assertEqual(old & new, set())

    def test_no_supersedes_record_id_means_no_purge(self):
        store = FakeKGStore()
        envelope = _envelope()

        KGConsumer(store).consume(envelope)

        self.assertEqual(store.purged, [])


class HighlightIdTests(unittest.TestCase):
    def test_deterministic_across_calls(self):
        self.assertEqual(highlight_id_for_highlight("rec-1", 0), highlight_id_for_highlight("rec-1", 0))

    def test_distinct_per_record(self):
        self.assertNotEqual(highlight_id_for_highlight("rec-1", 0), highlight_id_for_highlight("rec-2", 0))

    def test_distinct_per_highlight_within_one_document(self):
        self.assertNotEqual(
            highlight_id_for_highlight("rec-1", 0), highlight_id_for_highlight("rec-1", 1)
        )


if __name__ == "__main__":
    unittest.main()
