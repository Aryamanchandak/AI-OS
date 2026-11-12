# AI Agent (EAGV3 — Session 7)

A small typed cognitive agent: a five-stage loop over an MCP tool server,
with FAISS-backed vector memory and on-demand document indexing.

```
memory.read → perception.observe → decision.next_step → action.execute → memory.record_outcome
```

## Layout

```
src/agent/
├── schemas.py            typed data contracts (no local deps)
├── gateway.py            LLM + embedding gateway bridge (locates the workspace root)
├── cognition/
│   ├── perception.py     maintains goal state across iterations
│   ├── decision.py       one LLM call/turn: answer or call one tool
│   ├── action.py         MCP dispatch; large results → artifact store
│   └── memory.py         typed memory service (vector-first, keyword fallback)
├── services/
│   ├── vector_index.py   FAISS IndexFlatIP wrapper
│   └── artifacts.py      content-addressable byte store
├── agent7.py             orchestrator / entry point
└── app_planner.py        FastAPI chat UI

data/                     runtime state (git-ignored)
├── state/                index.faiss, index_ids.json, memory.json, artifacts/
└── sandbox/              upload staging for app_planner

docs/                     design notes and reports
tests/                    (pytest configured; currently empty)
```

## External dependencies (siblings, not vendored)

This component is **not self-contained**. It shells out to three siblings in
the parent `AI Code/` workspace, located at runtime by walking up from
`gateway.py` to the directory that contains both:

- `AI Code/llm_gateway/` — the shared LLM + `/v1/embed` gateway (auto-started on port 8107)
- `AI Code/mcp_server/`  — the MCP tool server
- `AI Code/.venv/`        — the root Python used as a gateway launch fallback

If the workspace lives elsewhere, set `AI_CODE_ROOT` to override the search.

> ⚠️ **Known regression after the src/ restructure:** `mcp_server` imports this
> agent's `memory`/`artifacts` modules (for the `index_document` /
> `search_knowledge` tools) via a stale `AI Code/agent` path that no longer
> exists. Those two tools are currently broken; the 3-line fix lives in
> `mcp_server/` (outside this repo) and is documented in
> [`docs/RESTRUCTURE_PLAN.md`](docs/RESTRUCTURE_PLAN.md). All other MCP tools are
> unaffected.

## Setup

```sh
uv sync          # creates .venv and installs the `agent` package (src layout)
cp .env.example .env   # then fill in real keys  (see Configuration)
```

## Configuration

Runtime keys are read from `.env` at the repo root (git-ignored). Notable keys:
`GEMINI_API_KEY` (file uploads), `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`,
`SEMANTIC_SCHOLAR_API_KEY`, and the `LLM_*` / `EMBED_*` gateway settings.

## Run

```sh
# One-shot query (console script, or the module form):
uv run agent "What is the current time in Asia/Tokyo and Asia/Kolkata?"
uv run python -m agent.agent7 "..."

# Web chat UI at http://127.0.0.1:8000
uv run python -m agent.app_planner
```
