# KG Identity, Aliases, and Evolving Knowledge Plan

**Owner:** Knowledge-graph project  
**Status:** Implemented in the standalone `Database/knowledge-graph` package (2026-07-16)

Implementation note: the study-system copy remains a design record. The live implementation is
additive to the Neo4j store and extraction pipeline in `Database/knowledge-graph`. It includes
source-scoped stable IDs, lexical normalization, deterministic resolver stages, reviewed identity
proposals/links, time-valid identity expansion, vector-query expansion terms, immutable temporal
claims, claim-history links, broad field tags, and additive provenance. The dedicated-review items
in section 10 remain policy decisions; physical consolidation is not implemented.

## 1. Decision for now

Do not attempt a universal taxonomy for every subject. For the first cross-domain system, retain:

- stable entity/concept IDs assigned by the KG;
- human-readable labels;
- source provenance;
- typed relationships/claims;
- optional broad `field` tags; and
- time/status metadata.

Use graph traversal, vector retrieval, and an LLM reranker to find relevant information at query time. A large, rigid domain/subdomain hierarchy can be added only where a trusted domain-specific taxonomy provides clear value.

Temperature zero may be used for model-assisted extraction/reranking, but it does not turn model judgment into a database identity guarantee.

## 2. Identity versus alias versus relatedness

These must remain different assertions:

- **Identity:** two records refer to the exact same real concept/entity.
- **Alias:** one label is another name used for a concept, possibly only in a field or time period.
- **Relatedness:** two distinct concepts are connected but not interchangeable.

The LLM may propose any of these. It must not silently convert one into another.

## 3. Link, do not destructively collapse

The default strategy should preserve nodes and add reviewed links:

```text
(X)-[:ALIAS_OF {status, provenance, valid_from, valid_to}]->(Y)
(X)-[:SAME_AS {status, provenance}]->(Y)
(X)-[:RELATED_TO {type, provenance}]->(Y)
```

Approved alias/same-as links form an identity cluster for retrieval. Original node IDs, labels, sources, and edges remain available. This avoids mutating X and Y into an opaque Z and losing why each form existed.

A canonical display label may be chosen for presentation, but it does not erase the other nodes.

## 4. What `MERGE` means

`MERGE` is an idempotent database write, not an instruction to merge meanings.

Example:

- if the incoming record already carries the KG ID for X, `MERGE` matches X and attaches the new relationship/source assertion;
- if it has no known ID, it creates a candidate node with a new stable ID;
- if X and Y are later confirmed to be the same, a reviewed `SAME_AS`/`ALIAS_OF` link joins their retrieval cluster; and
- X's old edges and Y's new edges remain connected to their original nodes, while an identity-expanded query can retrieve both neighborhoods.

This matches the desired behavior: existing information is not discarded, and new information becomes reachable through the confirmed identity link.

## 5. How candidate matches are found without surrendering the decision to an LLM

Use a staged resolver:

1. exact stable external/internal ID match;
2. exact normalized label within compatible context;
3. already approved alias edge;
4. deterministic identifiers such as DOI, ticker, standard ID, or URL where applicable;
5. lexical/vector similarity to create candidates; and
6. LLM reasoning to rank/explain candidates.

Only high-certainty deterministic matches can be automatic. Ambiguous semantic candidates become review proposals. The user, an authorized reviewer, or an explicit policy decides whether to approve the link.

Normalization is still needed for casing, whitespace, Unicode, punctuation, and known deterministic identifier formats. It should not be used to claim semantic identity.

## 6. Query-time alias expansion

When a query matches X:

1. find approved, currently valid `ALIAS_OF` and `SAME_AS` links;
2. collect the identity cluster;
3. retrieve claims and edges from each cluster member;
4. retain which member/source produced each result; and
5. rank results for the user's query and context.

This gives the retrieval benefit of aliases without destroying the underlying distinctions.

## 7. Feeding agent/chat discoveries back to the KG

An agent conversation must not directly rewrite KG identity. Use a proposal workflow:

```text
Chat observation
    -> structured KG proposal
    -> provenance includes conversation/turn and user acknowledgement
    -> validation/review
    -> approved alias, claim, or correction edge
    -> query indexes updated
```

If the user explicitly confirms “X and Y are aliases,” the agent can submit that confirmation as strong provenance, but a validated write service still creates the link.

For the vector database:

- the original source chunks normally remain unchanged;
- approved aliases are added to query-expansion metadata or a small alias index;
- queries expand to both labels before vector/keyword search; and
- re-embedding is only needed if the vector implementation requires alias text inside the indexed representation.

## 8. Time, corrections, and changing beliefs

Do not overwrite a claim when it is challenged or proven wrong. Represent assertions with:

- `observed_at`;
- `ingested_at`;
- optional `valid_from` and `valid_to`;
- source and source version;
- confidence/evidence quality;
- status such as `current`, `superseded`, `disputed`, or `retracted`; and
- links such as `SUPERSEDES`, `CONTRADICTS`, or `SUPPORTS`.

A later source can supersede an earlier claim without deleting it. Retrieval defaults to current, well-supported claims but can include history when the question is temporal or asks how understanding changed.

This is the basis for research tools that revise beliefs: beliefs are evidence-weighted, time-indexed assertions, not mutable single truth fields.

## 9. Minimal classification strategy

For arbitrary material “under the sun,” use the simpler MVP:

- extract concepts and claims;
- optionally assign one or more broad field tags;
- store the source context;
- avoid enforcing domain/industry/subtopic hierarchies;
- let vector and graph retrieval produce candidates; and
- let the query-time model decide relevance for the immediate question.

Field tags are retrieval hints, not identity keys. A concept can have multiple fields. Domain-specific taxonomies such as CFA can later exist as optional overlays rather than defining the global graph.

## 10. Decisions that need a dedicated KG design review

- Whether confirmed `SAME_AS` links may ever be physically consolidated.
- Who is authorized to approve identity links.
- Confidence thresholds for automatic deterministic matches.
- How conflicting identity assertions are represented.
- Which alias metadata must be indexed by the vector store.
- How source trust and temporal weighting affect default retrieval.
- How identity clusters are versioned and audited.

Study-system should not decide these points while implementing card generation. It only requires stable IDs and identity-expanded retrieval from the final KG.
