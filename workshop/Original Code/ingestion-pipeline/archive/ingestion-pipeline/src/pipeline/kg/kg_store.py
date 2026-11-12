"""Knowledge graph store backed by Neo4j.

Architecture:
- Nodes are Neo4j :Concept nodes, keyed by a stable id property.
- Edges are :KG_EDGE relationships with a `relation` property (free-form string).
- MERGE ensures idempotency on (subject_id, relation, object_id).
- All imports of the `neo4j` package are lazy; the store degrades gracefully
  when Neo4j is absent or unreachable (writes no-op, reads return empty).

Connection config (in priority order):
  1. Constructor kwargs
  2. Environment variables: NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD, NEO4J_DATABASE
  3. Defaults: bolt://localhost:7687, neo4j, neo4j, neo4j

Cycle detection (opt-in):
  Pass hierarchical_relations=frozenset({"PREREQUISITE_OF", "COMPONENT_OF"}) to
  raise CycleDetected before adding an edge that would introduce a cycle in those
  relation types. Disabled by default so the store works for any graph shape.
"""

import logging
import os
import uuid
from datetime import datetime
from typing import Any, Optional

from pipeline.kg.identity import external_id_key, normalize_label
from pipeline.kg.models import (
    Claim,
    ClaimStatus,
    GraphHit,
    IdentityLink,
    IdentityProposal,
    IdentityRelation,
    KGEdge,
    KGNode,
    MatchCandidate,
    ReviewStatus,
)

logger = logging.getLogger(__name__)

_DEFAULT_DB = "neo4j"
_UPSERT_EDGE_ROWS_CYPHER = """
UNWIND $rows AS row
MERGE (a:Concept {id: row.subject_id})
ON CREATE SET a.canonical_name = coalesce(row.subject_name, row.subject_id),
              a.labels = [coalesce(row.subject_name, row.subject_id)],
              a.normalized_name = row.subject_normalized_name,
              a.domain = coalesce(row.subject_domain, "general"),
              a.created_at = row.created_at
ON MATCH SET  a.canonical_name = CASE
                    WHEN a.canonical_name IS NULL OR a.canonical_name = ""
                    THEN coalesce(row.subject_name, row.subject_id)
                    ELSE a.canonical_name
                END,
              a.labels = CASE
                    WHEN coalesce(row.subject_name, row.subject_id) IN coalesce(a.labels, []) THEN a.labels
                    ELSE coalesce(a.labels, []) + coalesce(row.subject_name, row.subject_id)
                END,
              a.normalized_name = coalesce(a.normalized_name, row.subject_normalized_name),
              a.domain = coalesce(a.domain, row.subject_domain, "general")
MERGE (b:Concept {id: row.object_id})
ON CREATE SET b.canonical_name = coalesce(row.object_name, row.object_id),
              b.labels = [coalesce(row.object_name, row.object_id)],
              b.normalized_name = row.object_normalized_name,
              b.domain = coalesce(row.object_domain, "general"),
              b.created_at = row.created_at
ON MATCH SET  b.canonical_name = CASE
                    WHEN b.canonical_name IS NULL OR b.canonical_name = ""
                    THEN coalesce(row.object_name, row.object_id)
                    ELSE b.canonical_name
                END,
              b.labels = CASE
                    WHEN coalesce(row.object_name, row.object_id) IN coalesce(b.labels, []) THEN b.labels
                    ELSE coalesce(b.labels, []) + coalesce(row.object_name, row.object_id)
                END,
              b.normalized_name = coalesce(b.normalized_name, row.object_normalized_name),
              b.domain = coalesce(b.domain, row.object_domain, "general")
MERGE (a)-[r:KG_EDGE {relation: row.relation}]->(b)
ON CREATE SET r.id = row.id,
              r.source = row.source,
              r.source_hash = row.source_hash,
              r.sources = CASE WHEN row.source IS NULL THEN [] ELSE [row.source] END,
              r.source_hashes = CASE WHEN row.source_hash IS NULL THEN [] ELSE [row.source_hash] END,
              r.created_at = row.created_at
ON MATCH SET  r.source = coalesce(r.source, row.source),
              r.source_hash = coalesce(r.source_hash, row.source_hash),
              r.sources = CASE
                    WHEN row.source IS NULL OR row.source IN coalesce(r.sources, []) THEN coalesce(r.sources, [])
                    ELSE coalesce(r.sources, []) + row.source END,
              r.source_hashes = CASE
                    WHEN row.source_hash IS NULL OR row.source_hash IN coalesce(r.source_hashes, []) THEN coalesce(r.source_hashes, [])
                    ELSE coalesce(r.source_hashes, []) + row.source_hash END
"""


class CycleDetected(Exception):
    """Raised when adding a hierarchical edge would create a cycle."""


