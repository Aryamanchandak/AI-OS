# UI Plan — fixing the interface

Three separate complaints, three very different costs. Sequenced so the cheap
fixes ship first and the expensive one is optional.

| # | Complaint | Real cause | Cost |
|---|-----------|-----------|------|
| 1 | Buttons/dropdowns white-on-white, black-on-black | Missing `.streamlit/config.toml` | ~6 lines |
| 2 | Slogans and platitudes | 4 hardcoded HTML blocks | deletion only |
| 3 | "Streamlit looks awful" | Streamlit's aesthetic ceiling | a port |

Do **1 and 2 first** — they are independent of any architecture decision. If the
port in Stage 2 stalls, you still have a fixed, working app.

---

## Diagnosis of the contrast bug (complaint 2)

There is no `.streamlit/` directory in the project. Without `config.toml`,
Streamlit's base theme follows the *viewer's OS light/dark preference*. Meanwhile
`main.py:261–927` injects 660 lines of CSS that hard-assumes a light cream
palette (`--paper: #f5f1e8`, `--ink: #17212b`). On a dark-mode machine, Streamlit
paints its native widgets with dark tokens while your CSS paints the page cream —
hence black-on-black.

The dropdown is a distinct, worse case. Streamlit's selectbox is a BaseWeb
component that renders its popover in a **portal appended to `document.body`**,
outside `[data-testid="stSidebar"]`. Every dropdown rule in the current CSS is
scoped under that sidebar selector (`main.py:438–483`), so those rules are
*structurally incapable* of reaching the open dropdown. No amount of tweaking
them will work.

There are 26 Streamlit-internal selectors (`data-testid=`, `data-baseweb=`) in
the CSS. They are the fragile part — they break on Streamlit upgrades. The
`:root` color tokens at `main.py:266–283` are fine and worth keeping.

---

## Stage 0 — fix contrast + delete the copy (do this first)

**0a. Pin the theme.** Create `.streamlit/config.toml` mapping the existing
tokens so native widgets and injected CSS agree:

```toml
[theme]
base = "light"
primaryColor = "#8b6118"          # --gold-deep
backgroundColor = "#f5f1e8"       # --paper
secondaryBackgroundColor = "#fffdf8"  # --surface
textColor = "#17212b"             # --ink
font = "sans serif"
```

**This is also the diagnostic.** After adding it, open the app and check the
selectbox popover and the primary button specifically.

- If contrast is correct → root cause confirmed, and the Stage 2 port becomes a
  purely aesthetic decision rather than a bug fix.
- If it is *still* broken → there is a second cause, and I want it identified
  before rebuilding anything, because it may not be Streamlit's fault.

**0b. Delete the platitudes.** Four blocks, all pure copy:

| Location | Content to cut |
|----------|----------------|
| `main.py:1140–1147` | Hero: *"Map the forces. See the futures."* + "four transparent worlds" paragraph |
| `main.py:1179–1187` | Sidebar "Method at a glance" card (6 rows of self-description) |
| `main.py:1322–1332` | *"Four worlds, one challenged causal spine"* + explainer paragraph |
| `main.py:1451–1460` | Empty state: *"Your scenario map starts with one situation."* |

Replace the hero with a plain title row. Replace the empty state with one
functional line. The `◈` brand mark, eyebrow kickers, and `--gold` accents go
with them — that's the layer generating the marketing tone.

Deleting these also removes ~180 lines of now-dead CSS (`.whatif-hero`,
`.whatif-eyebrow`, `.brief-card`, `.result-intro`, `.empty-state`).

**Ships independently. Nothing below is required to get value from Stage 0.**

---

## Stage 1 — extract the pipeline (do this regardless)

Worth doing whether or not you port. `main.py` is 1,463 lines with UI and
orchestration interleaved.

**`pipeline.py`** — lift `main.py:1201–1302` into:

```python
def run_pipeline(brief: str, mode: str, on_progress: Callable[[str, str], None]) -> dict
```

`on_progress(step_id, message)` replaces each `pipeline_status.write(...)` call.
Streamlit passes a closure writing to `st.status`; an HTTP server passes one that
pushes to an event queue. Same pipeline, either shell.

**Carry the failure semantics deliberately** — they are stated requirements in
WORKFLOW.md §"Failure behavior and session state" and marked `R2`/`R3` in the
code, not incidental behavior:

- research failure → degrade to brief-only graph construction, stay visible
- critic/adjudicator failure → retain the builder graph, expose the failure
- verification failure → all edges stay `unverified`
- **a failed run never overwrites the last completed analysis**

That last one is currently enforced by *not* assigning to
`st.session_state.analysis_run` on the failure path (`main.py:1295–1302`). In a
server it becomes: don't replace the stored result until the new job succeeds.

**`presentation.py`** — `graph_to_dot`, `cell`, `short_label`, `scenario_name`,
`all_assignments`, `edge_robustness` (`main.py:41–243`). Pure functions of the
dataclasses, no Streamlit imports. Confirmed safe: neither test file imports
from `main`, so nothing breaks.

`main.py` then keeps only rendering, and both tests keep passing untouched.

---

## Stage 2 — port to HTML (recommended, but your call)

### Why this is more feasible than it looks

The whole app has **three interactive widgets**: a textarea, a two-option
select, and one button (`main.py:1166`, `1171`, `1176`). Everything else is
display. You are not rebuilding an interactive app — you are rebuilding a report
page with one form on it.

And the data side is nearly free: every UI-facing type in `schema.py` is a plain
`@dataclass` (`Node`, `Edge`, `Graph`, `SourceRecord`, `EvidenceClaim`,
`GraphCritique`, `AdjudicationReport`, `GraphDiff`), so `dataclasses.asdict`
gives clean JSON with no adapter layer.

### The real cost is progress streaming, not the HTML

`st.status` is currently giving you live incremental progress across an 11–13
LLM-call pipeline for free. A run takes minutes. Replacing that is the bulk of
the work:

- `POST /analyze` → starts a background task, returns a job id
- `GET /events/{job_id}` → SSE stream fed by the `on_progress` callback
- `GET /result/{job_id}` → the finished payload
- client-side JS to render the step list as events arrive

That is the honest reason "just serve HTML" isn't simple. Everything else is
templating.

### Structure

```
app.py              FastAPI: form POST, SSE progress, result render
pipeline.py         run_pipeline (Stage 1)
presentation.py     dot/cell/label helpers (Stage 1)
templates/          Jinja2: base, form, result, partials
static/
  app.css           tokens + real component CSS, no Streamlit selectors
  app.js            SSE client, tab/disclosure behavior
  viz-standalone.js vendored Graphviz renderer
```

### Two constraints not to trip over

**Don't add a system dependency.** There is no `dot` binary on this machine —
`st.graphviz_chart` was bundling viz.js client-side for you. This is graded
coursework, so `brew install graphviz` would break a grader's ability to run it.
Vendor `viz-standalone.js` into `static/` and render the DOT in the browser.
`graph_to_dot()` is reusable unchanged either way.

**Jinja autoescapes.** The code currently escapes manually — 18 `html.escape`
calls plus `_dot_escape`. Passing pre-escaped strings into `{{ }}` renders
`&amp;lt;`. Strip the manual escaping at those call sites during the port and let
Jinja own it (keep `_dot_escape`, that's DOT syntax, not HTML).

### Also update

`README.md` §Run and WORKFLOW.md §"UI artifacts" both hardcode
`streamlit run main.py`.

---

## Fallback — Option A: keep Streamlit, fix it properly

If Stage 0 alone resolves the contrast and the look is acceptable, stop there and
do this instead of Stage 2:

1. Keep `config.toml` (Stage 0a) as the single source of theme truth.
2. Cut the CSS from 660 lines to roughly 150: keep `:root` tokens and the custom
   card/matrix/ribbon classes; **delete all 26 Streamlit-internal selectors**.
   Let `config.toml` style native widgets rather than fighting them.
3. Accept the ceiling honestly. Dropdown popovers, dataframe chrome, and tab
   styling will never be fully yours.

Cost: a few hours vs. a day-plus for the port. Zero new dependencies. If the
grader mainly wants working analysis, this is defensible.

---

## Recommendation

Do **Stage 0 now** — it fixes complaint 2 outright, complaint 1 outright, and
tells us whether the theme was the real problem.

Then decide Stage 2 vs. Option A based on what Stage 0 looks like. Stage 1 is
worth doing either way.

I'd lean toward the port: with three widgets and dataclass-native results, you
get full visual control for a bounded amount of work, and the progress-streaming
layer is the only genuinely new machinery. But that's a real trade-off against
your time, so it's your call — not mine to make silently.

I have not started implementing. Tell me which stages to run.
