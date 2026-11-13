# Assignment 9 — Browser Comparison Agent + Replay Viewer

A browser-driving agent that completes a real comparison task on a
JavaScript-rendered site and renders the whole run as a self-contained HTML
replay report.

- **Architecture note:** [ARCHITECTURE.md](ARCHITECTURE.md)
- **Planning / gap analysis:** [ideas.md](ideas.md)
- **Integration evidence from the shared baseline:** [S9/code/VALIDATION.md](S9/code/VALIDATION.md)

## Layout

```
llm_gatewayV9/        LLM gateway service (FastAPI, :8109) — routing, failover,
                      /v1/chat, /v1/vision, and the SQLite cost ledger
S9/code/              the agent
  flow.py             growing-graph orchestrator          [UNMODIFIED]
  skills.py           skill dispatch                      [UNMODIFIED]
  browser/            the four-layer cascade + drivers
  prompts/*.md        one prompt per skill                [MODIFIED — see below]
  agent_config.yaml   the skill catalogue
  report.py           the replay viewer                   [NEW]
  make_fixture.py     synthetic session for demoing the viewer [NEW]
  replay.py           the original terminal stepper
  tests/test_report.py                                    [NEW]
```

The two top-level directories must stay siblings — `S9/code/gateway.py` locates
the gateway with `parents[2] / "llm_gatewayV9"`.

## Setup

```bash
# 1. the gateway
cd llm_gatewayV9
uv sync
cp .env.example .env        # then add a provider key (see below)
uv run main.py              # serves on :8109

# 2. the agent, in a second shell
cd S9/code
uv sync
uv run playwright install chromium
```

**You need an LLM provider key.** Nothing in the repo ships one. Verified on a
clean checkout: the gateway starts fine, but `/v1/providers` returns
`{"order":[],"providers":[]}` and every skill call then fails with

```
[n:1] planner  failed  err=exception: HTTPStatusError: Server error '503 Service Unavailable'
```

Create `llm_gatewayV9/.env` with at least one provider key. The runs documented
in `VALIDATION.md` used free-tier Gemini, which is why every cost row reads
`$0.000000`:

```bash
GEMINI_API_KEY=...          # what VALIDATION.md used; free tier is enough
# any of these also register a provider:
# GROQ_API_KEY= / CEREBRAS_API_KEY= / NVIDIA_API_KEY= /
# OPEN_ROUTER_API_KEY= / GITHUB_ACCESS_TOKEN=
# (ollama needs no key but must be running locally)
```

Confirm before running the agent — `/v1/providers` must list a non-empty
`order`:

```bash
curl -s http://localhost:8109/v1/providers | python3 -m json.tool | head
```

## Running a comparison

```bash
cd S9/code
uv run python flow.py "Compare the top 3 Hugging Face text-generation models \
sorted by likes. For each give the model name, parameter count, likes, and a \
one-line description."
```

The run prints its session id (`s8-xxxxxxxx`). Then:

```bash
uv run python report.py <session_id> --open
```

That writes `<session_id>_report.html` — one self-contained file, no CDN, no
JavaScript — covering all eight required elements:

| § | Element | Source |
|---|---|---|
| 1 | Original user goal | `query.txt` |
| 2 | Planner DAG | `graph.json`, rendered as inline SVG |
| 3 | Browser path chosen | `BrowserOutput.path` / `error_code` |
| 4 | Browser actions taken | `BrowserOutput.actions`, per turn |
| 5 | Screenshots & page-state logs | `browser/<ts>/<layer>/turn_NN_*` |
| 6 | Extracted data | browser content, distiller rows, critic verdict |
| 7 | Final comparison table | formatter `final_answer`, Markdown → HTML |
| 8 | Turn count & cost | per-node timings + gateway ledger |

Other flags: `--list` (show sessions), `-o PATH`, `--no-gateway` (skip the cost
fetch when the gateway is down — the rest of the report still renders).

## Seeing the viewer without a provider key

`make_fixture.py` writes a **synthetic session** — hand-written JSON in the exact
shapes `flow.py` persists, with generated placeholder screenshots. It exists so
the viewer can be developed and demonstrated without burning API calls. **It is
not a real agent run**: no browser was driven and no page was visited. Do not
present it as one in the demo.

```bash
uv run python make_fixture.py
uv run python report.py s9_fixture --no-gateway --open
```

## Tests

```bash
cd S9/code && uv run pytest tests/test_report.py -q     # 17 passed
```

The viewer tests cover the failure paths, not just the happy one: a
`gateway_blocked` browser node, a failing critic verdict, a run with no
formatter, ragged table rows, an empty a11y legend, and artifact-to-node
matching when two browser nodes run concurrently.

## What was changed from the shared baseline

The orchestrator is untouched. `flow.py`, `skills.py`, `persistence.py`,
`recovery.py`, `schemas.py` and everything under `browser/` are byte-identical
to the shared code.

| File | Change |
|---|---|
| `prompts/distiller.md` | added the comparison shape: `{columns, rows[], comparison}`, one row per item, `source_url` on every row, `"not stated"` rather than a dropped key |
| `prompts/formatter.md` | render `columns`/`rows` verbatim as a Markdown table, then a short takeaway |
| `prompts/critic.md` | check tables for ragged rows, fabricated cells, invented URLs, and unexplained row-count shortfalls |
| `prompts/planner.md` | the two-hop listing-site comparison shape, and a rule that the distiller node names its columns explicitly |
| `report.py` | **new** — the replay viewer |
| `tests/test_report.py` | **new** |

## Status

**Done and verified**

- `report.py`, all eight sections. Verified two ways: against a synthetic
  fixture, and against a real session persisted by an actual `flow.py` run
  (a failed one — see below) with the live gateway ledger attached.
- 17 viewer tests, weighted toward failure paths. Full suite: 46 passed.
- Repo layout, `.gitignore`, architecture note. Diff-verified that the
  orchestrator and the gateway are byte-identical to the shared baseline.

**Done but NOT yet validated against a live model**

- The prompt changes (distiller `rows`, formatter table rendering, critic table
  checks, planner two-hop shape). These are the comparison-table deliverable and
  no LLM has executed them yet — the unit tests exercise `report.py`'s handling
  of the resulting JSON, not the model's ability to produce it. Expect one or
  two rounds of prompt tuning after the first real run.

**Not done — blocked on a provider key**

- The live end-to-end comparison run. A `flow.py "hello"` smoke was attempted
  and failed at the planner with a gateway 503 because no provider is
  registered. Once a key is set, run the HF comparison, regenerate the report
  from that real session id, and walk *that* report through in the demo video.
- YouTube demo and the final comparison output both depend on that run.