class KGStore:
    """Knowledge graph store backed by Neo4j.

    Parameters
    ----------
    uri:
        Neo4j connection URI (bolt://localhost:7687 by default).
    user:
        Neo4j username.
    password:
        Neo4j password.
    database:
        Neo4j database name.
    hierarchical_relations:
        Set of relation strings that must form a DAG. If an edge whose relation
        is in this set would create a cycle, CycleDetected is raised. Pass an
        empty set (default) to skip cycle detection entirely.
    """

    def __init__(
        self,
        uri: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        database: Optional[str] = None,
        hierarchical_relations: frozenset[str] = frozenset(),
    ) -> None:
        self._uri = uri or os.getenv("NEO4J_URI", "bolt://localhost:7687")
        self._user = user or os.getenv("NEO4J_USERNAME", "neo4j")
        self._password = password or os.getenv("NEO4J_PASSWORD", "neo4j")
        self._database = database or os.getenv("NEO4J_DATABASE", _DEFAULT_DB)
        self.hierarchical_relations = hierarchical_relations
        self._driver: Any = None
        self._available: Optional[bool] = None
        self._constraints_ready = False

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def _get_driver(self) -> Any:
        if self._driver is not None:
            return self._driver
        logger.info("[KGStore] Connecting to Neo4j at %s (db=%s, user=%s)", self._uri, self._database, self._user)
        try:
            from neo4j import GraphDatabase  # type: ignore[import]
            driver = GraphDatabase.driver(
                self._uri, auth=(self._user, self._password)
            )
            driver.verify_connectivity()
            self._driver = driver
            self._available = True
            logger.info("[KGStore] Connected to Neo4j successfully")
            self._ensure_constraints()
            return self._driver
        except ImportError:
            logger.error(
                "[KGStore] MISSING DEPENDENCY — neo4j package not installed. "
                "Fix: pip install neo4j"
            )
            self._available = False
            return None
        except Exception as exc:
            if "driver" in locals():
                try:
                    driver.close()
                except Exception:
                    pass
            self._driver = None
            logger.error(
                "[KGStore] CANNOT CONNECT — Neo4j unreachable at %s. "
                "All reads/writes will no-op until the database is reachable. "
                "Error: %s",
                self._uri,
                exc,
                exc_info=True,
            )
            self._available = False
            return None

    def _ensure_constraints(self) -> None:
        if self._constraints_ready or self._driver is None:
            return
        logger.info("[KGStore] Ensuring schema constraints on :Concept(id)")
        try:
            self._driver.execute_query(
                "CREATE CONSTRAINT concept_id_unique IF NOT EXISTS "
                "FOR (c:Concept) REQUIRE c.id IS UNIQUE",
                database_=self._database,
            )
            self._driver.execute_query(
                "CREATE CONSTRAINT claim_id_unique IF NOT EXISTS "
                "FOR (c:Claim) REQUIRE c.id IS UNIQUE",
                database_=self._database,
            )
            self._driver.execute_query(
                "CREATE CONSTRAINT identity_proposal_id_unique IF NOT EXISTS "
                "FOR (p:IdentityProposal) REQUIRE p.id IS UNIQUE",
                database_=self._database,
            )
            self._constraints_ready = True
            logger.info("[KGStore] Schema constraints ready")
        except Exception as exc:
            logger.warning(
                "[KGStore] Could not create Neo4j constraints — "
                "duplicate nodes may appear. Error: %s",
                exc,
                exc_info=True,
            )

    def is_available(self) -> bool:
        """Return True if Neo4j is reachable and the driver is connected."""
        return self._get_driver() is not None

    def close(self) -> None:
        """Close the driver connection."""
        if self._driver is not None:
            self._driver.close()
            self._driver = None
            self._available = None

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    def execute_write(
        self,
        cypher: str,
        rows: Optional[list[dict[str, Any]]] = None,
        **params: Any,
    ) -> tuple[bool, Optional[str]]:
        """Execute a write query against Neo4j and return success + error text."""
        driver = self._get_driver()
        if driver is None:
            return False, "Neo4j unavailable"
        try:
            query_params = dict(params)
            if rows is not None:
                query_params["rows"] = rows
            driver.execute_query(cypher, database_=self._database, **query_params)
            return True, None
        except Exception as exc:
            logger.error("[KGStore] execute_write FAILED — %s", exc, exc_info=True)
            return False, str(exc)

    def upsert_node(self, node: KGNode) -> None:
        """Persist or update a concept node. Idempotent on node.id."""
        driver = self._get_driver()
        if driver is None:
            logger.warning("[KGStore] upsert_node skipped — Neo4j unavailable (node=%r)", node.id)
            return
        logger.debug("[KGStore] upsert_node id=%r name=%r domain=%r", node.id, node.canonical_name, node.domain)
        try:
            driver.execute_query(
                """
                MERGE (c:Concept {id: $id})
                ON CREATE SET c.canonical_name = $name,
                              c.labels = [$name],
                              c.domain = $domain,
                              c.fields = $fields,
                              c.external_ids = $external_ids,
                              c.normalized_name = $normalized_name,
                              c.created_at = $created_at
                ON MATCH SET  c.canonical_name = CASE
                                  WHEN c.canonical_name IS NULL OR c.canonical_name = ""
                                  THEN $name ELSE c.canonical_name END,
                              c.labels = CASE WHEN $name IN coalesce(c.labels, [])
                                  THEN c.labels ELSE coalesce(c.labels, []) + $name END,
                              c.domain = coalesce(c.domain, $domain),
                              c.fields = reduce(acc = coalesce(c.fields, []), x IN $fields |
                                  CASE WHEN x IN acc THEN acc ELSE acc + x END),
                              c.external_ids = reduce(acc = coalesce(c.external_ids, []), x IN $external_ids |
                                  CASE WHEN x IN acc THEN acc ELSE acc + x END),
                              c.normalized_name = $normalized_name
                """,
                id=node.id,
                name=node.canonical_name,
                domain=node.domain,
                fields=node.fields,
                external_ids=[external_id_key(k, v) for k, v in node.external_ids.items()],
                normalized_name=normalize_label(node.canonical_name),
                created_at=node.created_at.isoformat(),
                database_=self._database,
            )
        except Exception as exc:
            logger.error(
                "[KGStore] upsert_node FAILED id=%r name=%r — %s",
                node.id, node.canonical_name, exc,
                exc_info=True,
            )

    def submit_identity_proposal(self, proposal: IdentityProposal) -> None:
        """Persist a proposal without changing identity or retrieval behavior."""
        ok, error = self.execute_write(
            """
            MATCH (a:Concept {id: $source_id}), (b:Concept {id: $target_id})
            MERGE (p:IdentityProposal {id: $id})
            ON CREATE SET p.relation = $relation, p.rationale = $rationale,
                          p.provenance = $provenance, p.status = $status,
                          p.proposed_by = $proposed_by, p.created_at = $created_at
            MERGE (p)-[:PROPOSES_SOURCE]->(a)
            MERGE (p)-[:PROPOSES_TARGET]->(b)
            """,
            id=proposal.id,
            source_id=proposal.source_id,
            target_id=proposal.target_id,
            relation=proposal.relation.value,
            rationale=proposal.rationale,
            provenance=proposal.provenance,
            status=proposal.status.value,
            proposed_by=proposal.proposed_by,
            created_at=proposal.created_at.isoformat(),
        )
        if not ok:
            raise RuntimeError(error or "failed to submit identity proposal")

    def upsert_identity_link(self, link: IdentityLink) -> None:
        """Write a reviewed link while preserving both original concept nodes."""
        if link.status == ReviewStatus.APPROVED and (
            not link.reviewed_by or not link.provenance
        ):
            raise ValueError("approved identity links require reviewer and provenance")
        relation = link.relation.value
        if relation not in {item.value for item in IdentityRelation}:
            raise ValueError(f"unsupported identity relation: {relation}")
        cypher = f"""
            MATCH (a:Concept {{id: $source_id}}), (b:Concept {{id: $target_id}})
            MERGE (a)-[r:{relation} {{id: $id}}]->(b)
            ON CREATE SET r.status = $status, r.provenance = $provenance,
                          r.field = $field, r.valid_from = $valid_from,
                          r.valid_to = $valid_to, r.created_at = $created_at,
                          r.reviewed_at = $reviewed_at, r.reviewed_by = $reviewed_by
            ON MATCH SET r.status = $status, r.provenance = $provenance,
                         r.field = $field, r.valid_from = $valid_from,
                         r.valid_to = $valid_to, r.reviewed_at = $reviewed_at,
                         r.reviewed_by = $reviewed_by
        """
        ok, error = self.execute_write(
            cypher,
            id=link.id,
            source_id=link.source_id,
            target_id=link.target_id,
            status=link.status.value,
            provenance=link.provenance,
            field=link.field,
            valid_from=link.valid_from.isoformat() if link.valid_from else None,
            valid_to=link.valid_to.isoformat() if link.valid_to else None,
            created_at=link.created_at.isoformat(),
            reviewed_at=link.reviewed_at.isoformat() if link.reviewed_at else None,
            reviewed_by=link.reviewed_by,
        )
        if not ok:
            raise RuntimeError(error or "failed to write identity link")

    def review_identity_proposal(
        self,
        proposal_id: str,
        status: ReviewStatus,
        reviewer: str,
    ) -> None:
        """Review a proposal and materialize its link only when approved."""
        if status == ReviewStatus.PENDING:
            raise ValueError("a review must approve or reject the proposal")
        relation_cases = " ".join(
            f"WHEN p.relation = '{relation.value}' THEN '{relation.value}'"
            for relation in IdentityRelation
        )
        # APOC is intentionally not required. The three safe relationship
        # types are handled with conditional FOREACH clauses.
        cypher = f"""
            MATCH (p:IdentityProposal {{id: $id}})
                  -[:PROPOSES_SOURCE]->(a:Concept)
            MATCH (p)-[:PROPOSES_TARGET]->(b:Concept)
            SET p.status = $status, p.reviewed_by = $reviewer,
                p.reviewed_at = $reviewed_at
            WITH p, a, b, CASE {relation_cases} ELSE null END AS safe_relation
            FOREACH (_ IN CASE WHEN $status = 'approved' AND safe_relation = 'ALIAS_OF' THEN [1] ELSE [] END |
                MERGE (a)-[r:ALIAS_OF {{id: p.id}}]->(b)
                SET r.status = 'approved', r.provenance = p.provenance,
                    r.created_at = p.created_at, r.reviewed_at = $reviewed_at,
                    r.reviewed_by = $reviewer)
            FOREACH (_ IN CASE WHEN $status = 'approved' AND safe_relation = 'SAME_AS' THEN [1] ELSE [] END |
                MERGE (a)-[r:SAME_AS {{id: p.id}}]->(b)
                SET r.status = 'approved', r.provenance = p.provenance,
                    r.created_at = p.created_at, r.reviewed_at = $reviewed_at,
                    r.reviewed_by = $reviewer)
            FOREACH (_ IN CASE WHEN $status = 'approved' AND safe_relation = 'RELATED_TO' THEN [1] ELSE [] END |
                MERGE (a)-[r:RELATED_TO {{id: p.id}}]->(b)
                SET r.status = 'approved', r.provenance = p.provenance,
                    r.created_at = p.created_at, r.reviewed_at = $reviewed_at,
                    r.reviewed_by = $reviewer)
        """
        ok, error = self.execute_write(
            cypher,
            id=proposal_id,
            status=status.value,
            reviewer=reviewer,
            reviewed_at=datetime.utcnow().isoformat(),
        )
        if not ok:
            raise RuntimeError(error or "failed to review identity proposal")

    def upsert_claim(self, claim: Claim) -> None:
        """Persist an assertion as a node so later corrections never erase it."""
        ok, error = self.execute_write(
            """
            MATCH (s:Concept {id: $subject_id})
            MERGE (c:Claim {id: $id})
            ON CREATE SET c.predicate = $predicate, c.object_id = $object_id,
                          c.object_text = $object_text, c.source = $source,
                          c.source_version = $source_version, c.fields = $fields,
                          c.observed_at = $observed_at, c.ingested_at = $ingested_at,
                          c.valid_from = $valid_from, c.valid_to = $valid_to,
                          c.confidence = $confidence,
                          c.evidence_quality = $evidence_quality, c.status = $status
            ON MATCH SET c.status = $status, c.valid_to = $valid_to
            MERGE (s)-[:ASSERTS]->(c)
            WITH c
            OPTIONAL MATCH (o:Concept {id: $object_id})
            FOREACH (_ IN CASE WHEN o IS NULL THEN [] ELSE [1] END |
                MERGE (c)-[:CLAIM_OBJECT]->(o))
            """,
            id=claim.id,
            subject_id=claim.subject_id,
            predicate=claim.predicate,
            object_id=claim.object_id,
            object_text=claim.object_text,
            source=claim.source,
            source_version=claim.source_version,
            fields=claim.fields,
            observed_at=claim.observed_at.isoformat() if claim.observed_at else None,
            ingested_at=claim.ingested_at.isoformat(),
            valid_from=claim.valid_from.isoformat() if claim.valid_from else None,
            valid_to=claim.valid_to.isoformat() if claim.valid_to else None,
            confidence=claim.confidence,
            evidence_quality=claim.evidence_quality,
            status=claim.status.value,
        )
        if not ok:
            raise RuntimeError(error or "failed to write claim")

    def link_claims(
        self,
        newer_claim_id: str,
        relation: str,
        older_claim_id: str,
        provenance: Optional[str] = None,
    ) -> None:
        """Link claim history using SUPERSEDES, CONTRADICTS, or SUPPORTS."""
        allowed = {"SUPERSEDES", "CONTRADICTS", "SUPPORTS"}
        relation = relation.upper()
        if relation not in allowed:
            raise ValueError(f"claim relation must be one of {sorted(allowed)}")
        cypher = f"""
            MATCH (newer:Claim {{id: $newer_id}}), (older:Claim {{id: $older_id}})
            MERGE (newer)-[r:{relation}]->(older)
            ON CREATE SET r.provenance = $provenance,
                          r.created_at = $created_at
        """
        ok, error = self.execute_write(
            cypher,
            newer_id=newer_claim_id,
            older_id=older_claim_id,
            provenance=provenance,
            created_at=datetime.utcnow().isoformat(),
        )
        if not ok:
            raise RuntimeError(error or "failed to link claims")
    def upsert_edge(self, edge: KGEdge) -> None:
        """Persist a directed edge. Idempotent on (subject_id, relation, object_id).

        Creates the subject and object :Concept nodes if they don't exist.
        Raises CycleDetected if the edge is a hierarchical relation that would
        create a cycle (only when hierarchical_relations is configured).
        """
        driver = self._get_driver()
        if driver is None:
            logger.warning("[KGStore] upsert_edge skipped — Neo4j unavailable (edge=%r)", edge.id)
            return
        logger.debug(
            "[KGStore] upsert_edge %r -[%s]-> %r",
            edge.subject_id, edge.relation, edge.object_id,
        )
        if self.hierarchical_relations and edge.relation in self.hierarchical_relations:
            logger.debug("[KGStore] Checking cycle for hierarchical relation %r", edge.relation)
            self._check_cycle(edge.subject_id, edge.object_id)
        succeeded, error = self.execute_write(_UPSERT_EDGE_ROWS_CYPHER, rows=[self._edge_to_row(edge)])
        if not succeeded:
            logger.error(
                "[KGStore] upsert_edge FAILED %r -[%s]-> %r — %s",
                edge.subject_id, edge.relation, edge.object_id, error,
            )

    def upsert_edge_batch(self, edges: list[KGEdge]) -> None:
        """Batch-upsert a list of edges in a single query.

        More efficient than calling upsert_edge in a loop. Does NOT run cycle
        detection — use upsert_edge for edges that need it.
        """
        driver = self._get_driver()
        if driver is None:
            logger.warning("[KGStore] upsert_edge_batch skipped — Neo4j unavailable (%d edges)", len(edges))
            return
        if not edges:
            logger.debug("[KGStore] upsert_edge_batch called with empty list — nothing to do")
            return
        logger.info("[KGStore] upsert_edge_batch writing %d edges", len(edges))
        rows = [self._edge_to_row(edge) for edge in edges]
        succeeded, error = self.execute_write(_UPSERT_EDGE_ROWS_CYPHER, rows=rows)
        if succeeded:
            logger.info("[KGStore] upsert_edge_batch OK — %d edges written", len(edges))
        else:
            logger.error(
                "[KGStore] upsert_edge_batch FAILED (%d edges) — %s",
                len(edges), error,
            )

    # ------------------------------------------------------------------
    # Cycle detection
    # ------------------------------------------------------------------

    def _check_cycle(self, subject_id: str, object_id: str) -> None:
        """Raise CycleDetected if (subject → object) would create a cycle.

        Uses shortestPath in Neo4j to detect an existing path from object back
        to subject. If one exists, adding subject→object would close the loop.
        """
        driver = self._get_driver()
        if driver is None:
            return
        logger.debug("[KGStore] Cycle check: %r → %r", subject_id, object_id)
        try:
            from neo4j import RoutingControl  # type: ignore[import]
            records, _, _ = driver.execute_query(
                """
                MATCH (from:Concept {id: $from_id}), (to:Concept {id: $to_id})
                OPTIONAL MATCH path = shortestPath((to)-[:KG_EDGE*]->(from))
                RETURN path IS NOT NULL AS would_cycle
                """,
                from_id=subject_id,
                to_id=object_id,
                database_=self._database,
                routing_=RoutingControl.READ,
            )
            if records and records[0]["would_cycle"]:
                logger.warning(
                    "[KGStore] CYCLE DETECTED: adding %r → %r would close a loop — edge rejected",
                    subject_id, object_id,
                )
                raise CycleDetected(
                    f"Adding edge {subject_id} → {object_id} would create a cycle."
                )
            logger.debug("[KGStore] No cycle found for %r → %r", subject_id, object_id)
        except CycleDetected:
            raise
        except Exception as exc:
            logger.warning(
                "[KGStore] Cycle detection query FAILED for %r → %r — proceeding without check. Error: %s",
                subject_id, object_id, exc,
                exc_info=True,
            )

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def get_node(self, node_id: str) -> Optional[KGNode]:
        """Return a KGNode by id, or None if not found."""
        driver = self._get_driver()
        if driver is None:
            logger.warning("[KGStore] get_node skipped — Neo4j unavailable (id=%r)", node_id)
            return None
        logger.debug("[KGStore] get_node id=%r", node_id)
        try:
            records, _, _ = driver.execute_query(
                "MATCH (c:Concept {id: $id}) "
                "RETURN c.id AS id, c.canonical_name AS name, "
                "c.domain AS domain, coalesce(c.fields, []) AS fields, "
                "coalesce(c.external_ids, []) AS external_ids, c.created_at AS created_at",
                id=node_id,
                database_=self._database,
            )
            if not records:
                logger.debug("[KGStore] get_node id=%r → not found", node_id)
                return None
            r = records[0]
            node = KGNode(
                id=r["id"],
                canonical_name=r["name"] or "",
                domain=r["domain"] or "general",
                fields=list(r.get("fields") or []),
                external_ids=self._external_ids_from_keys(r.get("external_ids") or []),
                created_at=(
                    datetime.fromisoformat(r["created_at"])
                    if r["created_at"]
                    else datetime.utcnow()
                ),
            )
            logger.debug("[KGStore] get_node id=%r → %r", node_id, node.canonical_name)
            return node
        except Exception as exc:
            logger.error("[KGStore] get_node FAILED id=%r — %s", node_id, exc, exc_info=True)
            return None

    def search_by_name(self, query: str, limit: int = 20) -> list[GraphHit]:
        """Return nodes whose canonical_name contains the query substring."""
        driver = self._get_driver()
        if driver is None:
            return []

        q = query.strip()
        if not q:
            return []

        logger.debug("[KGStore] search_by_name query=%r limit=%d", q, limit)
        try:
            records, _, _ = driver.execute_query(
                """
                MATCH (c:Concept)
                WHERE toLower(c.canonical_name) CONTAINS toLower($q)
                RETURN c.id AS id, c.canonical_name AS name, c.domain AS domain
                LIMIT $limit
                """,
                q=q,
                limit=limit,
                database_=self._database,
            )
            hits = [
                GraphHit(id=r["id"], canonical_name=r["name"] or "", domain=r["domain"] or "general")
                for r in records
            ]
            logger.debug("[KGStore] search_by_name query=%r → %d result(s)", q, len(hits))
            return hits
        except Exception as exc:
            logger.error("[KGStore] search_by_name FAILED query=%r — %s", q, exc, exc_info=True)
            return []

    def find_identity_candidates(
        self,
        label: str,
        *,
        domain: Optional[str] = None,
        node_id: Optional[str] = None,
        external_ids: Optional[dict[str, str]] = None,
        limit: int = 20,
    ) -> list[MatchCandidate]:
        """Run the deterministic/lexical resolver stages without deciding identity.

        Stable node and external-ID matches are marked deterministic. Exact
        normalized labels and lexical matches remain review candidates because
        lexical equality is not a semantic identity guarantee.
        """
        driver = self._get_driver()
        normalized = normalize_label(label)
        if driver is None or not normalized:
            return []
        ext_keys = [external_id_key(k, v) for k, v in (external_ids or {}).items()]
        try:
            records, _, _ = driver.execute_query(
                """
                MATCH (c:Concept)
                WHERE ($node_id IS NOT NULL AND c.id = $node_id)
                   OR (size($external_ids) > 0 AND any(x IN $external_ids WHERE x IN coalesce(c.external_ids, [])))
                   OR ((c.normalized_name = $normalized
                        OR toLower(trim(c.canonical_name)) = toLower(trim($label)))
                       AND ($domain IS NULL OR c.domain = $domain OR c.domain = 'general'))
                   OR c.normalized_name CONTAINS $normalized
                   OR $normalized CONTAINS c.normalized_name
                WITH c,
                     CASE
                       WHEN $node_id IS NOT NULL AND c.id = $node_id THEN 'stable_id'
                       WHEN size($external_ids) > 0 AND any(x IN $external_ids WHERE x IN coalesce(c.external_ids, [])) THEN 'external_id'
                       WHEN c.normalized_name = $normalized
                         OR toLower(trim(c.canonical_name)) = toLower(trim($label))
                         THEN 'normalized_label'
                       ELSE 'lexical'
                     END AS match_type
                RETURN c.id AS id, c.canonical_name AS name, c.domain AS domain,
                       coalesce(c.fields, []) AS fields, match_type
                ORDER BY CASE match_type
                    WHEN 'stable_id' THEN 0 WHEN 'external_id' THEN 1
                    WHEN 'normalized_label' THEN 2 ELSE 3 END
                LIMIT $limit
                """,
                node_id=node_id,
                external_ids=ext_keys,
                normalized=normalized,
                label=label,
                domain=domain,
                limit=limit,
                database_=self._database,
            )
            scores = {"stable_id": 1.0, "external_id": 1.0, "normalized_label": 0.9, "lexical": 0.6}
            explanations = {
                "stable_id": "Exact stable KG identifier match.",
                "external_id": "Exact normalized external identifier match.",
                "normalized_label": "Exact lexical label in compatible context; review semantic identity.",
                "lexical": "Partial lexical similarity; use only as a proposal candidate.",
            }
            candidates = [
                MatchCandidate(
                    node=KGNode(
                        id=r["id"],
                        canonical_name=r["name"] or "",
                        domain=r["domain"] or "general",
                        fields=list(r.get("fields") or []),
                    ),
                    match_type=r["match_type"],
                    score=scores[r["match_type"]],
                    deterministic=r["match_type"] in {"stable_id", "external_id"},
                    explanation=explanations[r["match_type"]],
                )
                for r in records
            ]
            if node_id:
                known_ids = {candidate.node.id for candidate in candidates}
                for hit in self.identity_cluster(node_id):
                    if hit.id == node_id or hit.id in known_ids:
                        continue
                    candidates.append(
                        MatchCandidate(
                            node=KGNode(
                                id=hit.id,
                                canonical_name=hit.canonical_name,
                                domain=hit.domain,
                            ),
                            match_type="approved_identity_link",
                            score=1.0,
                            deterministic=True,
                            explanation="Connected by a reviewed, approved alias/same-as link.",
                        )
                    )
            return candidates
        except Exception as exc:
            logger.error("[KGStore] identity candidate lookup FAILED — %s", exc, exc_info=True)
            return []

    def resolve_or_create_node(
        self,
        canonical_name: str,
        *,
        domain: str = "general",
        node_id: Optional[str] = None,
        external_ids: Optional[dict[str, str]] = None,
        fields: Optional[list[str]] = None,
    ) -> tuple[KGNode, list[MatchCandidate], bool]:
        """Resolve only deterministic identity or create a new stable UUID node.

        Returns ``(node, candidates, created)``. Ambiguous label candidates are
        returned to the caller for proposal/review and are never auto-collapsed.
        """
        candidates = self.find_identity_candidates(
            canonical_name,
            domain=domain,
            node_id=node_id,
            external_ids=external_ids,
        )
        deterministic = next((candidate for candidate in candidates if candidate.deterministic), None)
        if deterministic:
            return deterministic.node, candidates, False
        node = KGNode(
            id=node_id or str(uuid.uuid4()),
            canonical_name=canonical_name,
            domain=domain,
            external_ids=external_ids or {},
            fields=fields or [],
        )
        self.upsert_node(node)
        return node, candidates, True

    def identity_cluster(
        self,
        node_id: str,
        *,
        as_of: Optional[datetime] = None,
    ) -> list[GraphHit]:
        """Return nodes joined by approved, currently-valid alias/same-as links."""
        driver = self._get_driver()
        if driver is None:
            return []
        instant = (as_of or datetime.utcnow()).isoformat()
        try:
            records, _, _ = driver.execute_query(
                """
                MATCH p=(root:Concept {id: $id})-[:ALIAS_OF|SAME_AS*0..]-(member:Concept)
                WHERE all(r IN relationships(p) WHERE r.status = 'approved'
                    AND (r.valid_from IS NULL OR datetime(r.valid_from) <= datetime($as_of))
                    AND (r.valid_to IS NULL OR datetime(r.valid_to) > datetime($as_of)))
                RETURN DISTINCT member.id AS id, member.canonical_name AS name,
                                member.domain AS domain
                """,
                id=node_id,
                as_of=instant,
                database_=self._database,
            )
            return [
                GraphHit(id=r["id"], canonical_name=r["name"] or "", domain=r["domain"] or "general")
                for r in records
            ]
        except Exception as exc:
            logger.error("[KGStore] identity_cluster FAILED id=%r — %s", node_id, exc, exc_info=True)
            return []

    def identity_expanded_edges(
        self,
        node_id: str,
        *,
        as_of: Optional[datetime] = None,
    ) -> list[KGEdge]:
        """Retrieve KG edges from every member while retaining original IDs."""
        cluster = self.identity_cluster(node_id, as_of=as_of)
        seen: set[str] = set()
        edges: list[KGEdge] = []
        for member in cluster:
            for edge in self.edges_for_node(member.id):
                key = edge.id or f"{edge.subject_id}:{edge.relation}:{edge.object_id}"
                if key not in seen:
                    seen.add(key)
                    edges.append(edge)
        return edges

    def identity_expansion_terms(
        self,
        node_id: str,
        *,
        as_of: Optional[datetime] = None,
    ) -> list[str]:
        """Return approved current labels for vector/keyword query expansion."""
        driver = self._get_driver()
        if driver is None:
            return []
        instant = (as_of or datetime.utcnow()).isoformat()
        try:
            records, _, _ = driver.execute_query(
                """
                MATCH p=(root:Concept {id: $id})-[:ALIAS_OF|SAME_AS*0..]-(member:Concept)
                WHERE all(r IN relationships(p) WHERE r.status = 'approved'
                    AND (r.valid_from IS NULL OR datetime(r.valid_from) <= datetime($as_of))
                    AND (r.valid_to IS NULL OR datetime(r.valid_to) > datetime($as_of)))
                UNWIND CASE WHEN size(coalesce(member.labels, [])) = 0
                    THEN [member.canonical_name] ELSE member.labels END AS label
                RETURN DISTINCT label ORDER BY label
                """,
                id=node_id,
                as_of=instant,
                database_=self._database,
            )
            return [str(r["label"]) for r in records if r.get("label")]
        except Exception as exc:
            logger.error("[KGStore] identity_expansion_terms FAILED id=%r — %s", node_id, exc, exc_info=True)
            return []

    def claims_for_identity(
        self,
        node_id: str,
        *,
        include_history: bool = False,
        as_of: Optional[datetime] = None,
    ) -> list[Claim]:
        """Retrieve claims across an identity cluster with source/time metadata."""
        driver = self._get_driver()
        if driver is None:
            return []
        instant = (as_of or datetime.utcnow()).isoformat()
        status_filter = "" if include_history else "AND c.status = 'current'"
        validity_filter = "" if include_history else """
                  AND (c.valid_from IS NULL OR datetime(c.valid_from) <= datetime($as_of))
                  AND (c.valid_to IS NULL OR datetime(c.valid_to) > datetime($as_of))
        """
        try:
            records, _, _ = driver.execute_query(
                f"""
                MATCH p=(root:Concept {{id: $id}})-[:ALIAS_OF|SAME_AS*0..]-(member:Concept)
                WHERE all(r IN relationships(p) WHERE r.status = 'approved'
                    AND (r.valid_from IS NULL OR datetime(r.valid_from) <= datetime($as_of))
                    AND (r.valid_to IS NULL OR datetime(r.valid_to) > datetime($as_of)))
                MATCH (member)-[:ASSERTS]->(c:Claim)
                WHERE true {validity_filter} {status_filter}
                RETURN DISTINCT c.id AS id, member.id AS subject_id,
                    c.predicate AS predicate, c.object_id AS object_id,
                    c.object_text AS object_text, c.source AS source,
                    c.source_version AS source_version, coalesce(c.fields, []) AS fields,
                    c.observed_at AS observed_at, c.ingested_at AS ingested_at,
                    c.valid_from AS valid_from, c.valid_to AS valid_to,
                    c.confidence AS confidence, c.evidence_quality AS evidence_quality,
                    c.status AS status
                ORDER BY coalesce(c.confidence, 0.0) DESC, c.ingested_at DESC
                """,
                id=node_id,
                as_of=instant,
                database_=self._database,
            )
            return [
                Claim(
                    id=r["id"],
                    subject_id=r["subject_id"],
                    predicate=r["predicate"],
                    object_id=r.get("object_id"),
                    object_text=r.get("object_text"),
                    source=r["source"],
                    source_version=r.get("source_version"),
                    fields=list(r.get("fields") or []),
                    observed_at=self._parse_datetime(r.get("observed_at")),
                    ingested_at=self._parse_datetime(r.get("ingested_at")) or datetime.utcnow(),
                    valid_from=self._parse_datetime(r.get("valid_from")),
                    valid_to=self._parse_datetime(r.get("valid_to")),
                    confidence=r.get("confidence"),
                    evidence_quality=r.get("evidence_quality"),
                    status=ClaimStatus(r.get("status") or ClaimStatus.CURRENT.value),
                )
                for r in records
            ]
        except Exception as exc:
            logger.error("[KGStore] claims_for_identity FAILED id=%r — %s", node_id, exc, exc_info=True)
            return []

    def neighbors(
        self,
        node_id: str,
        direction: str = "both",
        relation: Optional[str] = None,
    ) -> list[GraphHit]:
        """Return direct neighbor nodes of node_id.

        Parameters
        ----------
        direction:
            'outgoing' — nodes that node_id points to.
            'incoming' — nodes that point to node_id.
            'both'     — either direction.
        relation:
            If set, only edges with this relation string are traversed.
        """
        driver = self._get_driver()
        if driver is None:
            return []

        if direction == "outgoing":
            pattern = "(a:Concept {id: $id})-[r:KG_EDGE]->(b:Concept)"
        elif direction == "incoming":
            pattern = "(b:Concept)-[r:KG_EDGE]->(a:Concept {id: $id})"
        else:
            pattern = "(a:Concept {id: $id})-[r:KG_EDGE]-(b:Concept)"

        params: dict[str, Any] = {"id": node_id}
        cypher = f"MATCH {pattern}"
        if relation:
            cypher += " WHERE r.relation = $relation"
            params["relation"] = relation
        cypher += " RETURN DISTINCT b.id AS id, b.canonical_name AS name, b.domain AS domain"

        logger.debug("[KGStore] neighbors node_id=%r direction=%r relation=%r", node_id, direction, relation)
        try:
            records, _, _ = driver.execute_query(cypher, **params, database_=self._database)
            hits = [
                GraphHit(id=r["id"], canonical_name=r["name"] or "", domain=r["domain"] or "general")
                for r in records
            ]
            logger.debug("[KGStore] neighbors node_id=%r → %d result(s)", node_id, len(hits))
            return hits
        except Exception as exc:
            logger.error("[KGStore] neighbors FAILED node_id=%r — %s", node_id, exc, exc_info=True)
            return []

    def reachable(
        self,
        node_id: str,
        direction: str = "outgoing",
        max_hops: int = 10,
    ) -> list[GraphHit]:
        """Return all transitively reachable nodes from node_id.

        Parameters
        ----------
        direction:
            'outgoing' — follow edges away from node_id.
            'incoming' — follow edges toward node_id (ancestors).
        max_hops:
            Maximum path length to traverse.
        """
        driver = self._get_driver()
        if driver is None:
            return []

        if direction == "outgoing":
            cypher = (
                f"MATCH (a:Concept {{id: $id}})-[:KG_EDGE*1..{max_hops}]->(b:Concept) "
                "RETURN DISTINCT b.id AS id, b.canonical_name AS name, b.domain AS domain"
            )
        else:
            cypher = (
                f"MATCH (b:Concept)-[:KG_EDGE*1..{max_hops}]->(a:Concept {{id: $id}}) "
                "RETURN DISTINCT b.id AS id, b.canonical_name AS name, b.domain AS domain"
            )

        logger.debug("[KGStore] reachable node_id=%r direction=%r max_hops=%d", node_id, direction, max_hops)
        try:
            records, _, _ = driver.execute_query(
                cypher, id=node_id, database_=self._database
            )
            hits = [
                GraphHit(id=r["id"], canonical_name=r["name"] or "", domain=r["domain"] or "general")
                for r in records
            ]
            logger.debug("[KGStore] reachable node_id=%r → %d node(s) found", node_id, len(hits))
            return hits
        except Exception as exc:
            logger.error("[KGStore] reachable FAILED node_id=%r — %s", node_id, exc, exc_info=True)
            return []

    def edges_for_node(
        self,
        node_id: str,
        direction: str = "both",
        relation: Optional[str] = None,
    ) -> list[KGEdge]:
        """Return KGEdge objects for all edges touching node_id."""
        driver = self._get_driver()
        if driver is None:
            return []

        params: dict[str, Any] = {"id": node_id}
        if relation:
            params["relation"] = relation
        rel_filter = " AND r.relation = $relation" if relation else ""

        out_cypher = (
            "MATCH (a:Concept {id: $id})-[r:KG_EDGE]->(b:Concept) "
            f"WHERE true{rel_filter} "
            "RETURN a.id AS subject_id, a.canonical_name AS subject_name, "
            "a.domain AS subject_domain, r.relation AS relation, "
            "b.id AS object_id, b.canonical_name AS object_name, "
            "b.domain AS object_domain, r.id AS rid, r.source AS source, "
            "r.source_hash AS source_hash, coalesce(r.sources, []) AS sources, "
            "coalesce(r.source_hashes, []) AS source_hashes, r.created_at AS created_at"
        )
        in_cypher = (
            "MATCH (b:Concept)-[r:KG_EDGE]->(a:Concept {id: $id}) "
            f"WHERE true{rel_filter} "
            "RETURN b.id AS subject_id, b.canonical_name AS subject_name, "
            "b.domain AS subject_domain, r.relation AS relation, "
            "a.id AS object_id, a.canonical_name AS object_name, "
            "a.domain AS object_domain, r.id AS rid, r.source AS source, "
            "r.source_hash AS source_hash, coalesce(r.sources, []) AS sources, "
            "coalesce(r.source_hashes, []) AS source_hashes, r.created_at AS created_at"
        )

        if direction == "outgoing":
            cypher = out_cypher
        elif direction == "incoming":
            cypher = in_cypher
        else:
            cypher = f"{out_cypher} UNION {in_cypher}"

        logger.debug("[KGStore] edges_for_node node_id=%r direction=%r relation=%r", node_id, direction, relation)
        try:
            records, _, _ = driver.execute_query(cypher, **params, database_=self._database)
            edges = [self._row_to_edge(r) for r in records]
            logger.debug("[KGStore] edges_for_node node_id=%r → %d edge(s)", node_id, len(edges))
            return edges
        except Exception as exc:
            logger.error("[KGStore] edges_for_node FAILED node_id=%r — %s", node_id, exc, exc_info=True)
            return []

    def all_edges(self, relation: Optional[str] = None) -> list[KGEdge]:
        """Return all edges, optionally filtered by relation type."""
        driver = self._get_driver()
        if driver is None:
            return []

        if relation:
            cypher = (
                "MATCH (a:Concept)-[r:KG_EDGE {relation: $relation}]->(b:Concept) "
                "RETURN a.id AS subject_id, a.canonical_name AS subject_name, "
                "a.domain AS subject_domain, r.relation AS relation, "
                "b.id AS object_id, b.canonical_name AS object_name, "
                "b.domain AS object_domain, r.id AS rid, r.source AS source, "
                "r.source_hash AS source_hash, coalesce(r.sources, []) AS sources, "
                "coalesce(r.source_hashes, []) AS source_hashes, r.created_at AS created_at"
            )
            params: dict[str, Any] = {"relation": relation}
        else:
            cypher = (
                "MATCH (a:Concept)-[r:KG_EDGE]->(b:Concept) "
                "RETURN a.id AS subject_id, a.canonical_name AS subject_name, "
                "a.domain AS subject_domain, r.relation AS relation, "
                "b.id AS object_id, b.canonical_name AS object_name, "
                "b.domain AS object_domain, r.id AS rid, r.source AS source, "
                "r.source_hash AS source_hash, coalesce(r.sources, []) AS sources, "
                "coalesce(r.source_hashes, []) AS source_hashes, r.created_at AS created_at"
            )
            params = {}

        logger.debug("[KGStore] all_edges relation=%r", relation)
        try:
            records, _, _ = driver.execute_query(cypher, **params, database_=self._database)
            edges = [self._row_to_edge(r) for r in records]
            logger.debug("[KGStore] all_edges → %d edge(s)", len(edges))
            return edges
        except Exception as exc:
            logger.error("[KGStore] all_edges FAILED — %s", exc, exc_info=True)
            return []

    # ------------------------------------------------------------------
    # Factory helpers
    # ------------------------------------------------------------------

    @staticmethod
    def make_node(canonical_name: str, domain: str = "general") -> KGNode:
        """Convenience constructor for a new KGNode with a random UUID."""
        return KGNode(
            id=str(uuid.uuid4()),
            canonical_name=canonical_name,
            domain=domain,
        )

    @staticmethod
    def make_edge(
        subject_id: str,
        relation: str,
        object_id: str,
        source: Optional[str] = None,
        subject_name: Optional[str] = None,
        object_name: Optional[str] = None,
        domain: Optional[str] = None,
        source_hash: Optional[str] = None,
    ) -> KGEdge:
        """Convenience constructor for a new KGEdge with a random UUID."""
        return KGEdge(
            id=str(uuid.uuid4()),
            subject_id=subject_id,
            subject_name=subject_name,
            subject_domain=domain,
            relation=relation,
            object_id=object_id,
            object_name=object_name,
            object_domain=domain,
            source=source,
            source_hash=source_hash,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_datetime(value: Any) -> Optional[datetime]:
        if value is None or isinstance(value, datetime):
            return value
        return datetime.fromisoformat(str(value))

    @staticmethod
    def _external_ids_from_keys(keys: list[str]) -> dict[str, str]:
        result: dict[str, str] = {}
        for key in keys:
            if ":" in key:
                namespace, value = key.split(":", 1)
                result[namespace] = value
        return result

    @staticmethod
    def _row_to_edge(r: Any) -> KGEdge:
        return KGEdge(
            id=r["rid"] or str(uuid.uuid4()),
            subject_id=r["subject_id"],
            subject_name=r.get("subject_name"),
            subject_domain=r.get("subject_domain"),
            relation=r["relation"],
            object_id=r["object_id"],
            object_name=r.get("object_name"),
            object_domain=r.get("object_domain"),
            source=r["source"],
            source_hash=r.get("source_hash"),
            sources=list(r.get("sources") or []),
            source_hashes=list(r.get("source_hashes") or []),
            created_at=(
                datetime.fromisoformat(r["created_at"])
                if r["created_at"]
                else datetime.utcnow()
            ),
        )

    @staticmethod
    def _edge_to_row(edge: KGEdge) -> dict[str, Any]:
        return {
            "subject_id": edge.subject_id,
            "subject_name": edge.subject_name,
            "subject_normalized_name": normalize_label(edge.subject_name or edge.subject_id),
            "subject_domain": edge.subject_domain or "general",
            "relation": edge.relation,
            "object_id": edge.object_id,
            "object_name": edge.object_name,
            "object_normalized_name": normalize_label(edge.object_name or edge.object_id),
            "object_domain": edge.object_domain or "general",
            "id": edge.id,
            "source": edge.source,
            "source_hash": edge.source_hash,
            "created_at": edge.created_at.isoformat(),
        }
