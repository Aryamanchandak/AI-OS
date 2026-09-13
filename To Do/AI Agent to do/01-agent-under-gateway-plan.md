# Bring the AI Agent Under the AI OS Gateway

This is the same kind of move already planned for GLC and ingestion
(`../Gateway to do/GLC and ingestion gateway migration/`), applied to
`AI Agent/`. Read this alongside that roadmap — the agent should land on the
same gateway foundation (Plan 02) rather than growing a second, incompatible
notion of "the gateway."

Do not start by copying files or changing imports. This agent has more
loose ends than GLC or ingestion did at the same stage (own untracked git
history, external dependencies outside the AI OS tree, a documented bug that
turns out to already be fixed elsewhere, zero tests). Phase 0 below exists to
turn those unknowns into decisions before anything moves.

## What "AI Agent" currently is

A small typed cognitive agent (`EAGV3 — Session 7`): a five-stage loop —
`memory.read → perception.observe → decision.next_step → action.execute →
memory.record_outcome` — over an MCP tool server, with FAISS-backed vector
memory and on-demand document indexing. Source layout:

```text
AI Agent/src/agent/
├── schemas.py            typed data contracts
├── gateway.py            LLM + embedding bridge (locates a workspace root)
├── cognition/
│   ├── perception.py     goal state across iterations
│   ├── decision.py       one LLM call/turn: answer or call one tool
│   ├── action.py         MCP dispatch (stdio ClientSession); large results → artifact store
│   └── memory.py         typed memory service (vector-first, keyword fallback)
├── services/
│   ├── vector_index.py   FAISS IndexFlatIP wrapper
│   └── artifacts.py      content-addressable byte store
├── agent7.py             orchestrator / CLI entry point
└── app_planner.py        FastAPI chat UI (its own inline HTML, port 8000)
```

## Findings from this investigation (2026-09-13)

These are facts, not assumptions — verified against the filesystem and code
in this session. They change the shape of the plan versus a naive "move the
folder into gateway/" read of the request.

1. **`AI Agent/` is its own git repository**, untracked by the AI OS parent
   repo (`git status` at the AI OS root shows `?? "AI Agent/"`), with no
   remote and 4 local commits. It also currently has substantial **uncommitted
   work in progress**: `agent7.py`, `action.py`, `decision.py`, `memory.py`,
   `schemas.py`, and both `services/*.py` are modified but uncommitted; five
   docs are deleted-but-uncommitted; several new docs are untracked. This is
   the same situation Plan 01 of the GLC roadmap describes for `gateway/`
   itself before it was adopted — treat it the same way: commit and protect
   before moving anything.

2. **The agent's real runtime dependencies live outside `AI OS/` entirely —
   and its auto-boot mechanism does not currently resolve at all.**
   `gateway.py` walks up from its own file looking for an ancestor directory
   that contains both `llm_gateway/` and `mcp_server/` **as direct
   children**, falling back to an `AI_CODE_ROOT` env var that skips the
   walk-up but still requires `AI_CODE_ROOT/llm_gateway` to exist. Checked
   directly:
   - `~/Documents/AI Code/mcp_server` exists as a direct child of `AI Code/`.
   - `~/Documents/AI Code/llm_gateway` does **not** exist. The real
     `llm_gateway` lives one level deeper, at
     `~/Documents/AI Code/Final Gateway/llm_gateway`.
   - No directory on any real ancestor path of either agent checkout (see
     finding 4) has both as direct children. Setting
     `AI_CODE_ROOT=~/Documents/AI Code` does **not** fix this —
     `GATEWAY_V7_DIR` would resolve to a path that doesn't exist, and
     `ensure_gateway()` raises immediately.
   - As far as this investigation can tell, **the agent's auto-spawn LLM path
     is currently non-functional** unless run with some undocumented manual
     setup (e.g. starting `llm_gateway` by hand and pointing `AI_CODE_ROOT`
     at `Final Gateway`, which still wouldn't satisfy the `mcp_server`
     half of the check). This needs to be confirmed empirically in Phase 0,
     not assumed — but it changes the framing from "this still works via a
     personal folder" to "this may already be broken today," which makes
     repointing at `glc_v5` (Decision 1) a fix, not just a tidy-up.
   - Corroborating evidence for Decision 1: `Final Gateway/` also contains a
     dated `glc_v5-migration-20260906-161511/` folder — independent evidence
     that `llm_gateway`'s functionality was deliberately migrated into
     `glc_v5` at some point, consistent with the `/v1/chat`/`/v1/embed`
     contract match noted in finding 3.

