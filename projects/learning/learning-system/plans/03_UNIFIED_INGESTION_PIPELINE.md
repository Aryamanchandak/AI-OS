# Unified Ingestion Pipeline Feature Plan

**Owner:** A dedicated ingestion project, not study-system  
**Status:** Requirements to use when the ingestion system is built/refactored

**Implementation:** `Automation Personal/unified-ingestion` now implements the
shared capture/envelope/review/dispatch boundary. See its `docs/CUTOVER.md` for
the remaining live Neo4j/ChromaDB acceptance gates. Legacy study-system and Raw
Data ingestion paths remain intentionally preserved until those gates pass.

## 1. Objective

Build one shared ingestion pipeline that cleans, identifies, records, and dispatches source material before KG and vector-specific ingestion occurs.

Study-system specifies what knowledge it needs, but the resulting ingested facts and source material are available to every authorized system.

## 2. Why one pipeline

Separate KG and vector pipelines should not independently:

- read the same raw content;
- clean it differently;
- assign unrelated source IDs;
- hash different representations;
- disagree about document boundaries or versions; or
- lose the connection between a graph assertion and its supporting chunk.

Shared preprocessing creates one authoritative ingestion record, after which specialized consumers build their own optimized representations.

## 3. Proposed flow

```text
Source capture
    |
Immutable raw record
    |
Structural normalization
    |
Content/version hashing and exact deduplication
    |
Validated canonical ingestion envelope
    |
Semantic extraction (concepts, claims, triplets, optional field tags)
    |
Human/agent review queue for uncertain semantic decisions
    |
+--------------------+---------------------+
|                    |                     |
KG ingestor      Vector ingestor      Other consumers
```

## 4. Shared ingestion envelope

Every downstream consumer should receive the same core identifiers and source information:

- immutable `source_record_id`;
- source type and origin;
- captured and observed timestamps;
- normalized content or a stable reference to it;
- raw-content hash;
- normalized-content hash;
- source version/supersedes relationship;
- metadata and access policy;
- extraction version;
- structured concepts, claims, and relation proposals;
- confidence/review status; and
- provenance linking every derived item to the source.

## 5. What normalization means

An intelligent LLM returning strict JSON does not remove the need for normalization.

There are two distinct operations:

### Structural normalization — deterministic

- text encoding and line endings;
- extraction of supported metadata/frontmatter;
- whitespace rules where semantics are unchanged;
- stable source IDs and timestamps;
- JSON schema validation;
- hash inputs;
- URL/path normalization; and
- rejection/quarantine of malformed records.

### Semantic interpretation — model-assisted

- concept and claim extraction;
- relation proposals;
- possible field tags;
- alias/same-as proposals; and
- source-quality or contradiction signals.

Temperature zero improves repeatability but does not guarantee identical, correct, or complete semantics. LLM output must still be schema-validated, provenance-linked, and treated as a proposal where it could change identity or belief.

## 6. Deduplication layers

- **Exact raw duplicate:** deterministic hash; do not ingest twice.
- **Same normalized document:** normalized hash; link captures rather than repeat extraction.
- **New version of a source:** create a version/supersedes relationship; do not erase history.
- **Semantically overlapping content:** retain both sources and let KG/vector retrieval represent the overlap.
- **Possible duplicate concept:** send an identity proposal to the KG identity process; ingestion must not silently collapse it.

## 7. Study-system consumer requirements

The final KG/vector result must let study-system retrieve:

- stable concept IDs and labels;
- relationships and claims around a concept;
- source chunks supporting those claims;
- current versus superseded/disputed claim status;
- source and version references;
- update timestamps; and
- enough data to generate and validate learning material.

Study-system does not require the pipeline to generate cards or calculate mastery.

## 8. Preserving current work

The existing study-system ingestion assets are inputs to this project, not disposable code:

- vault scanning behavior;
- semantic hashing/frontmatter logic and tests;
- extraction schemas and prompts;
- validation lessons;
- manifest state transitions;
- KG edge persistence behavior; and
- vector embedding metadata.

The new ingestion project should compare these capabilities against its design and reuse or port them where sound.

## 9. Cutover gate

Study-system removes its ingestion path only after a fixture can:

1. enter the unified pipeline once;
2. produce linked final KG and vector records;
3. be reprocessed idempotently;
4. produce a new version without erasing history;
5. expose stable retrieval to study-system; and
6. preserve or map legacy source/concept references.

## 10. Questions for the ingestion design session

- What are the actual raw source types and capture mechanisms?
- Where is the immutable raw record stored?
- What component owns the ingestion envelope?
- Does semantic extraction happen once centrally or in a KG-specific stage?
- How are uncertain model proposals reviewed?
- How are corrections and new source versions propagated to final stores?
- How are failures retried without duplicate downstream writes?
