# Resolved MVP and Architecture

**Status:** Final — all open decisions resolved
**Scope:** Decisions required before feature implementation

## 1. Corrected definition

Study-system is not the frontend and it is not the data store. It is the **learning logic and orchestration system**.

It provides reusable capabilities for:

- selecting knowledge to turn into learning material;
- generating and validating flashcards and quizzes;
- serving due reviews and applying FSRS ratings;
- running Feynman and challenger interactions;
- tracking learning evidence, mastery, and calibration;
- applying baseline policy plus safe temporary overrides; and
- automating recurring learning work.

The unified chat frontend will call these capabilities through MCP tools. A future visual flashcard pane or unified dashboard belongs to the unified frontend project, not to the study-system core.

## 2. Logical architecture

There must be one implementation of learning rules, not duplicate logic in automation and MCP.

```text
                            Unified chat interface
                                     |
                                  MCP tools (stateless)
                                     |
                              +------v------+
Scheduled shell runner ----->| Study Core  |<----- future UI adapter
Manual automation run ------>| services    |
                              +------+------+
                                     |
                  +------------------+------------------+
                  |                  |                  |
             final KG query     vector search     study SQLite
             (read only)        (read only)       (owned writes)
```

Recommended code boundaries:

```text
study_system/
├── core/          # domain services and rules; no interface-specific behavior
├── automation/    # unattended jobs that call core services
├── mcp/           # validated MCP adapters that call core services
├── repositories/  # final KG, vector, and SQLite interfaces
├── config/        # baseline settings file (versioned, git-tracked)
└── prompts/       # versioned prompts used by core capabilities
```

These are logical boundaries. They can remain in one repository/package initially. If deployment later requires physical folders under separate Automation and MCP roots, both adapters should import the same versioned core package. Copying the learning logic into both folders is rejected because the two copies would drift.

**Sequencing note:** this folder restructuring happens *after* the baseline capture and characterization steps in `01_PRESERVATION_AND_MIGRATION.md` (Steps A–B), not concurrently with them. Wrap and characterize the existing behavior first; refactor into these boundaries second.

## 3. Data location versus data ownership

“Study-system owns FSRS” means it is the only system allowed to write FSRS state. It does **not** mean the database file is stored in this code repository.

All persistent input, output, configuration overrides, cards, and learning state live under the central database root:

```text
<AI Code>/Database/
├── Raw/
├── Ingested/
│   ├── SQLite/
│   │   ├── study_system/study_system.db
│   │   └── <other_project>/<other_project>.db
│   ├── Knowledge_Graph/
│   └── Vector_DB/
└── Runtime/                 # only when a runtime exchange is actually needed
    └── Exchange/
```

`Raw` and `Ingested` are the primary knowledge-data levels. SQLite, KG, and vector stores are representations under `Ingested`. `Runtime/Exchange` is not ingested knowledge: it was proposed as a temporary inbox/outbox for phone synchronization. Because phone synchronization is deferred, the Exchange folder is not part of the MVP and does not need to be created now.

### Resolved: table count

`study_system.db` has exactly **four tables**:

| Table | Owner writes | Purpose |
|---|---|---|
| `cards` | generation service | Card content, concept_id, source/version provenance |
| `review_state` | scheduling service | FSRS state per card — ease, stability, lapses, due date |
| `generation_runs` | automation job | One row per automation run — audit trail per §11 |
| `overrides` | override tool | Time-bounded baseline overrides, validated and attributed |

No separate concept-coverage or fluency table, and no Feynman/challenger session tables — see §7 for why.

Cross-project knowledge sharing happens through KG/vector retrieval or explicit APIs, not shared arbitrary writes.

## 4. What “call the final KG” means

Study-system queries the final, user-visible KG and vector database. It does not read ingestion staging tables or import internal ingestion classes.

The phrase “use a stable service or MCP contract” means a normal read interface such as:

- `kg.get_concept(concept_id)`;
- `kg.neighborhood(concept_id, depth)`;
- `kg.search(text)`;
- `vector.search(query, filters)`; or
- an equivalent public query API provided by those systems.

These are read calls to the final stores. The upstream database projects are responsible for exposing the information study-system needs. Direct access to a public database query driver can also be acceptable if it is deliberately supported and versioned; importing private ingestion modules is not.

## 5. Retrieval and caching

The MVP will re-query the final KG and vector database for current context when generating or evaluating material. It will not maintain a durable copy of retrieved source text.

