# Architecture and Product Decisions

Status: accepted for v0, 2026-08-07.

## Scope

The project implements the complete architecture in `Ideas.md`. Every phase has a deterministic local execution path; optional providers and graph infrastructure add capability without making credentials a prerequisite. The goal is to produce inspectable epistemic artifacts, not polished model prose.

## Decisions

### Local Streamlit application

**Choice:** A local Streamlit web app is the initial product surface.

**Rationale:** The primary workflows are structured input, evidence review, graph inspection, and saved-run browsing. Streamlit keeps those close to the Python domain layer and makes a useful no-deployment v0 possible.

**Tradeoffs:** Streamlit is less flexible than a separate API and frontend. The app implements the mobile card stack with responsive, horizontally snapping cards while retaining full desktop graph inspection; a native mobile client could still offer richer gestures.

### Python 3.11 and Pydantic models

**Choice:** Python 3.11+ and Pydantic v2 define the application and graph state.

**Rationale:** Typed validation is important because prose is not the artifact. Explicit enums and schemas make node types, verification grades, source tiers, and serialization inspectable.

**Tradeoffs:** Pydantic is an additional runtime dependency and schema evolution will need migrations or compatibility handling as the product matures.

### Canonical claim cards

**Choice:** Normalize whitespace, split conjunctions conservatively, classify empirical/normative/definitional components, record scope and horizon, assess basic falsifiability, and hash the canonical payload.

**Rationale:** Every downstream artifact needs a stable identity, and mixed claim types must be visible before construction.

**Tradeoffs:** Deterministic language heuristics are transparent but shallow. The shipped model-assisted path handles difficult claims when configured, while the local path remains reproducible and inspectable.

### Typed graph as the artifact

**Choice:** Argument state consists of typed nodes, explicit edges, load-bearing markers, verification records, and warnings. Markdown is generated from this graph.

**Rationale:** Graph state can be validated, persisted, exported, diffed, and rendered in multiple ways. It also prevents unsupported facts from disappearing inside fluent prose.

**Tradeoffs:** The deterministic graph builder uses a deliberately modest premise scaffold across all six shipped frames. Configured model providers can deepen those same frames without changing the graph contract.

### Deterministic mode as a supported product mode

**Choice:** The complete local workflow works without an API key. An OpenAI provider implements the same construction interface when credentials are available.

**Rationale:** Offline operation makes the system testable, auditable, and immediately usable. The provider boundary prevents one vendor from becoming the domain model.

**Tradeoffs:** Deterministic construction cannot excavate domain-specific premises as deeply as a capable model. OpenAI output is schema-validated but still requires human review and may fail or vary.

### OpenAI as the first model adapter

**Choice:** Start with the OpenAI Responses API and environment-based credentials. The default model is configurable in the UI.

**Rationale:** This satisfies the approved starting provider while retaining an abstract construction-provider contract.

**Tradeoffs:** Deterministic mode uses distinct Red/Blue role families rather than independent vendors. When configured for live models, the orchestrator rejects identical non-deterministic family labels. Network retries remain the responsibility of the provider SDK.

### User-supplied evidence before live retrieval

**Choice:** Users provide source metadata and relevant excerpts. The verification service matches empirical nodes to those sources, preserves source IDs, and grades support as primary, secondary, contested, unsupported, or fabricated.

**Rationale:** Clean live retrieval requires a search provider, credentials, citation extraction, and source-quality controls that are absent from this repository. User-supplied evidence gives v0 a truthful verification boundary.

**Tradeoffs:** The system does not authenticate URLs, fetch pages, or prove excerpts are accurate. Evidence grades are workflow labels, not external fact-checks. Lexical matching can miss semantic support and can produce false matches; every result tells users to inspect the original.

### Conservative verification and repair behavior

**Choice:** Unsupported, contested, or fabricated load-bearing empirical premises are visibly downgraded and added to warnings. The claim is retained so the missing dependency remains inspectable.

**Rationale:** Silent reliance on a weak fact is the failure mode v0 is designed to prevent.

**Tradeoffs:** Unsupported facts cannot be repaired honestly without evidence. The rubric therefore performs one bounded regeneration/hardening pass and preserves a failed gate when evidence remains absent instead of fabricating support.

### Named-proponent honesty rule

**Choice:** A run is `SOURCED` only when supplied evidence contains a named author or advocate. Otherwise it is labeled `CONSTRUCTED — no real proponent located`.

**Rationale:** This makes charity drift visible and avoids representing a synthetic case as a real advocate's position.

**Tradeoffs:** A name is not proof that the person holds every reconstructed premise. Future retrieval must connect proponents to exact nodes and quotations.

### Generic and configurable SA01–SA15 catalog

