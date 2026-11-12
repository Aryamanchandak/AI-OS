# MVP Implementation Verification Record

**Implementation plans:** `00_RESOLVED_MVP_AND_ARCHITECTURE.md`, `02_STUDY_AUTOMATION_MCP_AND_CONFIG.md`, `03_UNIFIED_INGESTION_PIPELINE.md`, `04_KG_IDENTITY_ALIASES_AND_EVOLUTION.md`, and the promoted scope of `05_INTERFACE_AND_FEATURE_BACKLOG.md`  
**Verification date:** 2026-07-17  
**Verification status:** Study automation/MCP, unified ingestion, KG identity/evolution, and the promoted chat/progress tier are locally verified; production KG/vector/gateway integration, legacy-data migration, live Neo4j acceptance, and live cutover remain pending

## 1. Purpose

This document records what was implemented for the resolved MVP, where each part lives, how it was verified, and what remains before production acceptance. It is evidence for review, not a replacement for the architecture plan.

## 2. Implemented components

| Plan capability | Implementation |
|---|---|
| Versioned baseline and safe runtime overrides | `config/baseline.json`, `src/study_system/core/baseline.py` |
| Shared learning rules used by adapters | `src/study_system/core/study_core.py` |
| FSRS compatibility entry point | `src/study_system/scheduler.py` |
| Four-table study-owned SQLite store | `src/study_system/storage/mvp_store.py`, `src/study_system/storage/migrations/010_mvp_four_table_schema.sql` |
| Final KG/vector read contracts | `src/study_system/repositories/interfaces.py` |
| File-backed development/test read adapters | `src/study_system/repositories/json_repositories.py` |
| Gateway-backed generation, quality checking, and practice evaluation | `src/study_system/core/gateway.py` |
| Headless bounded generation job | `src/study_system/automation/generate.py` |
| Fail-fast shell launcher and central logging | `scripts/run_study_automation.sh` |
| MCP service adapter | *(moved 2026-07-18 — was `src/study_system/mcp/tools.py`, now `mcp_server/tools/study/adapter.py` in the separate `mcp_server` project; see `plans/09`)* |
| Concrete stateless MCP server | *(moved 2026-07-18 — was `src/study_system/mcp/server.py`, folded into `mcp_server/tools/study/logic.py`; see `plans/09`)* |
| Package command entry points | `study-automation` in `pyproject.toml` (`study-mcp` removed with the MCP move, see `plans/09`) |
| MVP domain records | `src/study_system/types/mvp.py` |

The implementation was additive at the time this was originally written. **Resolved 2026-07-18:**
the legacy `cli/`, `session/`, `extraction/`, `generation/`, `ingestion/`, `kg/`, `vector/`,
`validation/`, and the old `storage/sqlite_store.py` + migrations 001–003 have since been deleted.
No code outside those directories imported them (verified by grep before deletion), the full test
suite passes (44 tests — the drop from 57 is entirely tests that belonged to the deleted modules),
and `mypy --strict` is clean across all remaining source files. See the checkpoint commit and
`CLAUDE.md`'s "What changed" section for the record.

## 3. Behavior implemented

The shared core now provides:

- deterministic selection of final-KG concepts with no existing card — `StudyCore.select_unseen_concepts()`
  (`core/study_core.py`) takes every concept from `kg.list_concepts()`, drops any whose ID is in
  `store.concept_ids_with_cards()`, sorts the remainder by `(domain, name, id)` for a stable order
  (not insertion order or randomness), and truncates to the requested count;
- current KG and vector retrieval without a durable source-context cache — `StudyCore.retrieve_context()`
  calls `kg.neighborhood()` and `vector.search()` fresh on every invocation and returns the result
  directly; nothing is written to SQLite except the resulting cards/provenance, so there is no
  context/chunk cache table to go stale;
- bounded card generation, quality validation, provenance capture, and generation audit records;
- idempotent card generation and write operations when an idempotency key is supplied — the caller
  passes `idempotency_key`; before doing any work, the method checks
  `store.get_idempotent_result(key, "<method_name>")`, which reads a row from `generation_runs`
  written under `operation = "idempotency:<method_name>"`; if found, the cached result is returned
  without redoing the work; on success the result is saved under that key
  (`storage/mvp_store.py::get_idempotent_result` / `save_idempotent_result`). This is separate from,
  and in addition to, the concept-level dedup above — a key never lets the *same* concept get a
  second card set even without a matching key;
