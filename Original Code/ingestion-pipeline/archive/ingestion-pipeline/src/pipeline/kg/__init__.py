"""knowledge_graph - Neo4j-backed knowledge graph for Raw Data downstream processing.

Typical usage::

    from knowledge_graph import KGStore
    from pipeline.kg.run import run_kg

    store = KGStore()  # picks up NEO4J_* env vars

    # End-to-end flow:
    # 1. Capture bronze data into Raw Data/bronze via the Raw Data pipeline.
    # 2. Run knowledge_graph.run.run_kg() to extract triplets and write Neo4j edges.

    hits = store.neighbors("interest_rates", direction="outgoing")
"""

import logging

from pipeline.kg.extraction import extract_triplets
from pipeline.kg.kg_store import CycleDetected, KGStore
from pipeline.kg.identity import external_id_key, normalize_label
from pipeline.kg.models import (
    APPLIES_TO,
    CAUSES,
    COMPONENT_OF,
    CONTRASTS_WITH,
    DEFINED_BY,
    IS_A,
    PART_OF,
    PREREQUISITE_OF,
    RELATES_TO,
    GraphHit,
    Claim,
    ClaimStatus,
    IdentityLink,
    IdentityProposal,
    IdentityRelation,
    IngestDocument,
    IngestResult,
    KGEdge,
    KGNode,
    MatchCandidate,
    ReviewStatus,
    Triplet,
)
from pipeline.kg.prompts import EXTRACT_TRIPLETS, EXTRACT_TRIPLETS_RETRY_SUFFIX


def configure_logging(level: int = logging.INFO) -> None:
    """Enable console logging for the knowledge_graph package."""
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    pkg_logger = logging.getLogger("pipeline.kg")
    pkg_logger.setLevel(level)
    if not pkg_logger.handlers:
        pkg_logger.addHandler(handler)


__all__ = [
    "configure_logging",
    "KGStore",
    "CycleDetected",
    "extract_triplets",
    "KGNode",
    "KGEdge",
    "Triplet",
    "IngestDocument",
    "IngestResult",
    "GraphHit",
    "IdentityLink",
    "IdentityProposal",
    "IdentityRelation",
    "ReviewStatus",
    "MatchCandidate",
    "Claim",
    "ClaimStatus",
    "normalize_label",
    "external_id_key",
    "EXTRACT_TRIPLETS",
    "EXTRACT_TRIPLETS_RETRY_SUFFIX",
    "PREREQUISITE_OF",
    "COMPONENT_OF",
    "CONTRASTS_WITH",
    "APPLIES_TO",
    "RELATES_TO",
    "IS_A",
    "PART_OF",
    "CAUSES",
    "DEFINED_BY",
]
