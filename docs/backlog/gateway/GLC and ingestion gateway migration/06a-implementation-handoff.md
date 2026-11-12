# Plan 06a — Implementation Handoff: Ingestion Domain Migration

**Audience:** the implementing agent (Codex).
**Rationale lives in `06-ingestion-domain-migration.md`** — this file carries
steps, paths, and pass/fail conditions. When a step says "per decision #N,"
read that section of Plan 06 rather than re-deriving the reasoning. Do not
copy rationale back into this file; two copies will diverge.

---

## 0. Hard rules — read before touching anything

1. **`ingestion-pipeline/merged-ingestion` is a READ-ONLY source.** Every
   file you create or edit is under `gateway/`. Do not fix things in place
   inside the old tree — it stays untouched, available only as rollback
   protection until Plan 07 retires it (decision #1).
2. **Contract stays byte-identical.** `/api/ingestion/*` and
   `contract_version == "component6.v1"` do not change (decision #4).
   Request/response shapes are unchanged.
3. **Mechanical move only.** No changes to coordinator behavior, review/judge
   gates, KG/vector/content/cleanup schemas, or retry/idempotency semantics
   (Work Package E). The reader/writer refactor is explicitly a separate,
   later project (decision #5) — do not fold it into this work.
4. **`shell/` is out of scope. Do not touch it.** The ingestion frontend
   already lives at top-level `shell/` (screens, `useIngestion.ts`, API
   client) — confirmed separate from the backend code this plan moves.
   Zero files under `shell/` should appear in this plan's diffs.
5. **Ingestion's model-calling profiles are already ported.** All seven
   profiles it needs already exist in `gateway/config/profiles.yaml` with
   pins matching `glc_v5/glc/profiles.yaml`. Verify equality; do not
   re-author the file.
6. **Ingestion gets its own new HTTP client for Work Package D — it does
   not keep importing `glc_v5/glc/client.py`.** See §0.1 for why.

### Do NOT do these

- Do **not** restructure `coordinator/`, `consumers/`, or any other internal
  ingestion folder beyond what's needed to import cleanly. Reorganization is
  a later, separate effort (decision #5 / Plan 06 "Explicitly out of scope").
- Do **not** delete `glc_v5/glc/client.py`. This plan stops *importing* it
  from ingestion (§0.1); whether the file itself is ever deleted afterward
  is Plan 07's call, not this one's.
- Do **not** wire `routing.yaml` or read `auto_route` / `cost_quality_tradeoff`
  / `escalate` on any LLM call ingestion makes. That's Plan 04 territory and
  unrelated to this move.
- Do **not** change any named profile string (`EXTRACTION_CHAT_PROFILE`,
  `EMBEDDING_GLC_PROFILE`, `COVER_CLASSIFICATION_PROFILE`,
  `DEFAULT_CLEANUP_PROFILE`) or any profile's provider+model pin.
- Do **not** build `gateway/sdk/` — deferred by Plan 04 decision #5.

### §0.1 — Resolved: which LLM client does ingestion use after the move?

Writing this handoff surfaced a real conflict between this plan's own exit
gate and Plan 04's notes: Plan 06's exit gate said ingestion must end up
with no `glc-v5`/`glc.client`/port-8111 dependency, while Plan 04a's
"Downstream constraints" section said the opposite — that ingestion keeps
`glc.client.LLM` permanently. Plan 07 separately claimed `glc.client` was
"being formalized into `gateway/sdk/`," which contradicted Plan 04 decision
#5 (SDK explicitly deferred, never built).

**Resolved, and all four docs (`04-glc-llm-orchestration-and-providers.md`,
`04a-implementation-handoff.md`, `06-ingestion-domain-migration.md`,
`07-runtime-cutover-and-legacy-removal.md`) have been corrected to agree:**
ingestion gets a **small, new HTTP client built under
`gateway/src/gateway/ingestion/`**, satisfying the exact same `ChatClient`
protocol (`extraction/gateway.py`), pointed at Gateway's registry-resolved
`/api/llm/chat`. It does **not** import `glc_v5/glc/client.py`. Grounding:
ingestion was confirmed as the *only* in-repo importer of
`glc_v5/glc/client.py` outside `glc_v5`'s own tests, so this satisfies both
decision #2's literal verification text (*"an HTTP-based client satisfying
`ChatClient`"* — it never required reusing the same class) and Plan 06's
own exit gate, without anyone deleting or editing `glc_v5/glc/client.py`
itself — that file's fate stays Plan 07's call. Proceed with Work Package D
as written below; nothing further to confirm with Aryaman on this point.

---

## 1. Decisions already made — do not relitigate

| # | Decision | Resolution |
| --- | --- | --- |
| 1 | Physical ownership | Full Gateway ownership. `gateway.ingestion` is its own top-level domain package — a **sibling** of `gateway/llm/`, not nested inside it. |
| 2 | Internal model access | HTTP isolation (matches Plan 04 decision #2, reversed 2026-09-21). Ingestion gets a new Gateway-owned HTTP client, not a continued import of `glc_v5/glc/client.py` — see §0.1. |
| 3 | Database ownership | Gateway's dependency container constructs ingestion's DB connections at startup. Schemas, queries, and physical location (`Database/*.db`) are unchanged. |
| 4 | Route / frontend contract | `/api/ingestion/*` and `component6.v1` unchanged. `shell/` is untouched — zero file moves, zero code changes. |
| 5 | Internal structure timing | Mechanical move first; the full pre-move test suite is the equivalence gate. Reader/writer refactor is separate and later, in its own commits. |
| 6 (Plan 04, adjacent) | Dormant routing fields | Not this plan's work. Ingestion never sets `auto_route`/`cost_quality_tradeoff`/`escalate`, so nothing here depends on how Plan 04 resolves it. |

---

## 2. Prerequisites — verified present as of 2026-09-23

Do not rebuild these. They exist and this plan builds on them:

| Thing | Path | Status |
| --- | --- | --- |
| Ingestion↔Gateway seam adapter | `gateway/src/gateway/app/temporary_ingestion_adapter.py` | ✅ present — this is what gets dissolved |
| Domain registration pattern | `gateway/src/gateway/app/router_registry.py` → `migrated_domain_registrations()` | ✅ present — control/llm/channels/voice already use it; ingestion is the one domain still bolted on separately |
| DI container | `gateway/src/gateway/app/dependencies.py` → `DependencyContainer` | ✅ present — `llm` and `channels` fields already show the pattern to follow for ingestion |
| Lifespan construction | `gateway/src/gateway/app/lifespan.py` → `build_container()` | ✅ present |
| Ingestion's required profiles | `gateway/config/profiles.yaml` | ✅ **all seven already present**: `chunker-v1`, `knowledge-extraction-v1`, `document-segmentation-v1`, `highlight-photo-summary-v1`, `cover-classification-v1`, `ocr-cleanup-v1`, `spelling-review-v1` — pins verified matching `glc_v5/glc/profiles.yaml` |
| Service registry | `gateway/config/services.yaml` | ✅ present — no new entry needed; ingestion isn't a separate network service |
| An orphaned ingestion-domain file **not covered by Plan 06's original doc** | `gateway/preview.py` (226 lines) | ⚠️ real, live code. Imports `ingestion.config`, `ingestion.coordinator.report`, `ingestion.coordinator.stages`, `ingestion.coordinator.state` — only reachable today via the same sys.path injection this plan removes. Must move into the new tree; flagged in §11. |

---

## 3. Source map

Two source roots feed the target tree, not one:

| Source | Lines | Moves to |
| --- | --- | --- |
| `ingestion-pipeline/merged-ingestion/src/ingestion/` | 15,422 total — `coordinator/` 2,875, `sources/` 1,963, `kg/` 1,874, `text_cleanup/` 1,150, `intake/` 869, `extraction/` 621, `vector/` 598, `publish/` 536, `consumers/` 392, plus top-level `runner.py`, `store.py`, `config.py`, `parsing.py`, `models.py`, `dispatch.py`, `routing.py`, `pipeline.py`, `ids.py`, `normalization.py`, `review_policy.py`, `content_store.py` | `gateway/src/gateway/ingestion/` (preserve internal layout — no reorganization) |
| `ingestion-pipeline/merged-ingestion/cockpit/server.py` | 767 | `gateway/src/gateway/ingestion/` — the router-factory seam Gateway currently calls (`config_from_environment`, `create_router`) |
| `gateway/preview.py` | 226 | `gateway/src/gateway/ingestion/preview.py` (or equivalent) — currently orphaned outside `src/`, discovered while writing this handoff, not in Plan 06's original doc |

Confirmed via `control/service.py`: its one "ingestion" mention (line 87) is
a comment only, not a code dependency. Work Package A's claim that the seam
is exactly `config_from_environment()` + `create_router(service)` holds.

### Target shape (from Plan 06, confirmed correct)

```text
gateway/src/gateway/ingestion/
├── api/
├── coordinator/
├── pipeline/
├── extraction/
├── sources/
├── consumers/        # renamed to destinations only in a later refactor
├── intake/
├── kg/
├── vector/
├── text_cleanup/
├── persistence/
└── preview.py         # gateway/preview.py's new home
```

---

## 4. Work Package A — Characterize the seam (confirm, don't rebuild)

- Confirmed two `main.py` files exist: `gateway/main.py` (repo root, 29
  lines — a compatibility shim for `uvicorn main:app` that re-exports from
  `gateway.app.main`) and `gateway/src/gateway/app/main.py` (the real app
  assembly). **Both** reference `INGESTION_ROOT` and both need updating.
- Confirmed the seam is exactly two functions
  (`temporary_ingestion_adapter.py:22-26`) plus `ReviewService`
  construction (lines 31-43) — nothing deeper is reached from outside
  ingestion.
- **`gateway/test_main.py` breaks on the move if not updated in the same
  commit**: line 6 imports `INGESTION_ROOT` directly from `main`, and line
  15 asserts `(INGESTION_ROOT / "cockpit" / "server.py").is_file()`. Update
  this test alongside the move, not as follow-up cleanup.
- **Establish the real baseline before touching anything.** Run
  `./.venv/bin/python -m pytest --collect-only -q` inside
  `ingestion-pipeline/merged-ingestion` and record the exact number. Plan
  06's prose says "~460"; a direct `grep -rn "def test_"` here found 441.
  Don't trust either figure — let pytest's own collection at the moment you
  start be the number Work Package F gates on.

**Done when:** a note (commit message is fine) records the actual pre-move
pytest-collected test count; confirmed public surface of `cockpit.server`
is exactly `config_from_environment()`, `create_router()`, and
`ReviewService`.

---

## 5. Work Package B — Import and package

- Import `src/ingestion/`, `cockpit/server.py`, and `gateway/preview.py`
  into `gateway/src/gateway/ingestion/`, per Plan 01's history-preserving
  import policy. Preserve internal file layout exactly.
- Add `gateway.ingestion` as first-party code in `gateway/pyproject.toml` —
  no separate dependency/version entry; it's not external anymore.

**Delete the `sys.path` injection — but it is four behaviors bundled into
one file, not one block.** `grep -n "sys.path" gateway/` passing is
necessary but not sufficient; each of these needs an explicit new home:

1. The `sys.path.insert` loop itself
   (`temporary_ingestion_adapter.py:17-20`) — deleted; imports become
   ordinary `from gateway.ingestion... import ...`.
2. The `AI_OS_PREVIEW=1` branch (lines 32-37), importing
   `PreviewCoordinator`/`preview_config` from what becomes
   `gateway/src/gateway/ingestion/preview.py` — update the import path, keep
   the behavior.
3. `INGESTION_DATABASE_ROOT` defaulting to `AI_OS_ROOT / "Database"`
   (line 39) — must land in the new container construction (Work Package
   C), not get silently dropped.
4. `INGESTION_RESOLVER` defaulting to `"local-reviewer"` (line 42) — same.
5. `ingestion_registration()` (lines 46-51, builds the `RouterRegistration`
   with `prefix="/api/ingestion"`) — becomes ingestion's own
   `registration()` function, matching the `migrated_domain_registrations()`
   pattern used by control/llm/channels/voice.

**Do not touch `gateway/main.py`'s own `PACKAGE_ROOT` sys.path.insert**
(lines 13-14) — that's the unrelated `uvicorn main:app` compatibility shim.
The done-check below must confirm *that one* survives while the ingestion
one is gone — not treat any `sys.path` hit as a failure.

- Update `gateway/test_main.py`: replace the `INGESTION_ROOT` import and the
  `cockpit/server.py` existence assertion with whatever the new equivalent
  check is (e.g. `import gateway.ingestion` succeeding), in the same commit.

**Done when:** `grep -n "sys.path" gateway/` finds exactly one hit (root
`main.py`'s `PACKAGE_ROOT` insert) and zero ingestion-related hits;
`import gateway.ingestion` and `import gateway.ingestion.preview` both work
with the package installed normally, no path manipulation required;
`gateway/test_main.py` passes against the new paths;
`temporary_ingestion_adapter.py` is deleted.

---

## 6. Work Package C — Compose through Gateway dependencies

This is the actual engineering work in this plan. Four concrete moves, not
a checklist:

1. **`ReviewService` joins `DependencyContainer`.** Today,
   `create_app()` eagerly builds `legacy_review_service =
   create_review_service()` *before* the FastAPI app exists, because
   `cockpit.server.create_router` captures one concrete `ReviewService`
   instance at construction time rather than resolving it per-request.
   Move that construction into `build_container()` (`lifespan.py`), add it
   as a field on `DependencyContainer` (`dependencies.py`), and add a typed
   accessor (`get_ingestion_service`) beside `get_llm_service` /
   `get_service_registry`.
2. **The router factory's capture timing.** If the router still needs one
   frozen service captured at construction, build it inside
   `build_container()` once the container's other pieces (DB paths, the
   §0.1 LLM client) are ready. Only switch to per-request `Depends`
   resolution if it provably doesn't change response behavior — Work
   Package E's "no behavior changes" constraint outranks stylistic
   consistency with other domains.
3. **Close ownership moves into the container.** Today
   `legacy_review_service.close()` runs manually in `lifespan.py`'s
   `finally` block, *outside* `DependencyContainer.close()`. Move it into
   `DependencyContainer.close()`, in reverse construction order, the way
   `channels.close()` and `http.close()` already do. Delete the manual
   close in `lifespan_for`'s `finally`; drop the `legacy_review_service`
   parameter from `lifespan_for()`'s signature entirely.
4. **Database/config construction moves to the container.**
   `INGESTION_DATABASE_ROOT` and whatever `config_from_environment()`
   currently reads get folded into `build_container()`'s existing
   `GLCPaths`/settings flow (or a small ingestion-specific settings loader
   called from there) — not read ad hoc inside ingestion's own code at
   import time.
5. **Mount via `migrated_domain_registrations()`.** Add
   `from gateway.ingestion.routes import registration as
   ingestion_registration` to `router_registry.py`, following the exact
   `control_registration()`/`llm_registration()` pattern, and include it in
   the returned tuple. Remove the separate `ingestion_registration(...)`
   call currently sitting in `create_app()`'s `register_routers(...)` call
   in `main.py`.

**Done when:** `create_app()` no longer constructs any ingestion service
before the FastAPI app/lifespan exists; starting and stopping Gateway
leaves no dangling ingestion DB connections/threads/executors (check open
file descriptors/threads across a start-stop cycle); `gateway/test_main.py`'s
ingestion tests pass unchanged against the new wiring; `DependencyContainer.close()`
is the only place ingestion resources are closed.

---

## 7. Work Package D — Replace the GLC package dependency

Per §0.1's resolution:

- Build a small HTTP client under `gateway/src/gateway/ingestion/`
  satisfying the exact `ChatClient` protocol from `extraction/gateway.py`:
  `chat(prompt=..., messages=..., profile=..., ...) -> dict`, pointed at
  Gateway's registry-resolved LLM address (`config/services.yaml`) and
  `/api/llm/chat`.
- Update `runner.py`'s construction — preserve the "exactly one instance,
  shared across the run" property; do not regress to one client per call.
- Delete the two `glc-v5` lines from ingestion's dependency metadata
  (`"glc-v5>=0.5.0"` and the `glc-v5 = { path = "../../glc_v5", editable =
  false }` source entry) once folded into gateway's own `pyproject.toml`.
- Preserve named-profile-only routing guards exactly (ground rule R1) — do
  not touch `EXTRACTION_CHAT_PROFILE`, `EMBEDDING_GLC_PROFILE`,
  `COVER_CLASSIFICATION_PROFILE`, or `DEFAULT_CLEANUP_PROFILE` values.
- **Profiles are already ported — verify only.** Confirm the seven profiles
  in `gateway/config/profiles.yaml` still have pins identical to
  `glc_v5/glc/profiles.yaml`. Do not re-author the file.
- Convert cross-project GLC tests into Gateway-domain contract tests;
  update `scripts/verify_environment.py` and `scripts/live_smoke.py` for
  the new client/URL.

**Done when:** `grep -rn "glc-v5\|glc\.client\|GLC_BASE_URL"
gateway/src/gateway/ingestion/` returns nothing; `gateway/pyproject.toml`
has no `glc-v5` entry contributed by ingestion; an end-to-end extraction
run produces the same `ClaimProposal`/`ConceptProposal`/`RelationProposal`
shape as before the move; a test asserts a real inbound HTTP request lands
on Gateway's own `/api/llm/chat` for each chat call.

---

## 8. Work Package E — Preserve data and processing semantics

A constraint on B–D, not new work:

- No diff in `coordinator/gates.py` (review/judge gates), `kg/`, `vector/`,
  `text_cleanup/`, `consumers/` behavior — confirmed by the full pre-move
  test suite passing unchanged.
- Specific retry test: kill a run after one destination (e.g. KG store)
  succeeds but before the next (e.g. vector store) is written; retry it;
  assert the first destination wasn't re-written.

**Done when:** the full ingestion suite (count from Work Package A) passes
unchanged against the migrated code; the retry test above passes.

---

## 9. Work Package F — Verification

- Full ingestion suite run from its new location, count matches Work
  Package A's recorded baseline.
- `gateway/test_main.py`, `gateway/test_contract_staleness.py`; export
  OpenAPI via `gateway/export_openapi.py` and diff against
  `migration/baseline/contracts/gateway-openapi.json`.
- Real shell review journey: load `http://127.0.0.1:8000/ingestion`, click
  through an actual review. `shell/` itself is untouched (decision #4), so
  this proves the backend wiring didn't change response shape.
- In-process extraction/embedding tests against a fake implementation of
  the §0.1-resolved `ChatClient` — no real provider call needed.
- Storage preflight, failure, recovery, idempotency tests.
- Update the README regression command that references
  `cockpit/server.py` directly (`gateway/README.md` line 93,
  `mypy --strict cockpit/server.py`) to the new path.

**Done when:** every regression command from `gateway/README.md` passes
from the new location; the manual shell review journey completes
end-to-end with no visible behavior change.

---

## 10. Exit gate — all must pass

- [ ] Gateway owns and imports ingestion normally — `gateway/src/gateway/ingestion/`
      exists; `ingestion-pipeline/merged-ingestion` is untouched and nothing
      in `gateway/` imports from it.
- [ ] No production `sys.path` injection points at the old project
      (`temporary_ingestion_adapter.py` deleted; root `main.py`'s unrelated
      `PACKAGE_ROOT` insert is the only remaining `sys.path` hit).
- [ ] Ingestion has no `glc-v5`, `glc.client`, or port-8111 dependency —
      resolved per §0.1.
- [ ] `/api/ingestion/*` and the shell journey are unchanged; `shell/` has
      zero modified files.
- [ ] The complete ingestion and Gateway suites pass, at the counts
      established in Work Package A/F.
- [ ] `gateway/preview.py`'s `AI_OS_PREVIEW=1` functionality still works
      from its new location.
- [ ] The old ingestion submodule remains available, untouched, as
      rollback protection — retiring it is Plan 07's job, not this plan's.

---

## 11. Open items for Aryaman — do not let Codex guess these

Both cross-plan contradictions originally flagged here (§0.1's client
choice, and Plan 07's stale `gateway/sdk/` reference) are now resolved and
corrected across `04-glc-llm-orchestration-and-providers.md`,
`04a-implementation-handoff.md`, `06-ingestion-domain-migration.md`, and
`07-runtime-cutover-and-legacy-removal.md`. One genuine open question
remains — this one isn't a contradiction, it's a gap only Aryaman can
answer:

1. **`gateway/preview.py`** was not mentioned anywhere in Plan 06's
   original doc. It's real, 226 lines, and depends on the same sys.path
   seam this plan removes. It should move into
   `gateway/src/gateway/ingestion/` regardless (it's ingestion-domain code
   either way) — but confirm whether `AI_OS_PREVIEW=1` is still an actively
   used dev path worth preserving, or dead weight worth deleting instead of
   moving.
