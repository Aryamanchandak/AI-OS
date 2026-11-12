# Decompose podcast-brief into MCP tools

> **Status:** approved plan, not yet implemented. Lives alongside `V3_PLAN.md` /
> `WORKFLOW.md`. Implementation is intended to happen in a fresh session.

## Context

`podcast-brief` is today a single linear pipeline (`core/pipeline.py :: run_pipeline`)
that every entry point — CLI, daily poller, iOS HTTP endpoint — funnels through. The
stages are `ingest → transcribe → extract → research → synthesize → format → deliver`.

We want to **expose the pipeline as MCP tools** so any MCP client can drive it: both
Claude Desktop / conversational use *now*, and the V3 agentic orchestrator *later*
(this is the "V3.1 — MCP exposure" milestone in `V3_PLAN.md`, pulled forward and scoped
to one server instead of per-agent servers).

Decisions locked with the user:
- **Consumer:** general-purpose (Claude Desktop today, V3 agents later).
- **Granularity:** per-stage tools **+** a high-level orchestrator tool.
- **Transport:** a **single HTTP server** (Streamable HTTP), reusing the existing
  Tailscale/FastAPI exposure in `interface/server.py`.
- **Types:** **Pydantic everywhere** — every stage I/O and every MCP tool I/O is a
  Pydantic model (Step 1). Also satisfies `V3_PLAN.md` pre-flight step 2.
- **No async, no concurrency in our layer.** Runtime is not a priority; **not exhausting
  Anthropic/Deepgram rate limits and code solidness are.** LLMs are called strictly one at
  a time, sequentially. No fan-out, no `asyncio` in the tool layer (Step 4).
- **`generate_brief` is automation, not agentic.** It calls each stage **in code, in a
  fixed order, one by one** — the ordering is never left to a model/prompt (Step 5).

### The key design idea: disk is the bus

MCP tools are stateless across calls and exchange JSON, so we cannot pass live objects
between tool calls. We don't need to — the pipeline already **persists most stage outputs
to disk keyed by `episode_id`** (audio MP3, cached transcript JSON, brief `.md`/`.html`,
SQLite `episodes`/`runs`). Each per-stage tool: takes an `episode_id`, **re-loads** its
inputs from disk, runs its stage, **persists** its output, returns a **compact Pydantic
result** (counts, paths, status).

Two stage outputs are **not yet persisted** and must be: `ExtractionResult` and the
research `SurfacedItemWithClaim[]`. With Pydantic this is trivial
(`model_dump_json` / `model_validate_json`).

---

## Step 1 — Pydantic everywhere (foundational; do first)

Replace the scattered `@dataclass`es with Pydantic v2 `BaseModel`s. `pydantic>=2.0` is
**already a dependency**. New file `core/models.py` holds the shared models; existing
modules import from it.

| Current dataclass | File today | Migration note |
|---|---|---|
| `EpisodeInfo`, `RSSEpisode` | `ingestion/ingest.py` | move to `core/models.py` |
| `Segment`, `Transcript` | `transcription/transcribe.py` | keep methods (`to_prompt_format`, `duration_seconds`, `timestamp`) — BaseModel supports methods & `@property`/`@computed_field`. `asdict`→`model_dump`; `save`/`load`→`model_dump_json`/`model_validate_json` |
| `Claim`, `ExtractionResult` | `extraction/extract.py` | `to_dict`→`model_dump`; persistence via `model_validate_json` |
| `SurfacedItemWithClaim` | `research/mcp_bridge.py` | real model with nested `LogicalSource` + nested `Claim` (no more `claim: object`) |
| `ShowConfig` | `core/config.py` | keep `slug` as `@property` |

**Mechanical pattern** (across `ingest.py`, `transcribe.py`, `extract.py`,
`synthesize.py`, `mcp_bridge.py`, `pipeline.py`): swap `dataclass`→`BaseModel`,
`asdict(x)`→`x.model_dump()`, JSON via `model_dump_json`/`model_validate_json`. Removes the
bespoke `to_dict`/`save`/`load`/`_parse_json_response` plumbing in favor of one consistent
mechanism.

## Step 2 — Artifact persistence for the two unsaved stages

- `core/config.py`: add `EXTRACTION_DIR = DATA_DIR/"extractions"`,
  `RESEARCH_DIR = DATA_DIR/"research_items"`; include both in `ensure_dirs()`.
- **Extraction:** persist `ExtractionResult` → `EXTRACTION_DIR/<id>.json`; load back.
- **Research:** persist `list[SurfacedItemWithClaim]` → `RESEARCH_DIR/<id>.json`
  (`TypeAdapter(list[SurfacedItemWithClaim]).dump_json(...)`); load the same way.
  `synthesize._format_research_mcp` consumes the same attributes unchanged.

