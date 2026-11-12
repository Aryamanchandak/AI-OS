"""Bridge: IngestionEnvelope -> Neo4j, via the ported KGStore.

Maps approved `RelationProposal`s to `KGEdge` upserts and approved ("current")
`ClaimProposal`s to temporal `Claim` upserts. Never auto-merges identities
(R4 / ground rule 4): ambiguous label matches are filed as an
`IdentityProposal` for human review while the already resolved/created node is
still used for the write.

Highlight_id (T33): the parse step splits a document into ordered highlights
before extraction, and each highlight gets its own envelope. So one envelope
maps 1:1 onto one real highlight, identified by `(source_record_id,
highlight_index)`. `KGStore` and the graph schema already key on
`highlight_id`, so nothing about the graph shape changes -- only the
granularity of what vouches for a node, edge, or claim.

Purge on supersede is document-scoped, not highlight-scoped: the predecessor
document was parsed into N highlights, so all N stop vouching at once.
`supersedes_highlight_count` on the envelope says how many, and their ids
regenerate deterministically from the predecessor's `source_record_id`.
"""

from __future__ import annotations

import logging
import uuid
from typing import Optional

from ingestion.ids import NAMESPACE as _NAMESPACE, highlight_id_for_highlight
from ingestion.kg.kg_store import CycleDetected, KGStore
from ingestion.kg.models import (
    Claim,
    ClaimStatus,
    CycleConflict,
    IdentityProposal,
    IdentityRelation,
    KGEdge,
    KGNode,
    ReviewStatus,
)
from ingestion.models import IngestionEnvelope

logger = logging.getLogger(__name__)

# `_NAMESPACE` and `highlight_id_for_highlight` live in `ingestion.ids` (single
# source of truth for deterministic ids). Re-exported here so existing imports
# (`from ingestion.consumers.kg_consumer import highlight_id_for_highlight`) work.
__all__ = ["KGConsumer", "highlight_id_for_highlight"]