Study-system still stores:

- generated cards and assessments, because they are learning records;
- source IDs, KG node IDs, and source-version/hash references used to create them;
- the model and prompt version; and
- FSRS/review state.

This preserves provenance without duplicating the source corpus. A short in-memory cache within one request is harmless, but no cross-session retrieval cache is required initially. If upstream content changes, a provenance/version comparison can later flag affected cards for regeneration or revalidation.

## 6. What the first MVP does

The first MVP is deliberately smaller than the previous v4 plan.

### Included

- a reusable core service layer;
- final KG/vector read adapters;
- central study SQLite storage (4 tables);
- flashcard generation with existing prompts and quality logic;
- FSRS scheduling and review-state updates;
- a minimal callable Feynman workflow (stateless MCP tool);
- a minimal callable challenger workflow (stateless MCP tool);
- MCP tools for the unified chat interface;
- a headless automation job;
- a fail-fast `.sh` launcher; and
- baseline configuration file plus audited temporary overrides.

### Deferred

- a standalone FastAPI/HTML study application;
- a button-driven dashboard;
- phone HTML delivery and result synchronization;
- a visual flashcard pane in the unified UI;
- complex mastery-based session planning;
- calendar availability and exam-phase planning;
- topic overrides;
- strong-topic re-verification policy;
- concept-level fluency/coverage scoring beyond has-a-card (see §7 — considered and rejected for MVP, not merely postponed);
- personalized FSRS retraining; and
- always-on background hosting.

Each deferred item remains recorded in `05_INTERFACE_AND_FEATURE_BACKLOG.md`.

## 7. Minimal MVP behavior

### Automation

The automation runner performs one bounded operation:

1. load baseline configuration file and merge in any active temporary overrides;
2. query the final KG for concepts;
3. exclude concepts that already have at least one card (`SELECT DISTINCT concept_id FROM cards`);
4. select the next deterministic batch of concepts with zero cards;
5. retrieve current KG/vector context;
6. generate and validate the configured number of card sets;
7. store cards, provenance references, and a `generation_runs` audit record; and
8. exit with a clear success or failure status.

**Resolved: concept selection rule.** The earlier "sufficiently represented" idea is dropped as ambiguous and redundant. Once a card exists, FSRS review state already tracks how well a concept is known — ease, stability, and lapses are a per-card fluency signal over time. A separate concept-level fluency score would just be a second, competing measure of the same thing the scheduler already owns. The MVP selector is a plain binary gate: has-a-card or does-not. If review-driven regeneration (e.g. "concept has cards but they're all lapsing badly, generate a supplementary set") is wanted later, it is a distinct backlog feature with its own design, not a threshold bolted into this selector.

No calendar fitting, mastery optimization, or sophisticated topic-priority model is required in this first operation.

### Chat/MCP

The initial MCP surface should let the unified chat interface:

- generate cards now with an optional temporary count;
- fetch due cards;
- submit a card rating;
- take one turn of a Feynman interaction;
- take one turn of a challenger interaction;
- report basic progress counts; and
- create or cancel a constrained temporary study override.

**Resolved: MCP tools are stateless.** Study-system does not hold conversation state for Feynman or challenger interactions. The unified chat frontend already retains conversation history and passes it with each call:

```text
feynman_turn(concept_id, conversation_so_far) -> {next_prompt, evaluation?, status: continue|done}
challenger_turn(concept_id, conversation_so_far) -> {next_prompt, evaluation?, status: continue|done}
```

Only the *final* outcome of a completed interaction is persisted — written into `review_state` (as a mastery/evidence signal) or logged alongside a `generation_runs`-style record. No dedicated session table exists, and this is why the schema in §3 is four tables rather than six: there is no mid-interaction state to store.

FSRS decides which existing cards are due. The MVP does not invent a second review-priority system.

## 8. Configuration answer

**Resolved: split baseline and overrides.**

Baseline configuration (e.g. five card sets per day, model/prompt versions) lives as a versioned file under `config/` — plain YAML/JSON, checked into git, reviewed like code, deployed with the application. It is not runtime data; it is a code-adjacent constant set, and keeping it in git gives diff history and rollback for free. It should not be scattered as a literal throughout the code.

The agent must not edit the baseline configuration file — it has no write path to it at all. Instead, it calls a constrained tool such as:

```json
{
  "operation": "set_temporary_override",
  "setting": "daily_card_sets",
  "value": 7,
  "starts_on": "2026-07-15",
  "expires_on": "2026-07-28",
  "reason": "user requested seven sets for fourteen days"
}
```