## Step 3 — State read helpers (`core/state.py`)

Mirror `get_recent_episodes`:
- `get_episode(episode_id) -> dict | None`
- `get_runs(episode_id) -> list[dict]` (per-stage audit log — used as the verification gate)

## Step 4 — No async; sequential & rate-limit-safe

We deliberately do **not** introduce `asyncio` into the tool layer.

- **Every MCP tool is a plain sync `def`.** FastMCP runs sync tools in a worker thread, so
  they don't block the transport — without us writing any async code.
- **The research stage keeps its existing sync wrapper** `research_claims_via_mcp` (which
  internally does `asyncio.run` over Research_MCP). Because FastMCP calls our sync tool on a
  worker thread, that `asyncio.run` gets a fresh event loop in that thread and works
  correctly — **no nested-loop crash, and no async exposed in our code.** (This drops the
  earlier async-entry-point idea entirely.)
- **Strictly sequential LLM calls.** Our pipeline already calls Claude one stage at a time
  (extract → synthesize, plus the Haiku speaker pass). We keep it that way and add **no**
  concurrency/fan-out, so a single brief never issues parallel model calls.
- **Solidness against rate limits:** wrap the Anthropic/Deepgram calls in a small
  `tenacity` retry with exponential backoff that specifically honors HTTP 429
  (`tenacity` is **already a dependency** and currently unused). Centralize this in one
  helper (e.g. `core/llm.py :: call_anthropic(...)`) so extract/synthesize/speaker-resolve
  all share the same backoff policy. This is the main "code solidness" upgrade and directly
  serves "don't exhaust my rate limits."

## Step 5 — Stage functions + an in-code orchestrator (the heart of this change)

To make `generate_brief` *automation, not agentic*, the per-stage tools and the
orchestrator must share **one set of ordered, disk-keyed stage functions**.

