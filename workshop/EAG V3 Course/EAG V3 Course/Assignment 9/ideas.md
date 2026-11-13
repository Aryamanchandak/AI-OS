# Assignment 9 — how we solve it

## What we actually have

Two zips, not yet a repo:

- `llm_gatewayV9/` — the LLM gateway service (FastAPI, port **8109**). Provides
  `/v1/chat`, `/v1/vision`, `/v1/cost/by_agent`, `/v1/calls`, a SQLite call ledger,
  provider routing/failover, and a dashboard.
- `S9SharedCode/code/` — the agent runtime. This is a **working S9 baseline**, not a
  scaffold.

### Already built (do NOT re-build these)

| Piece | Where |
|---|---|
| Growing-graph orchestrator (planner → skills → critic → formatter) | `flow.py` |
| Skill catalogue (yaml + markdown prompt per skill) | `agent_config.yaml`, `prompts/*.md` |
| Browser skill with the full 4-layer cascade: extract → deterministic → a11y → vision | `browser/skill.py` |
| Set-of-marks vision driver + a11y driver, action vocabulary (click/type/key/scroll/drag/wait/done) | `browser/driver.py`, `browser/dom.py`, `browser/highlight.py` |
| `gateway_blocked` detection (CAPTCHA / Cloudflare / login wall) → typed `error_code` → planner re-plan | `browser/skill.py`, `recovery.py` |
| Per-node persistence: inputs, status, `prompt_sent`, full `AgentResult`, timings, `graph.pkl` | `persistence.py`, `schemas.py` |
| Per-turn artifacts: raw screenshot, marked screenshot, a11y legend | written to `state/sessions/<sid>/browser/<layer>/turn_NN_*` |
| Cost/turn ledger per agent tag | gateway `/v1/cost/by_agent?session=...` |
| Terminal replay stepper | `replay.py` |

`VALIDATION.md` documents an end-to-end Hugging Face top-3 run that already exercised
search → filter → sort on the a11y path. That is 80% of the assignment's browser
requirement, already proven.

### The constraint, decoded

> "The orchestrator must not be modified."

That means **`flow.py`**. Fair game: `agent_config.yaml`, `prompts/*.md`, extensions
inside `browser/`, and brand-new standalone scripts. The report generator is a new
read-only script — it never touches the orchestrator, which is exactly why this
approach is safe.

---

## The four real gaps

### Gap 1 — The replay viewer (the centerpiece, ~60% of the marks)

`replay.py` is a terminal stepper. It shows no screenshots, no DAG, no cost summary.
But here is the key insight: **7 of the 8 required elements are already persisted to
disk.** This is an assembly job, not a data-collection job.

| # | Required element | Already on disk as |
|---|---|---|
| 1 | Original user goal | `state/sessions/<sid>/query.txt` |
| 2 | Planner DAG | `graph.pkl` + each node's `inputs` |
| 3 | Browser path chosen | `BrowserOutput.path` (`extract`/`deterministic`/`a11y`/`vision`) or `error_code="gateway_blocked"` |
| 4 | Browser actions taken | `BrowserOutput.actions` — per-turn `{turn, actions, outcome}` |
| 5 | Screenshots / page-state logs | `browser/<layer>/turn_NN_raw.png`, `turn_NN_marked.png`, `turn_NN_legend.txt` |
| 6 | Extracted data | `BrowserOutput.content`, distiller `fields` |
| 7 | Final comparison table | formatter `final_answer` — **needs prompt work, see Gap 2** |
| 8 | Turn count + cost | `turns`, `elapsed_s` per node + gateway `/v1/cost/by_agent` |

**Plan:** write `report.py <session_id>` — reads `state/sessions/<sid>/`, hits
`/v1/cost/by_agent?session=<sid>`, emits one self-contained `report.html` with
screenshots inlined as base64 data URIs. Sections in the exact 1–8 order of the brief.
Render the DAG as an inline Mermaid `graph TD` block (nodes coloured by status:
complete / failed / skipped) — no external libraries, no build step.

