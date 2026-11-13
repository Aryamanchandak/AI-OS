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
  skills.py           skill dispatch                      [MODIFIED — see below]
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
cp ../.env.example ../.env  # then add a provider key (see below)
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

Create `Assignment 9/.env` (beside this README) with at least one provider key.
The gateway loads that parent file, not `llm_gatewayV9/.env`. The runs documented
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

The current example is a beginner moving from treadmill to road running:
men's UK 11, USD 200 per pair, delivery to Mumbai. The confirmed profile is
`S9/code/examples/beginner_runner.yaml`; its request is `beginner_runner.md`
in the same directory. Live INR prices need a dated exchange-rate source.
No real retailer comparison has been completed yet. The Hugging Face command
below is the supplied baseline example.

For a key-free integration check, run `uv run python dry_run_shoes.py` inside
`S9/code`. It runs real Chromium against local fictional shops through the
unchanged course executor, with scripted model responses and memory disabled.
It writes a session, comparison output, summary and `shoes_report.html` under
`state/sessions/s9-shoes-dry-<id>/`. All prices and stock are fictional; this
checks browser/runtime/report wiring, not live retailer access or model quality.

After keys are configured, supply both the request and its profile to the live
agent from `S9/code` (the planner cannot read a YAML file merely named in a prompt):

```bash
uv run python flow.py "$(cat examples/beginner_runner.md examples/beginner_runner.yaml)"
```

This reads both files and passes their combined text as the agent's request.

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

The orchestrator (`flow.py`), `persistence.py`, `recovery.py` and `schemas.py`
are untouched. Browser drivers now retain visited page text and pass it to
the model; `skills.py` includes original source inputs in critic prompts and
preserves complete input records rather than silently clipping later sources.
These changes prepare the multi-retailer shoe example without editing the
orchestrator. They are covered by `tests/test_comparison_evidence.py`.

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
- Full local suite: 67 passed, including the real-Chromium key-free shoe run,
  profile/eligibility cases, source-evidence regressions, and HTTP access blocks.
  The dry run selected 3 fictional shoes, excluded 3, and recorded 24 actions.
  Its generated report is review evidence, not a live assignment submission.
- Repo layout, `.gitignore`, architecture note. The orchestrator remains
  byte-identical to the supplied course ZIP.

**Done but NOT yet validated against a live model**

- The prompt changes (distiller `rows`, formatter table rendering, critic table
  checks, planner two-hop shape). These are the comparison-table deliverable and
  no LLM has executed them yet — the unit tests exercise `report.py`'s handling
  of the resulting JSON, not the model's ability to produce it. Expect one or
  two rounds of prompt tuning after the first real run.

## Submission to-do

- [ ] Configure a provider key in `Assignment 9/.env`; never commit the key.
- [ ] Run the real shoe comparison using the confirmed beginner-runner profile.
- [ ] Manually verify the exact men's UK 11 variants, stock, Mumbai delivery,
      prices, dated USD–INR conversion, and evidence behind suitability judgments.
- [ ] Confirm at least three successful browser interactions and all eight
      required replay sections, including actual turn counts and usage/cost.
- [ ] Package the real final table, trace/log, screenshots and replay report;
      generated outputs are currently excluded from Git. Label dry-run data
      separately and use the real run as submission evidence.
- [ ] Update this README and the architecture note with the verified outcome
      and reproduction instructions. Fix code only where the real run exposes gaps.
- [ ] Record and upload the YouTube demo showing the request, browser actions,
      final comparison and replay report.
- [ ] Review the final changes, commit and push after approval, and confirm
      the instructor can access the GitHub repository, evidence and video.