**5a. Factor each stage into a disk-keyed function** (in `core/stages.py`, thin wrappers
over today's stage modules). Each takes an `episode_id` (+ minimal params), re-loads its
inputs from disk, runs, persists, and returns a Pydantic `*Result`:
`stage_ingest(url,…) → stage_transcribe(episode_id,…) → stage_extract(episode_id,…) →
stage_research(episode_id) → stage_synthesize(episode_id) → stage_deliver(episode_id,…)`.
Each logs its `runs` row (`started`/`completed`/`failed`) exactly as `run_pipeline` does now.

**5b. New `core/orchestrator.py :: process_episode(...)`** calls those stage functions
**in the fixed order, one by one, in plain Python** — carrying over the current
degrade-not-fail behavior (research failure → warn & continue; delivery failure → leave
markdown on disk) and the `transcript_only` / `skip_research` branches. This becomes the
single source of truth for stage order.

**5c. Both entry points delegate to it:**
- CLI `core/pipeline.py :: run_pipeline` → thin wrapper over `process_episode` (removes its
  inline stage logic; same observable behavior).
- MCP `generate_brief` tool → calls `process_episode`. So the "big" tool runs the exact
  same in-code sequence as a human stepping through the per-stage tools — order guaranteed
  by code, not a prompt.

## Step 6 — `interface/mcp_server.py` (the FastMCP server)

`from mcp.server.fastmcp import FastMCP`; `mcp = FastMCP("podcast-brief")`. Every tool is a
**thin sync wrapper** over a `core/stages.py` function or an existing helper. Tool I/O uses
Pydantic models from `core/models.py`.

**Per-stage tools** (all sync, disk-keyed): `ingest_audio`, `transcribe_episode`,
`extract_claims`, `research_claims`, `synthesize_brief`, `deliver_brief` → each wraps the
matching `stage_*` function and returns its `*Result`.

**Orchestrator tool:** `generate_brief(url, profile?, show?, transcript_only?,
skip_research?)` → calls `core.orchestrator.process_episode` (Step 5).

**Query / admin tools:** `list_recent_episodes`, `get_episode_status` (→ `state.get_episode`
+ `state.get_runs`), `list_shows`, `poll_shows`, `check_config` (refactor `cli.cmd_check`
into a reusable function returning a model).

**Resource:** `brief://{episode_id}` serves `data/briefs/<id>.md` so clients read full
briefs without bloating tool returns.

## Step 7 — Mount on the existing HTTP server + auth (`interface/server.py`)

`app.mount("/mcp", mcp.streamable_http_app())` — one process serves `/brief` and MCP.
Reuse `PODCAST_BRIEF_API_TOKEN` as middleware on the mount (keep local/no-token behavior).
Run: `uvicorn interface.server:app --host 0.0.0.0 --port 8765`.

## Step 8 — Packaging (`pyproject.toml`)

Add `mcp` (official SDK, ships FastMCP). Add stdio-fallback entry point
`podcast-brief-mcp = "interface.mcp_server:main"` (HTTP remains primary).

---

## Driving an agent through the tools (enforcing steps + verifying claims)

**1. Two modes:**
- **Automation (default) — `generate_brief(url)`** runs the whole defined sequence in code
  (Step 5), in order, sequentially, with degrade-not-fail. The order is enforced *in
  Python*, never by the model. Use this when you just want the brief.
- **Step-by-step (manual/inspection)** — call the six per-stage tools yourself on one
  `episode_id` when you want to pause and inspect between stages.

**2. Keeping a step-by-step run on the rails.** A short playbook
(`config/prompts/agent_playbook.md`, surfaced via the server instructions) states the
canonical order and the rule: *after each per-stage tool, call
`get_episode_status(episode_id)` and confirm the expected `runs` row is `completed` before
the next stage.* Because every stage writes a `runs` row, `get_episode_status` is a real
**verification gate** — you (or a client) can see exactly where it is and refuse to skip.
Pydantic-typed returns give a validated object at each step, not free text.

**3. Verifying claims (literal).** Claim verification *is* `research_claims`: each `Claim`
goes through Research_MCP triage + source-gathering, yielding per claim a
`triage_correctness` (`true`/`false`/`topic`), `triage_confidence`, and `logical_sources`.
Read them back from `RESEARCH_DIR/<id>.json` or the `brief://<id>` resource without
re-running.

---

## How the code changes, file by file

- `core/models.py` — **new.** All shared Pydantic models + tool `*Result` models.
- `core/stages.py` — **new.** Six disk-keyed `stage_*` functions (Step 5a).
- `core/orchestrator.py` — **new.** `process_episode` ordered sequence (Step 5b).
- `core/llm.py` — **new.** `call_anthropic` with tenacity 429 backoff (Step 4).
- `interface/mcp_server.py` — **new.** FastMCP server: tools, resource, `main()`.
- `interface/server.py` — mount MCP app; extend token auth to the mount.
- `core/pipeline.py` — `run_pipeline` becomes a thin wrapper over `process_episode`.
- `ingestion/ingest.py`, `transcription/transcribe.py`, `extraction/extract.py`,
  `summarisation/synthesize.py` — import models from `core.models`; Pydantic persistence;
  route Anthropic calls through `core/llm.py`.
- `research/mcp_bridge.py` — Pydantic `SurfacedItemWithClaim`/`LogicalSource`;
  add (de)serializer. **Stays sync** (keep `research_claims_via_mcp`).
- `core/config.py` — `EXTRACTION_DIR`, `RESEARCH_DIR`, `ensure_dirs`, `ShowConfig` model,
  extracted `check_config()`.
- `core/state.py` — `get_episode`, `get_runs`.
- `pyproject.toml` — add `mcp`; add stdio entry point.
- `MCP_PLAN.md`, `config/prompts/agent_playbook.md` — **new docs.**

**Reused as-is:** every stage's core function, `state.*`, `format.*`, `deliver.*`,
`poll.poll_all_shows`, `config.load_shows/find_show_by_url`.

---

## Verification

1. **Pydantic migration intact:** existing CLI path
   (`podcast-brief brief <url> --skip-research`) runs end-to-end.
2. **Orchestrator parity:** `run_pipeline` (now delegating to `process_episode`) produces
   the same result as before on a cached episode.
3. **Disk-as-bus seam:** `extract_claims` then `synthesize_brief` as **separate** tool
   calls produce the same brief as `generate_brief` in one shot.
4. **Server up:** `uvicorn interface.server:app --port 8765`; `GET /` health JSON intact;
   `/mcp` serves MCP.
5. **Protocol smoke test:** via MCP SDK client / `mcp dev`: `list_tools` shows every tool
   with Pydantic schemas; `check_config` + `list_recent_episodes` (free); `generate_brief`
   on a known URL with `skip_research=true` → lands in Readwise inbox.
6. **In-code ordering:** confirm `generate_brief` invokes stages in the fixed order with no
   model/prompt deciding sequence (inspect the `runs` rows: ingest→…→deliver in order).
7. **Sequential / rate-limit:** confirm no parallel LLM calls during one brief; force a
   simulated 429 and confirm the `tenacity` backoff retries rather than crashing.
8. **No async:** grep confirms no `async`/`await` in `interface/mcp_server.py`,
   `core/stages.py`, `core/orchestrator.py`; `research_claims` runs without a nested-loop
   error (sync tool on FastMCP worker thread).
9. **Claim verification:** after `research_claims`, `RESEARCH_DIR/<id>.json` has per-claim
   `triage_correctness` / `confidence` / `logical_sources`.
10. **External client:** Claude Desktop → HTTP MCP endpoint, one real query end-to-end.