3. **`glc_v5` (already inside AI OS, already an active gateway-migration
   target) looks like the successor to `llm_gateway`, not a coincidence.**
   `glc_v5/glc/routes/chat.py` serves `POST /v1/chat` and `POST /v1/embed`;
   its `ChatRequest` docstring literally says *"Backward-compatible
   request — every new field is optional."* This is strong circumstantial
   evidence that `glc_v5` is the evolved, in-repo replacement for the
   `llm_gateway` service the agent still auto-spawns on port 8107 — but this
   is an inference, not a verified contract match. Confirm field-for-field
   before relying on it (see Decision 1 below).

4. **The mcp_server "known regression" documented in this repo looks fixed —
   but for a *different checkout* of this agent than the one in `AI OS/`.**
   `AI Agent/README.md` and `TODO.md` §7 both describe `mcp_server` importing
   this agent's `memory`/`artifacts` modules via a dead
   `sys.path.insert(0, ".../AI Code/agent")` and via flat `import memory` /
   `import artifacts`. Reading the actual current `mcp_server` source shows
   both are fixed in syntax: `mcp_server.py` inserts
   `_find_workspace_root() / "AI Agent" / "src"` onto `sys.path`, and
   `tools/knowledge/memory/tool.py` does
   `from agent.cognition import memory as _memory` /
   `from agent.services import artifacts as _artifacts` — matching the
   current package layout. But `mcp_server`'s own workspace root is
   `~/Documents/AI Code`, not `AI OS`, so that fix resolves to
   `~/Documents/AI Code/AI Agent/src` — **a second, separate checkout**,
   confirmed to exist with its own `.git` directory, sitting outside `AI OS/`
   entirely. A `diff -rq` of its `src/` against `AI OS/AI Agent/src/` came
   back byte-identical at the time of this investigation, so today the two
   have not drifted — but nothing keeps them in sync, and this plan must not
   assume `AI OS/AI Agent` is "the" checkout mcp_server actually exercises.
   See Decision 3 for how this gets resolved before history import.

5. **Port collision with the gateway.** `app_planner.py` runs its own
   `FastAPI()` app and serves it on `127.0.0.1:8000` — the exact port the AI
   OS Gateway (`gateway/main.py`) already owns. Two standalone `uvicorn`
   processes can coexist today only because they're never run at the same
   time from the same terminal; under one gateway they cannot both bind 8000.

6. **No test coverage.** `pytest` is configured (`pyproject.toml`) but the
   suite is empty — confirmed by running it (`no tests ran`). GLC (563
   passed), ingestion (460 passed), and gateway (27 passed) all have a
   baseline to protect during their migrations; this agent has none. Per the
   GLC roadmap's program rule ("Each plan begins with characterization
   tests"), this has to be built, not skipped.

7. **Separate persistence root.** The agent keeps its own state at
   `AI Agent/data/state/` (`index.faiss`, `index_ids.json`, `memory.json`)
   and `AI Agent/data/sandbox/` (upload staging), independent of the AI OS
   root `Database/` that ingestion and GLC already write into.

8. **Real design debt already tracked, orthogonal to this move.**
   `TODO.md` documents unresolved memory/artifact issues (content becomes
   unsearchable once offloaded to an artifact, no artifact GC, no per-run
   scoping, high-temperature classifier calls) and deferred loop features
   (parallel tool firing, HITL round-cap breaks). None of this blocks putting
   the agent under the gateway, but the migration will touch
   `memory.py`/`action.py`/`gateway.py` directly, so don't silently "fix"
   any of it in the same commits — that's explicitly against the GLC
   program rule separating structural moves from behavioral changes.

## Decision

The AI OS Gateway becomes the agent's runtime host, the same way it is
becoming the host for ingestion and (per the other roadmap) GLC:

- The agent's five-stage loop, memory service, and vector index become a
  gateway domain (`agent/`), mounted the same way ingestion is mounted today
  (`app.include_router(..., prefix="/api/agent")`), not a second standalone
  FastAPI process on port 8000.
- The agent stops auto-spawning its own LLM gateway subprocess. It calls
  whatever LLM backend the AI OS Gateway resolves for it — most likely
  `glc_v5` once Plan 04 of the GLC roadmap lands, or `glc_v5` directly today
  if its `/v1/chat` and `/v1/embed` contracts are confirmed compatible before
  that migration finishes.
