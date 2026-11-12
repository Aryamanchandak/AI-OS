# Preservation and Migration Plan

**Goal:** Redesign freely without discarding working logic, prompts, data, or lessons from the existing system.

## 1. Preservation principle

The target architecture may rewrite any implementation. “Preserve the hard work” does not mean every current class remains in production. It means:

- behavior is understood before replacement;
- useful algorithms and prompts are retained or deliberately superseded;
- persistent data is never abandoned silently;
- tests capture the parts that already work;
- historical documents remain available; and
- deletion is delayed until the replacement is proven.

## 2. Existing asset inventory

### Keep and adapt for the MVP

| Existing asset | Value to preserve | Likely destination |
|---|---|---|
| `generation/generator.py` | Parameterized flashcard and quiz generation | Core card-generation service |
| Card-generation prompts | Existing card/quiz behavior and prompt work | Versioned core prompts |
| `validation/quality.py` and prompts | Grounding and rubric checks | Core validation service |
| `scheduling/scheduler.py` | FSRS scheduling calculations | Core scheduling service |
| Scheduler tests | Verified first/subsequent-review behavior | Expanded core tests |
| `types/card.py` | Card, rating, and review contracts | Core domain models |
| `storage/sqlite_store.py` | Existing schema access and learning data | Split repositories/migrations |
| SQL migrations | Existing cards, reviews, quiz, mastery, and config schema history | Central database migration history |
| Feynman prompt | Substantial evaluation design | Callable Feynman capability |
| Challenger prompt | Substantial adversarial-question design | Callable challenger capability |
| Calibration logic | Useful later evidence model | Deferred feature module |
| Overrides logic | Useful basis for expiring policy changes | Restricted override service |
| SessionPlanner | Existing planning thinking | Reference for later autonomous director |

### Transfer to another owner after replacement

| Existing asset | Future owner | Preservation action |
|---|---|---|
| `ingestion/ingester.py` | Unified ingestion project | Extract requirements and reusable behavior |
| `ingestion/vault_manifest.py` | Unified ingestion project | Preserve semantic hashing/tests |
| `extraction/extractor.py` and prompt | Unified ingestion/KG extraction | Preserve schema, validation, and prompt lessons |
| local `kg/kg_store.py` | KG project | Compare behavior with final KG before retirement |
| local `vector/vector_store.py` | Vector project | Retain only until final vector adapter works |
| concept directory storage | Probably superseded by central DB plus upstream retrieval | Migrate any unique data before retirement |

### Replace as interfaces become available

| Existing asset | Reason |
|---|---|
| Interactive terminal reviewer | Unified chat/MCP becomes the user path |
| Interactive terminal quiz | Unified chat/MCP becomes the user path |
| Terminal chat router | Unified frontend already owns conversation |
| Monolithic CLI orchestration | Mixes ingestion, generation, storage, and UI concerns |
| Direct provider clients | Should use the shared LLM gateway |

## 3. Baseline capture before editing

Before architectural changes:

1. record current commands and expected outcomes;
2. back up the existing SQLite database and concept files;
3. record schema and migration versions;
4. run the current tests and store the result;
5. add sample fixtures for generation, rating, due-card selection, Feynman input, and challenger input;
6. identify every configured data path; and
7. record which current commands are actually used versus merely present.

No migration should be attempted without knowing where the real current data resides.

## 4. Characterization tests

Characterization tests protect behavior without claiming the current design is ideal.

Minimum tests to add:

- card generation parses valid model JSON and rejects malformed output;
- target card count reaches the generator correctly;
- grounding failure prevents or flags activation according to the approved rule;
- first and later FSRS ratings produce expected state transitions;
- recording the same review/result twice is idempotent or rejected;
- due-card retrieval is stable and filters card types correctly;
- existing cards/reviews can be read from a copied database fixture;
- active/expired overrides resolve correctly; and
- migration on a copy preserves row counts and foreign-key relationships.

## 5. Replacement strategy

Use an incremental replacement approach:

### Step A — Wrap

Create new repository and service interfaces around existing working functions. Do not rewrite algorithms yet.

### Step B — Characterize

Add tests at the new service boundaries and confirm old behavior through them.

### Step C — Redirect

Point the new automation and MCP adapters at the shared core services.

### Step D — Migrate storage

Copy the real study database to the central path using a tested migration/backup process. Validate schema, row counts, representative records, due-card queries, and FSRS writes.

### Step E — Shadow

Where practical, run the old and new read/planning paths against the same fixture and compare results. New writes must use a test/copy database until accepted.

### Step F — Switch

Make automation/MCP the normal entry points. Keep old terminal entry points available temporarily for diagnostics.

### Step G — Retire separately

Archive or remove an old component only in a later change after its replacement has operated successfully. Do not mix feature delivery with broad deletion.

## 6. Data migration safeguards

- Never test migration against the only copy of the real database.
- Create a SQLite-consistent backup first.
- Make migrations forward-only and versioned.
- Run foreign-key checks and integrity checks.
- Compare table counts before and after.
- Verify a sample of cards, reviews, mastery records, and settings.
- Keep the original database read-only until the new path has passed acceptance.
- Document rollback as switching the configured path back to the untouched copy.

## 7. Upstream handoff safeguards

Ingestion/KG/vector code may leave this repository only after:

- its functional requirements have been copied into the relevant feature plan;
- the new owner has implemented the interface;
- a fixture ingests through the new unified pipeline;
- final KG and vector stores expose the expected result;
- study-system retrieves equivalent or better context; and
- legacy manifests or source IDs have a mapping where needed.

## 8. Explicit non-goals

This preservation plan does not require:

- retaining obsolete folder structures forever;
- preserving undocumented bugs;
- keeping terminal interfaces after replacement;
- maintaining duplicate implementations; or
- forcing the MVP to include every partially built later feature.

## 9. Removal gate checklist

For every file or subsystem proposed for removal:

- [ ] Existing responsibility documented
- [ ] Existing data identified
- [ ] Replacement owner named
- [ ] Replacement interface implemented
- [ ] Characterization tests pass
- [ ] Data migration or compatibility verified
- [ ] End-to-end acceptance completed
- [ ] Rollback documented
- [ ] Removal performed separately

