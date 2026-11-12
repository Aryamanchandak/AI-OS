# KGStore — Neo4j Knowledge Graph Store

**Last updated:** 2026-07-16
**Replaces:** SQLite + NetworkX design (see git history)

---

## What This File Does

`kg_store.py` is the persistence layer for the `knowledge_graph` package.
It wraps a Neo4j database with a clean Python API for creating and querying
concept nodes and typed edges. All imports are lazy; the store degrades
gracefully when Neo4j is absent or unreachable.

---

## Architecture

- **Backend**: Neo4j (`:Concept` nodes, `:KG_EDGE` relationships)
- **Nodes**: `(:Concept {id, canonical_name, labels, normalized_name, domain, fields, external_ids, created_at})`
- **Edges**: `(a)-[:KG_EDGE {relation, id, source, source_hash, sources, source_hashes, created_at}]->(b)`
- **Relations**: free-form strings stored as the `relation` property on `:KG_EDGE`
- **Idempotency**: `MERGE` on `(subject_id, relation, object_id)` — safe to re-ingest
- **Identity**: reviewed `:ALIAS_OF` / `:SAME_AS` links; nodes are never physically collapsed
- **Evolution**: immutable `:Claim` nodes linked by `:SUPERSEDES`, `:CONTRADICTS`, or `:SUPPORTS`

## Connection Config

Constructor kwargs → env vars → defaults:

| Env var | Default |
|---|---|
| `NEO4J_URI` | `bolt://localhost:7687` |
| `NEO4J_USERNAME` | `neo4j` |
| `NEO4J_PASSWORD` | `neo4j` |
| `NEO4J_DATABASE` | `neo4j` |

## Key Methods

| Method | Description |
|---|---|
| `execute_write(cypher, rows=…, **params)` | Run an arbitrary write query; returns `(ok, error)`. **This is the pipeline's write path** — `ingestion.write_kg` calls it with the batch UNWIND-MERGE Cypher. |
| `upsert_node(node)` | MERGE a :Concept node |
| `upsert_edge(edge)` | MERGE a :KG_EDGE relationship (auto-creates nodes if missing); runs cycle detection if `hierarchical_relations` is set |
| `upsert_edge_batch(edges)` | Batch MERGE via UNWIND — preferred for bulk writes (no cycle check) |
| `find_identity_candidates(...)` | Staged ID/external-ID/label resolver; semantic matches remain candidates |
| `resolve_or_create_node(...)` | Auto-resolve deterministic IDs only; otherwise assign a stable UUID |
| `submit_identity_proposal(proposal)` | Store an inert, auditable proposal |
| `review_identity_proposal(id, status, reviewer)` | Materialize a link only on approval |
| `upsert_identity_link(link)` | Validated write API; approved links require reviewer + provenance |
| `identity_cluster(id, as_of)` | Approved/current alias and same-as cluster |
| `identity_expanded_edges(id, as_of)` | Edges across the cluster, preserving originating node/source |
| `identity_expansion_terms(id, as_of)` | Labels for vector and keyword query expansion |
| `upsert_claim(claim)` / `link_claims(...)` | Store time-indexed assertions and their history |
| `claims_for_identity(...)` | Current claims by default, or full history on request |
| `get_node(id)` | Fetch a KGNode by id |
| `search_by_name(query, limit)` | Nodes whose `canonical_name` contains the substring |
| `neighbors(id, direction, relation)` | Direct neighbors (outgoing / incoming / both) |
| `reachable(id, direction, max_hops)` | Transitive reach via variable-length Cypher paths |
| `edges_for_node(id, direction, relation)` | KGEdge objects for all edges touching a node |
| `all_edges(relation)` | All edges, optionally filtered by relation string |
| `is_available()` | True if Neo4j is reachable |
| `close()` | Close the driver connection |
| `make_node(name, domain)` | Factory — new KGNode with UUID id |
| `make_edge(subject_id, relation, object_id)` | Factory — new KGEdge with UUID id |

## Cycle Detection (opt-in)

Pass `hierarchical_relations=frozenset({"PREREQUISITE_OF", "COMPONENT_OF"})` to
the constructor. Before inserting a hierarchical edge, `upsert_edge` runs a
`shortestPath` Cypher query to check for an existing reverse path. If one exists,
`CycleDetected` is raised. Disabled by default.

## Relation Types

Free-form strings — any value is valid. Common defaults are exported as constants
from `knowledge_graph.models`: `PREREQUISITE_OF`, `COMPONENT_OF`, `CONTRASTS_WITH`,
`APPLIES_TO`, `RELATES_TO`, `IS_A`, `PART_OF`, `CAUSES`, `DEFINED_BY`.

## Role in the pipeline

`KGStore` is standalone — no dependency on any domain package. In the storage pipeline it is
constructed once by `run.py::run_kg()` as `KGStore()` (picking up `NEO4J_*` env vars, no cycle
detection), and `ingestion.write_kg` writes through `execute_write(_UPSERT_EDGE_ROWS_CYPHER, rows=…)`.
The read methods (`neighbors`, `reachable`, `edges_for_node`, `search_by_name`, `all_edges`) are a
query API with no in-repo caller yet.

New extraction artifacts use deterministic UUID5 concept IDs scoped to the bronze source hash.
This keeps reruns idempotent without claiming that identical labels in different sources are the
same entity. Existing JSONL artifacts and their older IDs remain valid and rebuildable.