class KGConsumer:
    """`EnvelopeConsumer` (see `ingestion.dispatch`) for the `kg` target."""

    target = "kg"

    def __init__(self, store: KGStore, *, proposed_by: str = "kg_consumer") -> None:
        self.store = store
        self.proposed_by = proposed_by

    def consume(self, envelope: IngestionEnvelope) -> str:
        highlight_id = highlight_id_for_highlight(
            envelope.source_record_id, envelope.highlight_index
        )

        if envelope.supersedes_record_id:
            # Every highlight of the superseded document stops vouching, not
            # just the one at this index. Purging is idempotent and the old and
            # new id sets are disjoint (they derive from different
            # source_record_ids), so a sibling envelope repeating this purge
            # cannot strip a contribution belonging to a live highlight.
            for index in range(envelope.supersedes_highlight_count or 0):
                self.store.purge_contributions(
                    highlight_id_for_highlight(envelope.supersedes_record_id, index)
                )

        node_cache: dict[tuple[str, str], KGNode] = {}
        skipped = 0

        def resolve(label: str, domain: Optional[str]) -> KGNode:
            key = (label, domain or "general")
            if key in node_cache:
                return node_cache[key]
            node, candidates, _created = self.store.resolve_or_create_node(
                label, domain=domain or "general", highlight_id=highlight_id,
            )
            for candidate in candidates:
                if candidate.deterministic or candidate.node.id == node.id:
                    continue
                self.store.submit_identity_proposal(
                    IdentityProposal(
                        id=str(
                            uuid.uuid5(_NAMESPACE, f"identity:{node.id}:{candidate.node.id}")
                        ),
                        source_id=node.id,
                        target_id=candidate.node.id,
                        relation=IdentityRelation.ALIAS_OF,
                        rationale=candidate.explanation,
                        provenance=[envelope.envelope_id],
                        status=ReviewStatus.PENDING,
                        proposed_by=self.proposed_by,
                    )
                )
            node_cache[key] = node
            return node

        batched_edges: list[KGEdge] = []
        for relation in envelope.semantic.relations:
            if relation.status != "approved":
                continue
            if not relation.evidence:
                logger.warning(
                    "[KGConsumer] skipping relation %r — no evidence pointer",
                    relation.proposal_id,
                )
                skipped += 1
                continue
            subject = resolve(relation.subject, relation.domain)
            obj = resolve(relation.object, relation.domain)
            edge = KGEdge(
                id=str(uuid.uuid5(_NAMESPACE, f"edge:{relation.proposal_id}")),
                subject_id=subject.id,
                subject_name=relation.subject,
                subject_domain=relation.domain,
                relation=relation.predicate,
                object_id=obj.id,
                object_name=relation.object,
                object_domain=relation.domain,
                source=envelope.source_record_id,
                source_hash=envelope.normalized_content_hash,
                highlight_id=highlight_id,
            )
            if relation.hierarchical:
                try:
                    self.store.upsert_edge(edge, check_cycle=True)
                except CycleDetected:
                    logger.warning(
                        "[KGConsumer] relation %r diverted — %r -> %r would "
                        "close a cycle; filed as CycleConflict for review, not written",
                        relation.proposal_id, relation.subject, relation.object,
                    )
                    self.store.submit_cycle_conflict(
                        CycleConflict(
                            id=str(
                                uuid.uuid5(_NAMESPACE, f"cycle_conflict:{relation.proposal_id}")
                            ),
                            subject_id=subject.id,
                            subject_name=relation.subject,
                            predicate=relation.predicate,
                            object_id=obj.id,
                            object_name=relation.object,
                            rationale=(
                                f"Adding {relation.subject!r} -[{relation.predicate}]-> "
                                f"{relation.object!r} would close a cycle in a relation "
                                "explicitly marked hierarchical."
                            ),
                            provenance=[envelope.envelope_id],
                            status=ReviewStatus.PENDING,
                            proposed_by=self.proposed_by,
                        )
                    )
                    skipped += 1
            else:
                batched_edges.append(edge)

        if batched_edges:
            self.store.upsert_edge_batch(batched_edges)

        for claim in envelope.semantic.claims:
            if claim.status != "current":
                continue
            if not claim.concept_labels:
                logger.warning(
                    "[KGConsumer] skipping claim %r — no concept_labels to attach to",
                    claim.proposal_id,
                )
                skipped += 1
                continue
            if not claim.evidence:
                logger.warning(
                    "[KGConsumer] skipping claim %r — no evidence pointer",
                    claim.proposal_id,
                )
                skipped += 1
                continue
            evidence_text = claim.evidence[0].quote
            for label in claim.concept_labels:
                subject = resolve(label, None)
                graph_claim = Claim(
                    id=str(uuid.uuid5(_NAMESPACE, f"claim:{claim.proposal_id}:{label}")),
                    subject_id=subject.id,
                    # ClaimProposal carries free-text `text` + `concept_labels`,
                    # not a structured (subject, predicate, object) triple —
                    # that structure lives in RelationProposal instead. ASSERTS
                    # is a fixed sentinel predicate for "this concept has this
                    # claim text asserted about it." Revisit if/when claims gain
                    # real structure (MASTER_PLAN §8 OPEN #15, atomic facts).
                    predicate="ASSERTS",
                    object_text=claim.text,
                    source=envelope.source_record_id,
                    source_version=str(envelope.version),
                    observed_at=claim.observed_at,
                    valid_from=claim.valid_from,
                    valid_to=claim.valid_to,
                    confidence=claim.model_confidence,
                    highlight_id=highlight_id,
                    evidence_text=evidence_text,
                    status=ClaimStatus.CURRENT,
                )
                self.store.upsert_claim(graph_claim)

        if skipped:
            logger.info(
                "[KGConsumer] envelope %r: %d proposal(s) skipped (see warnings above)",
                envelope.envelope_id, skipped,
            )
        return f"kg:{envelope.envelope_id}"