- `app_planner.py`'s inline-HTML chat UI is retired in favor of a chat surface
  in the shared React shell (`shell/`), talking to the new `/api/agent/*`
  routes the same way the shell already talks to `/api/ingestion/*`.
- The MCP tool server dependency is resolved explicitly (not left pointing
  at a personal folder outside the repo) — see Decision 3.
- `AI Agent/`'s own git history is preserved through a deliberate
  import/subtree decision, not a Finder copy, mirroring Phase 2 of the GLC
  dismantle plan.

## Decisions required before implementation

### 1. LLM/embedding backend

- [ ] Confirm `glc_v5`'s `POST /v1/chat` and `POST /v1/embed` are a strict
      superset of what `AI Agent/src/agent/gateway.py` and its vendored
      `llm_gateway_client.LLM` actually send and expect back (message shape,
      tool-call shape, embedding response fields, error envelope). Do this
      with a recorded fixture comparison, not a read-through.
- [ ] If compatible: point the agent at `glc_v5` directly and delete the
      `ensure_gateway()` auto-spawn logic in `gateway.py` entirely, along with
      the `AI_CODE_ROOT`/sibling-walk-up logic it exists to support.
- [ ] If not compatible: decide whether to (a) add the missing fields to
      `glc_v5` as part of the parallel GLC migration, or (b) keep a thin
      compatibility shim inside the new `agent/` domain until Plan 04 of the
      GLC roadmap lands. Do not fork a second standalone `llm_gateway`
      process back into existence to route around the mismatch.

### 2. MCP tool server ownership

`mcp_server` is currently a personal folder outside any repo
(`~/Documents/AI Code/mcp_server`), reached only via `AI_CODE_ROOT`. That is
not a viable dependency for an AI OS Gateway domain.

- [ ] **Option A — vendor it in.** Bring `mcp_server` into the AI OS tree
      (submodule or import, same history-preservation question as `glc_v5`)
      as a sibling the `agent/` domain can depend on explicitly.
- [ ] **Option B — dissolve the process boundary.** Several `mcp_server`
      tools (`knowledge_graph`, `vector_db`, `documents`) look like they
      already wrap capabilities that ingestion/GLC/Database expose within
      this same monorepo. If so, the stdio MCP hop may be a historical
      artifact of the agent living in an unrelated workspace, not a real
      isolation requirement — worth asking whether those tools become direct
      in-process calls into gateway domains instead, with only genuinely
      external tools (finance, news, research, media) keeping an MCP-style
      boundary.
- [ ] Whichever option: fix the `AI Code/agent` / `AI Code/mcp_server`
      hardcoded personal-folder assumptions everywhere they appear (agent
      side and mcp_server side) so nothing depends on a path outside the AI
      OS repo.

### 3. Git history policy for `AI Agent/` — and which checkout is canonical

- [ ] First resolve finding 4: `~/Documents/AI Code/AI Agent` and
      `AI OS/AI Agent` are two separate git repos with (currently) identical
      `src/` content. Decide which one is canonical before importing
      anything — importing `AI OS/AI Agent`'s history is only correct if it
      is actually the checkout in active use, not a stale copy left behind
      when `AI OS` was split out of the old `AI Code` workspace. Check both
      repos' commit logs/dates to see which one has been the one actually
      edited.
- [ ] Once the canonical checkout is identified, decide the same way Plan
      01/Phase 2 of the GLC dismantle doc did: history-preserving
      subtree/import vs. a single migration-snapshot commit. The canonical
      repo has only 4 commits and no remote, so a full-history import is
      cheap here — default to that unless there's a reason not to.
- [ ] Confirm current uncommitted work in the canonical `AI Agent/` should be
      committed to its own repo first (Phase 0), not folded into the
      migration diff.