**Choice:** Provide fifteen explicitly generic flag labels and prompts covering common forensic-review themes. The shipped `config/sa_flags.json` can be copied and selected through `STEELMAN_FORENSIC_FLAGS`; startup validation requires exactly one definition for every code SA01–SA15.

**Rationale:** `Ideas.md` references SA01–SA15 without defining them. Inventing authoritative meanings would be unsafe; a labeled scaffold makes the workflow usable while keeping the gap explicit.

**Tradeoffs:** The catalog is not a recognized standard, is not investment advice, and should be replaced with the user's actual definitions when available. The app does not claim accounting completeness.

### Mandatory benign-case escalation gate

**Choice:** Requested escalation is allowed only after a substantive benign explanation, management-supporting evidence consideration, residual-risk statement, and evidence grade are recorded.

**Rationale:** This operationalizes the v0 requirement that every flag receive a management steelman before escalation.

**Tradeoffs:** Length and completeness rules cannot judge whether the explanation is genuinely strong. A human remains responsible for review.

### SQLite with graph-shaped relational tables

**Choice:** SQLite is the v0 system of record. Analyses keep a complete JSON snapshot and normalized node, edge, source, and verification tables.

**Rationale:** SQLite is zero-configuration and reliable for a local single-user application, while normalized graph entities preserve a migration path and allow inspection.

**Tradeoffs:** It does not offer native graph traversal, concurrent distributed writes, or Neo4j query semantics. JSON snapshots duplicate normalized data by design to preserve exact run artifacts.

### Setup and automated verification

**Choice:** Package metadata, deterministic tests, a quick-start README, and this decision record ship with v0.

**Rationale:** The product must be reproducible without credentials and its safety gates must be regression-tested.

**Tradeoffs:** The OpenAI adapter is not exercised by offline tests because it would introduce network, cost, and nondeterminism.

## Assumptions

- Python 3.11+ is available.
- This is initially a local, single-user tool.
- API secrets are supplied through environment variables and must never be persisted.
- User-supplied source excerpts are permitted inputs and users remain responsible for source rights and accuracy.
- `primary` and `secondary` are user-selected provenance tiers, not conclusions independently reached by the app.
- The SA01–SA15 meanings in this repository are placeholders pending actual organizational definitions.
- SQLite JSON snapshots and normalized tables may coexist despite duplication because auditability matters more than minimal storage.
- No `mirfish`, decision-tracker, or other AI OS repository should be inferred or modified.

## Full-scope delivery choices

### Parallel frames and DAG orchestration

Both claim sides run concurrently. Within each, all six frames fan out concurrently and merge into the typed graph. The execution log records claim surgery, fan-out, verification, hardening, parity, crux, tracker, and rubric stages. Deterministic frame construction keeps the local path reproducible; live providers can deepen construction behind the same contract.

### Red/Blue, retreat paths, and budget parity

Red attacks distinct surviving verification gaps; Blue either anchors a repair to evidence or emits an ordered retreat condition. Configured live families must differ. Both sides receive and consume identical token/search reservations, and asymmetry raises an error. A stable claim-derived shuffle blinds side order without making saved reruns nondeterministic.

### Cruxes, predictions, and decision tracking

The system pairs opposing load-bearing dependencies into at most three cruxes. Each side emits a dated prediction with direction, numeric threshold, unit, and settling observation. SQLite preregisters and resolves predictions, then reports Brier score and accuracy across resolved entries.

### Rubric and regeneration

The gate scores proponent sourcing, load-bearing verification, hardening survival, crux isolation, falsifiable predictions, and budget parity. Below threshold triggers exactly one additional pressure pass. Evidence failures remain failed rather than being synthetically repaired.

### Verification cache and temporal identity

Stable node-text hashes key a SQLite verification cache. Stable claim and node hashes plus retained JSON snapshots enable comparisons across reruns. This is the local temporal-diff substrate; consumers can compare graph JSON without an external database.

### Neo4j and local integrations

`Neo4jGraphStore` writes claims, premise nodes, and relationships through the official driver when the optional extra is installed. `LocalMirfishAdapter` provides second-order path traversal over the same graph. SQLite tracker methods implement the absent decision-tracker contract locally. All adapters are injectable and covered offline.

### Domain packs and evaluation

General, rates/macro, credit, and forensic-accounting lenses feed every frame. The evaluation module provides an ideological-voice proxy and a held-out resolved-dispute scoring harness; the tracker supplies long-run calibration from real resolutions. These deterministic harnesses are executable baselines, with human/curated datasets supplied by callers.

### Retrieval boundary

User-supplied sources are the functioning retrieval input. Search budgets are enforced and logged even in deterministic mode. No credential-free search service with a stable provenance contract was assumed; a live provider can add search behind the provider boundary without changing graphs, grading, or parity rules.