The override is validated, stored in the `overrides` SQLite table, attributed to its creator, time-bounded, auditable, and reversible. Effective configuration at request time is the baseline file merged with any currently-active (non-expired) override rows. This makes "agent cannot change baseline" a structural property of the system, not a policy that has to be remembered — the agent's tool simply has no code path to the file.

## 9. Terminal answer

Interactive terminal commands are not part of the target system. They should be replaced by MCP/chat workflows and automation.

The `.sh` file remains appropriate because it is a launcher, not an interactive user interface. It should:

- resolve its own location;
- activate the correct environment;
- validate required configuration and dependencies;
- run exactly one automation entry point;
- stop on the first error;
- log the run; and
- return a non-zero status on failure.

Existing terminal commands are retained temporarily as compatibility and diagnostic paths until replacement acceptance tests pass. Then they can be archived or removed separately.

## 10. SessionPlanner answer

`SessionPlanner` is existing code that attempts to combine due cards, new cards, mastery verification, and exam phase into a session. It is not required for the first MVP automation selector.

It should be preserved as reference work, covered by characterization tests where useful, and reconsidered when advanced autonomous planning is promoted. The redesign is allowed to rewrite it; preservation means keeping its useful decisions and tests available, not freezing its current implementation.

**Note on the Preservation Plan's "Shadow" step:** running old and new paths against the same fixture and comparing results (see `01_PRESERVATION_AND_MIGRATION.md` §5E) is appropriate for FSRS scheduling and validation logic, where the new implementation should match the old. It is not appropriate for concept selection — the new binary has-a-card rule is a deliberate simplification of SessionPlanner's approach, not a reimplementation of it, so divergence from the old selector's output is expected and correct.

## 11. Audit-reason answer

There is no need to create KG nodes for automation decision reasons or build a separate explanation subsystem. The MVP should write one compact `generation_runs` row in study SQLite containing:

- run ID and timestamp;
- effective configuration (baseline merged with active overrides);
- selected concept IDs;
- operation and outcome; and
- a simple selection code such as `unseen_coverage`.

This is ordinary backend logging and is useful for diagnosing an unattended job. It should not be recalculated by an LLM every time.

## 12. Direct responses to the cross-cutting comments

1. **Can the system do more than the original capability list?** Yes. Later capabilities include adaptive quizzes, misconception tracking, source-change revalidation, briefing/revision sessions, cross-topic challenges, workload forecasting, and agent-generated temporary study campaigns. They are backlog items, not MVP scope.
2. **Should study-system dictate ingestion requirements?** Yes. It supplies a consumer-requirements contract. A separate ingestion system implements those requirements for the benefit of every consumer.
3. **Does study-system store nothing?** Its repository stores no runtime data. Its owned data is stored centrally in its Database file, across exactly four tables (§3).
4. **Why cache retrieved context?** No durable context cache in the MVP. Re-retrieve current context and retain only provenance references with generated learning records.
5. **Are public reads needed?** Yes. Study-system reads the final KG/vector interfaces; it does not read private ingestion state.
6. **Should all terminal behavior disappear immediately?** No. It disappears only after MCP/automation replacements pass, so working behavior is not lost.
7. **Do we build the dashboard now?** No. Use the unified chat interface; visual UI work is separately parked.
8. **Do we build calendar/mastery logic now?** No. Preserve existing ideas and defer a deeper design until the MVP operates.
9. **Do MCP tools need to track conversation state?** No. They are stateless — the calling chat interface owns and passes conversation history; study-system persists only final outcomes (§7).

## 13. MVP acceptance criteria

The MVP is complete when:

1. one shell command runs card-generation automation without an IDE;
2. the job queries final KG/vector interfaces and writes only to central study SQLite (`cards`, `review_state`, `generation_runs`, `overrides`);
3. rerunning it is idempotent using `(concept_id, source_version_hash)` as the dedup key — no duplicate generation runs/cards for the same concept at the same source version;
4. the unified chat interface can call MCP tools for generation, due-card review, Feynman, and challenger, with no server-side session state required for the latter two;
5. ratings update FSRS state correctly in `review_state`;
6. an agent can create a validated expiring override in the `overrides` table but has no write path to the baseline configuration file;
7. existing cards and reviews remain accessible; and
8. no ingestion, KG, vector, or legacy study code has been deleted before its replacement gate is met.