- [ ] Decide what happens to the non-canonical duplicate (delete it, or
      leave it and document that it's dead) so a future investigation
      doesn't rediscover the same ambiguity.

### 4. Chat UI ownership

- [ ] Approve retiring `app_planner.py`'s standalone HTML/JS chat UI in favor
      of a shell-hosted chat page calling `/api/agent/*`, consistent with how
      ingestion's UI already lives in `shell/` rather than as its own served
      HTML.
- [ ] Decide whether file-upload-to-Gemini (`_upload_to_gemini` in
      `app_planner.py`) is still wanted, and if so where it belongs (agent
      domain vs. a shared upload utility other domains could also use).

### 5. State storage location

- [ ] Decide whether `data/state/` (FAISS index, `memory.json`) and
      `data/sandbox/` move under the root `Database/` (matching the GLC
      roadmap's "root `Database/` remains the data location unless a separate
      storage migration is explicitly approved") or stay agent-domain-local
      under `gateway/`. Either is defensible; make it explicit rather than
      letting it default silently.

## Proposed target structure

Following Plan 02's gateway foundation shape (`src/gateway/app/`,
`src/gateway/platform/`) and the ingestion precedent
(`app.include_router(create_router(service), prefix="/api/ingestion")`):

```text
gateway/src/gateway/
├── app/
│   └── main.py                  # adds: app.include_router(agent_router, prefix="/api/agent")
├── platform/                    # shared with ingestion/GLC (Plan 02)
└── agent/
    ├── api/
    │   ├── routes.py            # /api/agent/* — chat, upload, memory inspection
    │   └── schemas.py
    ├── cognition/
    │   ├── perception.py
    │   ├── decision.py
    │   ├── action.py            # MCP dispatch or direct in-process calls (Decision 2)
    │   └── memory.py
    ├── services/
    │   ├── vector_index.py
    │   └── artifacts.py
    ├── llm_client.py            # replaces gateway.py; calls glc_v5, no subprocess spawn
    ├── orchestrator.py          # replaces agent7.py's loop, minus the CLI entrypoint
    └── tests/
```

The standalone CLI (`uv run agent "..."`) can remain as a thin script that
imports the same orchestrator, for local debugging — it just stops being the
only way to run the agent.

## Migration plan

### Phase 0: Protect and characterize the current agent

- [ ] Commit the current uncommitted work in `AI Agent/`'s own repo (or
      explicitly discard it, with Aryaman's confirmation — do not fold
      in-progress unrelated changes into the migration diff).
- [ ] Write characterization tests for the five-stage loop, memory
      read/write, vector search, and artifact put/get against the current
      behavior, before moving any code. This is the test suite item 6 above
      is missing.
- [ ] Empirically confirm whether the agent can boot at all today (finding
      2): try the documented `AI_CODE_ROOT` override, try no override, and
      record whatever actually happens. If a working configuration exists
      that isn't documented anywhere, write it down. If nothing boots the
      LLM path, that's the behavior to record — don't spend time trying to
      resurrect the old `llm_gateway` process just to capture a trace of it;
      go straight to characterization tests written against a stubbed/
      recorded LLM+MCP backend instead, since a live "old world" trace may
      not be obtainable at all.
- [ ] Resolve finding 4's canonical-checkout question (Decision 3) with an
      actual live call to `index_document`/`search_knowledge` through
      `mcp_server` pointed at whichever checkout is canonical, not just a
      source read. Update or remove the stale regression note in
      `README.md`/`TODO.md` based on the result.
- [ ] Resolve Decision 1 (LLM backend compatibility) with recorded fixtures
      before Phase 3 depends on the answer.

Exit condition: agent behavior is reproducible from tests and fixtures, not
memory; the mcp_server status is confirmed rather than assumed; the backend
compatibility question has evidence, not a guess.

### Phase 1: Import history into the gateway repository

- [ ] Apply the git-history policy from Decision 3.
- [ ] Import `AI Agent/` under a clearly marked migration path inside the
      gateway repo (or wherever the monorepo's history-import convention
      lands per the parallel GLC Phase 2 work — reuse one convention for
      both).
- [ ] Keep the original `AI Agent/` directory until the imported code passes
      the Phase 0 characterization tests.

Exit condition: agent source exists inside the gateway-owning repository
with history intact and traceable (`git log --follow`).

### Phase 2: Land on the gateway foundation

Blocked on Plan 02 (`GLC and ingestion gateway migration/02-gateway-foundation.md`)
landing first — the agent domain should be built directly against the typed
dependency container and service registry that plan introduces, not against
today's thin `gateway/main.py`.