- due-card retrieval and validated FSRS ratings from 1 through 4;
- stateless Feynman and challenger start/evaluation flows, with only completed evidence persisted;
- progress counts, recent activity, and active override reporting — all three are one call,
  `StudyCore.progress_counts()`, exposed as the `study_progress` MCP tool: counts come from
  `mvp_store.progress_counts()` (cards/concepts/due/generation-run counts via plain `COUNT(*)`
  queries), recent activity from `mvp_store.recent_activity()` (a read-only `UNION` view over
  existing `generation_runs` rows — no separate event table), and active overrides from
  `mvp_store.active_override_records()`; and
- allowlisted, bounded, attributed, expiring, cancellable temporary overrides.

**Exactly four SQLite tables:** `cards`, `review_state`, `generation_runs`, `overrides` — enforced
by `storage/migrations/010_mvp_four_table_schema.sql` and asserted directly in
`tests/unit/test_mvp_store.py`.

The automation path additionally provides preflight validation and a non-blocking single-run file lock under the central Database root. The shell launcher resolves its own location, requires Python 3.11 or newer, validates dependencies, stops on errors, and writes logs outside the repository.

The MCP server exposes exactly these ten tools:

1. `study_generate_cards`
2. `study_get_due_cards`
3. `study_submit_review`
4. `study_start_feynman`
5. `study_evaluate_feynman`
6. `study_start_challenger`
7. `study_grade_challenger`
8. `study_progress`
9. `study_set_temporary_override`
10. `study_cancel_temporary_override`