This is also the best thing to film for the YouTube demo: scroll the report top to
bottom while narrating.

### Gap 2 — The comparison table

Today the distiller emits a **flat** `{"fields": {...}}` dict and the formatter writes a
numbered list. Neither produces an N-row × M-column table. Fix in the prompts only:

- `prompts/distiller.md` — add a `rows` output shape:
  `{"columns": [...], "rows": [{...}, {...}], "rationale": "..."}`, one row per compared
  item, with a `source_url` column so every cell is traceable.
- `prompts/formatter.md` — when INPUTS contain `rows`/`columns`, render a Markdown
  table verbatim and never drop or invent a row.
- The critic already auto-inserts after the distiller (`critic: true`), so a fabricated
  row gets caught for free — worth showing in the demo.

### Gap 3 — Task choice + one clean run

Pick **Hugging Face text-generation models sorted by likes**. Reasons:

- Already proven to work on the a11y path (`VALIDATION.md` §HF).
- Not CAPTCHA-walled. `VALIDATION.md` shows Redfin is — so avoid Amazon / Flipkart /
  Redfin-class anti-bot retail, or the run demonstrates `gateway_blocked` instead of a
  comparison.
- The filter/sort widgets are genuinely JS-driven, which is the whole point of the brief.
- Detail pages (model cards) give a natural second browser hop for per-item fields.

Suggested DAG (the planner will emit this if the prompt nudges it):

```
planner
  └─ browser  (huggingface.co/models — filter Task=Text Generation, sort by Likes,
               read top 3 model ids)                    ← actions 1,2,3
       ├─ browser  (model card #1 — expand files/params)  ← action 4
       ├─ browser  (model card #2)
       ├─ browser  (model card #3)
       └─ distiller → critic → formatter
```

That is 4+ visible actions (search/filter, sort, open detail, expand), comfortably
clearing the "at least three" bar.

**Backup task if HF's UI shifts:** compare 5 AI coding tools by free vs paid plan —
pricing pages are JS-rendered with monthly/annual toggles and expandable tiers, and
none of them are CAPTCHA-walled.

### Gap 4 — Submission artifacts

YouTube demo, GitHub repo, replay trace/log, final comparison output, architecture note
(1–2 pages: the cascade, why each layer, the escalation rule, the "orchestrator
untouched" boundary).

---

## Suggested order of work

1. **Set the repo up and prove it runs.** Merge both zips into one repo, `git init`,
   `uv sync`, `playwright install chromium`, start the V9 gateway on :8109, add a
   provider key. *Blocker: no API key ships in `.env.example` — only `TAVILY_API_KEY`.
   You'll need a Gemini free-tier key (what VALIDATION.md used).*
2. **Baseline run.** `uv run python flow.py "<HF comparison query>"` — confirm a
   `state/sessions/<sid>/` directory appears with browser artifacts. Nothing else is
   worth building until one trace exists on disk.
3. **Prompt work** (Gap 2): distiller `rows` schema + formatter table rendering.
4. **`report.py`** (Gap 1) — the big one. Build it against the trace from step 2.
5. Re-run clean, generate the final report, record the demo, write the architecture note.

## Risks worth naming up front

- **No provider key = nothing runs.** This is the single hard blocker; resolve it first.
- **HF a11y run took ~17s and 4 turns.** Fine, but the a11y driver can burn its 12-turn
  cap on a dropdown it can't see. If it flakes, `metadata.selectors` (Layer 2a,
  deterministic) is the documented escape hatch — and switching layers mid-demo is
  actually a *good* story for the "cheapest correct path" part of the brief.
- **Don't force `force_path`.** The natural cascade choosing its own layer is what the
  brief is asking you to demonstrate. `VALIDATION.md` §8 is honest that natural vision
  escalation is rare — if you want a vision-path run for the report, use a canvas-only
  page as a *second* session rather than distorting the main comparison run.