- [ ] Register the agent as a domain service constructed during gateway
      lifespan (typed, injected — no new module-level globals, matching Plan
      02's dependency rule).
- [ ] Add the agent's LLM/embedding backend and (per Decision 2) MCP/tool
      dependency to `config/services.yaml`.
- [ ] Remove `gateway.py`'s `ensure_gateway()` subprocess-spawn logic and the
      `AI_CODE_ROOT` sibling walk-up once the backend is resolved through the
      service registry instead.

Exit condition: the agent domain constructs and tears down through gateway
lifespan; no code path still searches for a sibling `llm_gateway`/`mcp_server`
directory outside the repo.

### Phase 3: Move the cognition loop and memory services

- [ ] Move `schemas.py`, `cognition/*.py`, `services/*.py` into
      `gateway/src/gateway/agent/` per the target structure.
- [ ] Replace `agent7.py`'s orchestration with `orchestrator.py`, keeping a
      thin CLI wrapper if still wanted.
- [ ] Wire memory/artifact persistence to the location decided in Decision 5.
- [ ] Re-run the Phase 0 characterization tests against the moved code.

Exit condition: the loop runs correctly from inside the gateway process
using the moved modules; no import still points back at the old
`AI Agent/src` tree.

### Phase 4: Replace the standalone chat UI

- [ ] Add `/api/agent/*` routes (chat turn, file upload, memory inspection)
      following the ingestion router's shape.
- [ ] Build the chat surface in `shell/` per Decision 4, retiring
      `app_planner.py`'s inline HTML.
- [ ] Preserve the Gemini file-upload flow if Decision 4 kept it, wired
      through the new routes instead of a standalone endpoint.

Exit condition: chatting with the agent works end-to-end through the AI OS
Gateway's normal port and shell, with no second `uvicorn` process needed.

### Phase 5: Resolve the MCP/tool dependency

Scope and steps depend entirely on Decision 2's outcome (vendor mcp_server
in vs. dissolve the process boundary for in-repo tools). Do not begin this
phase until that decision is made — it changes the shape of `action.py`
significantly either way.

Exit condition: every tool the agent can call resolves to something inside
the AI OS repository or an explicitly approved external service; nothing
depends on `~/Documents/AI Code/*` outside this repo.

### Phase 6: Retire the standalone `AI Agent/` project

- [ ] Confirm all Phase 0 characterization tests plus any new domain tests
      pass against the gateway-hosted version.
- [ ] Confirm no runtime path still imports from the old `AI Agent/src`
      location.
- [ ] Archive or remove the original `AI Agent/` directory only after the
      above is pushed and recoverable, matching the GLC plan's "no submodule
      is removed until its replacement is pushed and recoverable" rule.

## Explicitly out of scope for this move

- Fixing any of the `TODO.md` memory/artifact design debt (unsearchable
  offloaded content, missing GC, classifier temperature, etc.) — track those
  as their own follow-ups after the structural move, per the GLC program
  rule separating structural and behavioral changes.
- Building parallel tool firing or the HITL round-cap-break feature.
- Redesigning the five-stage loop itself.
- Deciding `glc_v5`'s or ingestion's own internal restructuring — this plan
  only depends on their external contracts.

## Risks and controls

**Nothing currently proves `glc_v5` can serve as a drop-in `llm_gateway`
replacement.** Control: Decision 1's fixture comparison happens before any
code deletion, not after.

**The MCP tool server is the one dependency with no repo of record at all.**
Control: Decision 2 is resolved explicitly, in writing, before Phase 5 —
this is the one place where "just move the folder" isn't an option because
there is no folder inside this repo to move yet.

**Zero test coverage means regressions are invisible.** Control: Phase 0's
characterization tests are a hard prerequisite for Phase 1, not a
nice-to-have — this is the one place this migration cannot reuse an existing
passing suite the way GLC/ingestion could.

**Stale documentation has already caused one wasted-effort risk** (the
mcp_server regression that turned out to be fixed). Control: Phase 0
requires a live verification, not a re-read of the existing docs, before
anything in this plan treats a documented "known issue" as still true.

## Definition of done

1. The AI OS Gateway can serve a full agent chat turn, including tool calls,
   without spawning any subprocess outside its own lifespan-managed
   services.
2. No runtime code path references `AI_CODE_ROOT`, `~/Documents/AI Code/`,
   or any path outside the AI OS repository.
3. The agent's chat UI is part of the shared `shell/`, not a second FastAPI
   process bound to port 8000.
4. `glc_v5` (or its gateway-migrated successor) is the agent's only LLM/
   embedding backend, with the compatibility question from Decision 1
   resolved with evidence.
5. The MCP/tool dependency question (Decision 2) has a resolved, documented
   answer reflected in the actual code, not left as an open question.
6. A characterization test suite exists and passes against the gateway-hosted
   agent.
7. `AI Agent/`'s git history is preserved in the chosen location.
8. The original standalone `AI Agent/` directory is removed only after the
   above is pushed and recoverable.

## Aryaman's comments

Add corrections, constraints, or desired end-state details here — especially
on Decisions 1–5, since each blocks a later phase.