**Why Feynman and challenger are two separate modes, and why each is two tools, not one:**
Feynman ("explain it back to me in plain language") and challenger ("defend your claim against
adversarial probing") are different pedagogical techniques with different grading prompts
(`review/prompts/feynman_evaluator_v1.md` vs `challenger_v1.md`) and different evaluation schemas
(`gaps/shallow_areas/connections_missed/...` vs `initial_probe/follow_up_probes/edge_cases/...`) —
collapsing them into one mode would lose that distinction, not simplify anything.

Within each mode, `start_*` and `evaluate_*`/`grade_*` are separate because they have different
contracts: `start_*` is deterministic, read-only, and idempotent-by-construction (calling it twice
for the same concept just returns the same opening prompt — `core/study_core.py::start_feynman`
explicitly discards its `idempotency_key` argument with a comment explaining why), while
`evaluate_*`/`grade_*` is the call that actually needs the student's answer, grades it, and writes a
`generation_runs` audit row. A single tool can't have a "give me an opening prompt" mode and a
"grade this answer" mode with different required arguments cleanly.

**A third tool per mode, `study_record_*_evaluation`, is a fallback, not normally needed.**
Auditing this while answering the question above surfaced that `evaluate_feynman`/`grade_challenger`
already call the shared LLM gateway directly (`StudyCore`'s `practice_evaluator`, always wired to
`GatewayPracticeEvaluator` in `mcp/tools.py::build_mcp_core`) and persist the graded outcome in the
same call — the response contains an `evaluation` key and is done. `study_record_feynman_evaluation`
/ `study_record_challenger_evaluation` only matter if the gateway was unavailable, in which case
`evaluate_*`/`grade_*` instead returns a bare `grading_prompt` for the calling agent to grade itself.
The module docstring in `mcp_server/tools/study/logic.py` previously claimed the *opposite* — that
`evaluate_feynman`/`grade_challenger` never call an LLM and always require a follow-up `record_*`
call — which was accurate for an earlier design but became stale once `GatewayPracticeEvaluator` was
wired in and was never updated. Fixed 2026-07-18; see `plans/08_MCP_SURFACE_RECONCILIATION.md`.

## 4. Acceptance-criteria mapping

| Criterion from plan 00 §13 | Status | Verification evidence |
|---|---|---|
| One shell command runs generation without an IDE | Implemented; production run pending | `scripts/run_study_automation.sh`, automation preflight and lock tests |
| Read KG/vector and write only the four study-owned tables | Unit-verified | Repository contracts/adapters, exact-table assertions in `test_mvp_store.py` and `test_mvp_core.py` |
| Idempotent generation for concept/source version | Unit-verified | Binary has-card test, repeated generation-key test, database uniqueness constraints |
| MCP generation, review, Feynman, and challenger tools are callable and stateless | Unit-verified at adapter/server level | Exact MCP surface test and core flow tests |
| Ratings correctly update FSRS state | Unit-verified | Scheduler suite plus rating/state and invalid-input tests |
| Agent can create an expiring override but cannot write baseline | Unit-verified | Override allowlist, bound, expiry, cancellation, and merge tests; no baseline write API exists |
| Existing cards and reviews remain accessible | Preserved, migration acceptance pending | Legacy code was retained; prototype auxiliary-row preservation is tested, but no production database migration was executed |
| No upstream or legacy code deleted before replacement gate | Verified in implementation scope | Work was additive; legacy modules and migrations remain present |

## 5. Automated verification result

The complete test suite was run from the repository root with Python 3.11:

```bash
env UV_CACHE_DIR=/tmp/uv-cache PYTHONPATH=src \
  uv run --no-dev --with pytest \
  --python /Users/aryamanchandak/.local/bin/python3.11 \
  python -m pytest
```

Result on 2026-07-16:

```text
collected 57 items
57 passed in 0.26s
```

Coverage included:

- automation preflight and single-run locking;
- MCP bootstrap without a configured KG and exact MCP tool registration;
- four-table schema and prototype auxiliary-data preservation;
- deterministic unseen-concept selection and provenance;
- generation, review, and override idempotency;
- generated-card quality rejection;
- due-card filtering and FSRS state transitions;
- Feynman and challenger evaluation validation/persistence;
- temporary override validation, expiry, and cancellation;
- progress and unified recent activity; and
- pre-existing scheduler and vault-manifest behavior.

## 6. Production verification still required

`config/baseline.json` intentionally leaves `kg_concepts_path` and `vector_snippets_path` as `null`. The automation runner therefore fails fast until final KG/vector exports are configured or production service adapters replace the JSON adapters. The configured LLM gateway at `http://127.0.0.1:8107` must also be running for gateway-backed generation and evaluation.

Before declaring the MVP fully accepted, perform these environment-dependent checks:

1. Configure final KG and vector sources without pointing at ingestion staging data.
2. Start or configure the LLM gateway.
3. Run `scripts/run_study_automation.sh --check`.
4. Run `scripts/run_study_automation.sh` twice against an isolated acceptance database.
5. Confirm the second run creates no duplicate cards for unchanged concept/source versions.
6. Inspect the central SQLite file and confirm it contains only `cards`, `review_state`, `generation_runs`, and `overrides` for the MVP store.
7. Exercise all MCP tools over the selected transport and confirm retries with the same idempotency key do not duplicate writes.
8. Run a read/migration acceptance check against a copy of the existing production study database.

Until those checks pass, the precise claim is: **the MVP implementation is complete and unit-verified, but production integration and existing-data acceptance are pending external runtime configuration.**

## 7. Plan 01 preservation/migration verification (earlier session)

Before the gateway/schema work described above, an earlier pass on this branch executed plan `01_PRESERVATION_AND_MIGRATION.md`'s process directly:

- **Baseline capture (§3):** `plans/BASELINE_CAPTURE.md` records the current commands, configured data paths (legacy `Config` env vars vs. `StudyBaseline`/`config/baseline.json`), the two coexisting schema histories (legacy migrations 001-003 vs. the MVP four-table schema in migration 010), and confirms **no real SQLite database, vault, or concept-directory data exists anywhere in this checkout**. Practical effect: plan 01 §6's data-migration safeguards (never test against the only copy, backup first) are dormant, not yet live — there is nothing to lose today. Re-run that capture once a real vault/`.env` is configured and `study ingest` has actually run once.
- **Version control safety net:** this repository had no git history at all before that session. `git init` plus an initial baseline-snapshot commit now make every subsequent change reversible. Local history from that session: `54ba836` (baseline snapshot), `25b9b68` (logs-outside-repo fix, single-run lock, idempotency keys, bounded overrides, quality-check hook), `e47112f` (atomic idempotency fix, pytest `pythonpath` config, first real end-to-end automation run), `079e2b7` (Feynman/challenger redesigned from a word-count heuristic to prompt-rendering). The gateway/schema-consolidation work in §1-§6 above happened after this and is not yet committed as of this writing.
- **Manual end-to-end verification** (not just unit tests, at the state of the code as of `079e2b7`): ran `scripts/run_study_automation.sh` against a real temporary Database root and a hand-written JSON KG fixture (2 concepts). Confirmed the single-run `flock` lock was created and released under `<database_root>/Locks/`, the log file resolved outside the repository via the `AI Code` ancestor search, and 4 real cards plus 1 `generation_runs` audit row landed in a real SQLite file at the configured path. This ran against the schema/tools as they existed at that commit; re-run it if you want current end-to-end proof against the gateway-backed generator and the consolidated four-table schema.

## 8. Cross-repo MCP integration — a second surface, needs reconciling

Section 2 above lists `src/study_system/mcp/server.py` as *the* concrete MCP server. That file did not exist yet during the earlier session in §7. At that time, this system's tools were instead wired into a **separate, already-existing shared MCP server** at `/Users/aryamanchandak/Documents/AI Code/mcp_server` — the multi-project server that already hosts `finance`, `knowledge_graph`, `vector_db`, and other tool groups for the unified chat interface:

- `mcp_server/tools/study/{__init__,logic.py}` registers the same study tool surface under `group="study"`, following that project's existing `@register(group=...)` auto-discovery convention (same shape as its `finance`/`vector_db`/`knowledge_graph` groups).
- `mcp_server/mcp_server.py` gained one additional `sys.path` entry for this repo's `src/`, mirroring how it already adds the sibling `AI Agent/src`.
- The `StudyCore` backend is built lazily, on first tool call (`_get_tools()`), not at import time — matching that project's own pattern (`vector_db/search/logic.py`, `knowledge_graph/graph/logic.py`), so a misconfigured `baseline.json` only breaks study calls, not the whole shared server's startup. (A first pass built it eagerly at import time; that was caught and fixed before committing, since it would have taken finance/knowledge/news/etc. down too on a bad config.)
- Verified in isolation: direct file import of `logic.py` (bypassing that project's other groups, since `knowledge_graph`'s own `knowledge_graph` package and `agent` package aren't installed in this sandbox — a pre-existing environment gap, unrelated to this change). Confirmed no import-time I/O, `study_progress`/`study_get_due_cards` work with no KG configured, and `study_start_feynman` on an unknown concept raises `KeyError` as expected. The full shared server (all groups together) was never actually started in this sandbox.
- That project's local git history (also newly initialized, same reasoning as above): `9f67d96` (baseline snapshot), `28b33be` (initial wiring), `6b90ea6` (lazy-init fix).

**Resolved 2026-07-18 — see `plans/08_MCP_SURFACE_RECONCILIATION.md` for the full record**, then
**superseded the same day by `plans/09_MCP_ADAPTER_RELOCATION.md`**: rather than keep the standalone
`study_system/mcp/server.py` as a secondary local-test path (plan 08's decision), the entire `mcp/`
package was moved out of this repo into `mcp_server/tools/study/`. This repo no longer has any MCP
code — read plan 09 for the current state, not this paragraph.

## 9. Plan 03 unified-ingestion implementation verification

Plan `03_UNIFIED_INGESTION_PIPELINE.md` was implemented as a separate project at:

```text
/Users/aryamanchandak/Documents/AI Code/Automation Personal/unified-ingestion
```

Keeping ingestion in its own project avoids adding another ingestion path to the already-dirty legacy `Database/Raw Data` code. The implementation writes runtime data only beneath the central Database root and leaves the existing Raw Data, KG, vector, and study-system implementations intact.

### 9.1 Implemented components

| Plan capability | Implementation |
|---|---|
| Configuration and central Database-root path resolution | `src/unified_ingestion/config.py` |
| Typed source, envelope, extraction, review, and dispatch records | `src/unified_ingestion/models.py` |
| Deterministic normalization and source/path identity | `src/unified_ingestion/normalization.py` |
| SQLite ledger, version links, review queue, and dispatch state | `src/unified_ingestion/store.py` |
| Gateway-backed semantic extraction with strict structured output | `src/unified_ingestion/extraction.py` |
| Independent KG/vector handoff and retry handling | `src/unified_ingestion/dispatch.py` |
| Capture, process, reprocess, review, and retry orchestration | `src/unified_ingestion/pipeline.py` |
| Read-only Markdown-tree discovery | `src/unified_ingestion/sources.py` |
| Operator CLI | `src/unified_ingestion/cli.py` |
| Shell entry point | `scripts/run_ingestion.sh` |
| Cutover and rollback checklist | `docs/CUTOVER.md` |

### 9.2 Behavior implemented

The pipeline now provides:

- immutable raw capture under `Database/Raw Data/unified/YYYY-MM-DD/<source_type>/`, with captured files made read-only;
- a durable ledger, normalized envelopes, review records, and dispatch handoffs under `Database/Ingested/Unified_Ingestion/`;
- separate raw and normalized SHA-256 hashes;
- deterministic UTF-8, line-ending, Unicode NFC, frontmatter, whitespace, blank-line, bullet, URL, and path normalization;
- quarantine for malformed inputs without losing the original capture;
- exact-duplicate and normalized-duplicate linking without redundant extraction;
- semantic versioning and supersession only when normalized source content changes;
- stable envelope, source, claim, relation, and proposal identities with legacy-reference mapping;
- extraction-version reprocessing without recapturing the source;
- gateway extraction for concepts, claims, relations, tags, and source-quality assessments;
- exact evidence quotes with normalized character ranges;
- review routing for unresolved evidence, low-confidence identity/alias decisions, and source-quality concerns;
- explicit approve/reject review operations and approved/current/disputed/superseded proposal states;
- idempotent, independently retryable KG and vector dispatch keyed by envelope, target, and extraction version; and
- a read-only, deterministically sorted Markdown-tree scanner that preserves the legacy vault scan/hash boundary.

The CLI exposes `capture`, `capture-tree`, `process`, `reviews`, `review`, `retry-dispatches`, and `status` commands. Capture is intentionally decoupled from extraction and dispatch, so source evidence can be preserved even while the gateway or a downstream target is unavailable.

### 9.3 Automated verification result

Verification run on 2026-07-17:

```text
unified-ingestion pytest: 20 passed in 0.15s
unified-ingestion strict mypy: Success, 10 source files
study-system regression pytest: 57 passed in 0.28s
study-system strict mypy: Success, 6 selected source files
shell syntax: run_ingestion.sh, run_study_automation.sh, and run_study_mcp.sh passed
```

The ingestion tests cover immutable capture, normalization, quarantine, exact and normalized deduplication, semantic version supersession, extraction-version reprocessing, evidence resolution, review decisions, dispatch idempotency/retries, stable identities, source-policy handling, and deterministic tree scanning.

### 9.4 Cutover status and remaining gates

The implementation is locally verified, but it does **not** claim a completed production cutover. `unified-ingestion/docs/CUTOVER.md` keeps the following gates open:

1. Configure and exercise a live LLM gateway using representative sources.
2. Replace or consume the JSON handoff with the production Neo4j/KG and vector adapters.
3. Verify downstream systems preserve the same envelope IDs, extraction version, source hashes, evidence spans, and access policy.
4. Migrate or reconcile legacy ingestion records and confirm rollback from backups.
5. Run shadow ingestion, compare KG/vector outputs, then explicitly approve ownership cutover.
6. Confirm study retrieval reads only approved/current downstream records after cutover.

Until those gates pass, the precise Plan 03 claim is: **the unified ingestion pipeline is implemented and locally verified, with durable capture and idempotent handoff ready for integration; live downstream writes and legacy migration remain pending.**

## 10. Consolidated verification summary

| Workstream | Current state |
|---|---|
| Plan 02 study automation, configuration, quality gates, and standalone MCP | Implemented and unit/protocol verified |
| Four-table MVP persistence | Implemented; prototype auxiliary tables are migrated into the four-table model and removed |
| Plan 03 unified capture, normalization, extraction, review, and handoff | Implemented and unit verified in the separate `unified-ingestion` project |
| Live LLM gateway acceptance | Pending |
| Live KG/vector integration and provenance validation | Pending |
| Existing production-data migration and rollback drill | Pending |
| Standalone versus shared MCP exposure decision | Pending reconciliation described in §8 |

## 11. Plan 04 KG identity, aliases, and evolving knowledge verification

Plan `04_KG_IDENTITY_ALIASES_AND_EVOLUTION.md` correctly identified the live owner as the
standalone knowledge-graph project rather than the deprecated `study_system/kg` stub. The
implementation was therefore made at:

```text
/Users/aryamanchandak/Documents/AI Code/Database/knowledge-graph
```

The study-system plan remains the design and verification pointer. No identity logic was added to
the deprecated local KG module.

### 11.1 Implemented components

| Plan capability | Implementation |
|---|---|
| Identity, proposal, candidate, and temporal-claim types | `Database/knowledge-graph/src/knowledge_graph/models.py` |
| Unicode/case/whitespace/punctuation label normalization | `Database/knowledge-graph/src/knowledge_graph/identity.py` |
| Stable external-identifier lookup keys | `Database/knowledge-graph/src/knowledge_graph/identity.py` |
| Reviewed identity proposal and link writes | `Database/knowledge-graph/src/knowledge_graph/kg_store.py` |
| Deterministic/lexical candidate resolver | `Database/knowledge-graph/src/knowledge_graph/kg_store.py` |
| Time-valid identity-cluster traversal | `Database/knowledge-graph/src/knowledge_graph/kg_store.py` |
| Identity-expanded edge and claim retrieval | `Database/knowledge-graph/src/knowledge_graph/kg_store.py` |
| Vector/keyword alias-expansion terms | `Database/knowledge-graph/src/knowledge_graph/kg_store.py` |
| Immutable claims and history relationships | `Database/knowledge-graph/src/knowledge_graph/kg_store.py` |
| Source-scoped stable IDs for new extraction artifacts | `Database/knowledge-graph/src/knowledge_graph/extraction.py` |
| Normalized-name ingestion and additive edge provenance | `Database/knowledge-graph/src/knowledge_graph/ingestion.py`, `kg_store.py` |
| Public exports and technical reference | `Database/knowledge-graph/src/knowledge_graph/__init__.py`, `kg_store.md` |

### 11.2 Behavior implemented

- New concepts extracted from different bronze sources receive different deterministic UUID5 IDs,
  preventing equal-looking labels from silently asserting cross-source identity. Rerunning the same
  source remains deterministic and idempotent. Previously persisted JSONL artifacts and legacy IDs
  remain valid.
- Concept labels are normalized lexically for candidate discovery, while the original labels and
  canonical display label remain preserved. Normalization does not itself approve identity.
- Stable internal IDs and exact external identifiers are the only automatic deterministic resolver
  matches. Exact normalized labels and partial lexical matches remain review candidates.
- `ALIAS_OF`, `SAME_AS`, and `RELATED_TO` remain distinct relationship assertions. Approved
  identity links require provenance and reviewer attribution.
- Chat/extractor observations can be stored as inert `IdentityProposal` nodes. Rejection creates no
  identity link; approval materializes only the allowlisted relationship type.
- Approved, currently valid `ALIAS_OF` and `SAME_AS` links form a query-time identity cluster.
  Retrieval retains the original member node IDs and source provenance rather than physically
  collapsing nodes.
- Identity expansion terms expose approved current labels to vector or keyword callers without
  changing or re-embedding original chunks.
- Claims are stored as separate time-indexed nodes with source/version, observation/ingestion and
  validity times, confidence, evidence quality, field tags, and lifecycle status. Claims can be
  linked with `SUPERSEDES`, `CONTRADICTS`, or `SUPPORTS`; history is not deleted.
- Repeated evidence on ordinary KG edges accumulates `sources` and `source_hashes` rather than
  retaining only the first provenance pointer.

### 11.3 Automated verification result

Verification was executed inside `Database/knowledge-graph` using its Python 3.11 environment:

```bash
PYTHONPYCACHEPREFIX=/tmp/kg-pyc PYTHONPATH=src \
  .venv/bin/python -m unittest discover -s tests -v

PYTHONPYCACHEPREFIX=/tmp/kg-pyc \
  .venv/bin/python -m compileall -q src tests

.venv/bin/python -m pip check
```

Result on 2026-07-16:

```text
8 identity/evolution tests passed
package import smoke test passed
source and test compilation passed
No broken requirements found
```

The focused tests cover normalization, external identifiers, source-scoped stable IDs, resolver
certainty, inert proposal behavior, rejection safety, review requirements, temporal claim
provenance, validity-aware identity traversal, and vector-query expansion terms.

Strict `mypy` was not available in the knowledge-graph virtual environment, so no static-typing
claim is made for this workstream.

### 11.4 Verification limits and policy decisions intentionally left open

A live Neo4j server was not available during this implementation, so the Cypher paths were tested
through a recording fake driver, package compilation, and model-level tests rather than a live
database integration run. Production acceptance still requires:

1. Run schema-constraint creation and every new write/read query against the deployed Neo4j version.
2. Exercise proposal approval/rejection and time-valid cluster traversal with representative data.
3. Confirm the vector consumer uses `identity_expansion_terms` before keyword/vector retrieval.
4. Decide reviewer authorization, deterministic-match thresholds, conflicting identity assertions,
   source-trust weighting, cluster audit/version policy, and whether physical consolidation is ever
   permitted.

Physical consolidation was deliberately not implemented. The precise Plan 04 claim is:
**the additive identity, alias, resolver, provenance, query-expansion, and evolving-claim APIs are
implemented and locally unit-verified; live Neo4j compatibility and governance acceptance remain
pending.**

## 12. Plan 05 interface and feature-backlog verification

`05_INTERFACE_AND_FEATURE_BACKLOG.md` is a sequencing backlog rather than authorization to build
every future feature. The implementation therefore promoted only sections 2 and 3: the active MVP
services and the next-tier unified-chat contract. Sections 4 through 9 remain deferred as the plan
requires.

### 12.1 Promotion record and implemented scope

The plan now records the required outcome, owner, dependencies, data contract, acceptance criteria,
and preservation impact. The user-visible outcome is that a unified chat client can:

- fetch due flashcards, control presentation/answer reveal, and submit an FSRS rating;
- request bounded generation or create/cancel an expiring generation campaign;
- run grounded Feynman and challenger turns;
- inspect cards, final-KG coverage, unseen concepts, due reviews, recent activity, and active
  overrides; and
- do all of the above through the existing shared `StudyCore` and ten MCP tools, without duplicating
  learning, scheduling, retrieval, or persistence rules in a chat client.

Most of this surface was already present from Plan 02 in the active dirty worktree. The concrete
Plan 05 gap implemented in this pass was basic progress and recent activity.

### 12.2 Files and behavior added in this pass

| Capability | Implementation |
|---|---|
| Cross-workflow recent activity feed | `src/study_system/storage/mvp_store.py::recent_activity` |
| Final-KG coverage and unseen-concept calculation | `src/study_system/core/study_core.py::progress_counts` |
| Bounded recent-activity access through the MCP facade | `src/study_system/mcp/tools.py::progress_counts` |
| Extended `study_progress` contract | `src/study_system/mcp/server.py::study_progress` |
| Unified-chat contract documentation | `README.md` |
| Promotion record and explicit deferred scope | `plans/05_INTERFACE_AND_FEATURE_BACKLOG.md` |
| Store/core acceptance coverage | `tests/unit/test_mvp_store.py`, `tests/unit/test_mvp_core.py` |

The activity feed is derived read-only from existing `generation_runs` and `review_state` records.
Completed Feynman/challenger outcomes are represented as `generation_runs`-style audit rows; no
mid-interaction session or `practice_attempts` table exists. The feed does not introduce a duplicate
event table. Returned activity has a timestamp, type, entity ID, and structured details. The
caller-supplied activity limit is validated between 1 and 200.

`study_progress` now returns:

- `cards`;
- `concepts_with_cards`;
- `total_concepts` from the final KG adapter;
- `unseen_concepts` as final-KG IDs without cards;
- `due_cards`;
- `generation_runs`;
- `recent_activity`; and
- `active_overrides`.

### 12.3 Automated verification result

Focused verification:

```bash
env UV_CACHE_DIR=/tmp/uv-cache \
  uv run --no-dev --with pytest \
  --python /Users/aryamanchandak/.local/bin/python3.11 \
  python -m pytest \
  tests/unit/test_mvp_store.py \
  tests/unit/test_mvp_core.py \
  tests/unit/test_mcp_server.py \
  tests/unit/test_mcp_bootstrap.py
```

```text
25 passed in 0.39s
```

Full study-system regression verification on 2026-07-17:

```bash
env UV_CACHE_DIR=/tmp/uv-cache \
  uv run --no-dev --with pytest \
  --python /Users/aryamanchandak/.local/bin/python3.11 \
  python -m pytest
```

```text
57 passed in 0.28s
```

Strict typing of the four touched source modules also passed:

```text
Success: no issues found in 4 source files
```

`git diff --check` passed for every file touched in this Plan 05 pass.

### 12.4 Explicitly deferred scope

No standalone study frontend, autonomous director, calendar/exam planner, phone synchronization,
advanced-learning feature, or always-on service was introduced. Those items require their own
promotion records and acceptance criteria. The precise Plan 05 claim is: **the active MVP and
unified-chat tool contract are present, and basic progress is complete and regression-verified;
the later backlog remains intentionally unimplemented.**

## 13. Updated consolidated verification summary

| Workstream | Current state |
|---|---|
| Plan 02 study automation/MCP | Implemented and unit/protocol verified; live gateway acceptance pending |
| Plan 03 unified ingestion | Implemented and unit verified; downstream cutover pending |
| Plan 04 KG identity/evolution | Implemented and locally unit verified; live Neo4j/governance acceptance pending |
| Plan 05 active MVP + chat tier | Implemented and regression verified; later backlog intentionally deferred |
| Existing production data migration | Pending backup, migration, and rollback drill |
| Standalone versus shared MCP exposure | Pending reconciliation described in §8 |

## 14. Final ledger-alignment implementation and verification (2026-07-17)

This section records the final implementation pass requested against
`06_COMMENT_RESOLUTION_LEDGER.md`. The pass audited the existing dirty MVP implementation against
the ledger and the final decisions in `00_RESOLVED_MVP_AND_ARCHITECTURE.md`. It corrected a material
prototype mismatch: the code had temporarily created six tables and persisted mid-interaction
practice attempts, while the resolved architecture requires exactly four tables and stateless
Feynman/challenger calls.

### 14.1 Changes implemented

| Resolved requirement | Implemented result | Primary files |
|---|---|---|
| Exactly four study-owned SQLite tables | The runtime schema now contains only `cards`, `review_state`, `generation_runs`, and `overrides` | `src/study_system/storage/mvp_store.py`, `src/study_system/storage/migrations/010_mvp_four_table_schema.sql` |
| Remove unapproved auxiliary tables without silently losing completed evidence | Startup compatibility migration moves completed prototype practice evidence and retry results into internal `generation_runs` audit rows, then removes `practice_attempts` and `idempotency_keys` | `src/study_system/storage/mvp_store.py` |
| Stateless Feynman/challenger interactions | Start calls are deterministic and read-only; they return a mode/concept handle, prompt, source references, and `continue` status without creating a session row | `src/study_system/core/study_core.py` |
| Unified chat owns conversation state | Evaluation tools accept optional `conversation_so_far` and incorporate it into the grounded grading prompt | `src/study_system/core/study_core.py`, `src/study_system/mcp/tools.py`, `src/study_system/mcp/server.py` |
| Persist only final practice outcomes | Completed model or externally supplied evaluations are written as provenance-backed `feynman_evaluation` or `challenger_evaluation` audit operations | `src/study_system/core/study_core.py`, `src/study_system/storage/mvp_store.py` |
| Preserve write idempotency within the approved schema | Retry results use deterministic internal audit-row IDs in `generation_runs`; review-state update and retry record remain one SQLite commit | `src/study_system/storage/mvp_store.py`, `src/study_system/core/study_core.py` |
| Keep progress semantically accurate | `generation_runs` count includes only actual card-generation operations; internal retry rows are excluded from activity; completed practice outcomes appear as practice activity | `src/study_system/storage/mvp_store.py` |
| Keep the ten-tool MCP contract | Tool names remain unchanged; Feynman/challenger evaluation schemas now also accept caller-owned conversation history | `src/study_system/mcp/server.py`, `tests/unit/test_mcp_server.py` |
| Keep runtime data outside the repository | Central database path, lock path, and launcher log path remain rooted under the central `Database/` tree | `src/study_system/core/baseline.py`, `src/study_system/automation/generate.py`, `scripts/run_study_automation.sh` |
| Make the implementation contract reviewable | Plan 02 and the project README now state that practice starts are read-only, chat owns history, only final evidence is persisted, and the schema has four tables | `plans/02_STUDY_AUTOMATION_MCP_AND_CONFIG.md`, `README.md` |

The implementation remains additive with respect to legacy study functionality. Interactive legacy
CLI, ingestion, scheduling, and historical migrations were not removed.

### 14.2 Verification added or updated

Tests now explicitly verify:

- a newly created MVP database has exactly the four approved tables;
- a prototype six-table database preserves completed practice evidence and retry results before the
  two auxiliary tables are removed;
- due-card ratings update `review_state` without a separate review-history table;
- Feynman/challenger starts are deterministic and do not require persisted session state;
- caller-provided conversation history reaches the Feynman grading prompt;
- completed practice evaluation evidence is persisted as an audit operation;
- idempotency keys cannot be reused across different write operations;
- repeated generation and review keys do not duplicate their effects;
- progress and recent activity distinguish generation, review, and completed practice evidence; and
- the MCP server still exposes exactly the approved ten tools.

Final local verification from the study-system repository:

```bash
.venv/bin/python -m pytest -q
```

```text
57 passed in 0.28s
```

Strict typing was run over the ten active MVP source files:

```text
Success: no issues found in 10 source files
```

Additional checks:

```text
bash -n scripts/run_study_automation.sh scripts/run_study_mcp.sh   passed
git diff --check                                                   passed
scripts/run_study_mcp.sh --help                                    passed
study_system.automation.generate --help                            passed
```

The broad repository-wide strict type check still reports pre-existing issues in legacy
compatibility modules (`storage/sqlite_store.py`, `core/config.py`, and `core/clients.py`). Those
modules were not changed as part of this ledger-alignment pass, and no claim is made that legacy
code is strict-mypy clean.

### 14.3 Remaining production acceptance gates

This implementation pass did not fabricate external runtime configuration. The checked-in
`config/baseline.json` still leaves `kg_concepts_path` and `vector_snippets_path` unset, and the
configured LLM gateway must be available for gateway-backed generation, validation, and practice
evaluation. Therefore the following remain environment-dependent acceptance work:

1. Configure supported final KG and vector read sources, never ingestion staging data.
2. Start/configure the shared LLM gateway and run the automation preflight.
3. Run two locked generations against an isolated central acceptance database and inspect the
   second-run duplicate behavior.
4. Exercise all ten tools through the selected live MCP exposure path.
5. Reconcile the standalone study MCP server with the shared multi-project MCP registration
   described in §8.
6. When real legacy learning data exists, migrate a backup copy and perform the rollback drill.

Precise final claim for this pass: **the resolved study MVP code contract is implemented and locally
verified, including the exact four-table schema and stateless practice model; live external-system
integration and production-data migration remain pending.**
