# Causal Scenario Engine — Workflow

## Runtime flow

The app runs a fixed, bounded pipeline with no agent loop:

```text
brief
  → research plan (1 model call)
  → search + fetch + clean + rank (deterministic HTTP)
  → claims (10 sources per parallel model call)
  → evidence-aware graph builder (1 model call, replaces old extraction)
  → one selected critic (1 model call)
  → one adjudication/repair round (1 model call; no send-back)
  → exact-edge sensitivity (deterministic)
  → load-bearing edge verification (1 batched model call)
  → four scenario propagations (deterministic)
  → four narratives (parallel model calls)
```

Quick mode retrieves up to 20 sources and has 11 nominal model calls. Deep mode
retrieves up to 40 sources and has 13 nominal calls in this implementation.
Deep intentionally retains one critic rather than stacking a second critic.

## Code map — what each file does

The project has five folders. `engine/` is pure pipeline logic and never touches
a web framework; `web/` and `legacy/` are two interchangeable UI shells built on
top of it; `tests/` and `docs/` are self-explanatory.

```text
engine/   pure pipeline logic (research → graph → debate → propagate → synth)
web/      current UI: FastAPI app, HTML templates, static assets
legacy/   older UI: Streamlit shell, kept for comparison
tests/    offline deterministic + contract tests
docs/     this file, planning notes, and design history
```

If you're reading the code for the first time: start with `engine/schema.py`
(the vocabulary), then `engine/pipeline.py` (the orchestrator — its imports
are the entire pipeline in one place), then drill into whichever stage file
you care about.

### `engine/` — the pipeline

**`schema.py`** — no logic, only types. Two parallel representations of the
same causal vocabulary:
- `@dataclass` types (`Node`, `Edge`, `Unknown`, `Graph`, `SourceRecord`,
  `EvidenceClaim`, `GraphCritique`, `AdjudicationReport`, `GraphDiff`, …) are
  what the rest of the pipeline reads and mutates.
- Pydantic `*In` / `*Out` models (`CausalGraphOut`, `EvidenceClaimsOut`,
  `GraphCritiqueOut`, `AdjudicationOut`, `EdgeEvidenceOut`, …) mirror them and
  are handed to Gemini as a forced JSON `response_schema`; the model's answer
  is copied back into the dataclasses.

**`research.py`** — search, fetch, rank, and turn text into an evidence
ledger. No dependency on any other engine file.
- `DuckDuckGoSearchProvider.search()` — scrapes DuckDuckGo's HTML result
  page; no API key needed.
- `plan_research()` *(1 LLM call)* — asks Gemini for query groups tagged
  `evidence` / `counterevidence` / `context`; locally forces at least two
  counterevidence groups even if the model doesn't return any.
- `retrieve_sources()` *(no LLM, concurrent HTTP)* — runs the planned queries
  in a thread pool, canonicalizes and deduplicates URLs, rejects
  local/private targets before fetching (`_safe_public_url` — an SSRF guard
  against model-generated queries), strips HTML to visible text
  (`_TextExtractor`), then ranks sources by authority/recency/relevance
  buckets and caps the list at 20 (quick) or 40 (deep).
- `extract_claims()` *(N parallel LLM calls, 10 sources per call)* — for each
  claim Gemini returns, `supporting_passage` must be an exact (whitespace-
  normalized) substring of that source's actual text or the claim is
  silently dropped. This is what prevents hallucinated quotes from entering
  the evidence ledger.

**`extract.py`** — situation string → causal `Graph`, in exactly one LLM
call.
- `_SYSTEM` encodes the graph's hard invariants directly in the prompt
  (8–15 nodes, exactly 1 intervention root, 3–5 leaf outcomes, ≤3 hops,
  exactly 2 unknowns, DAG).
- `build_graph()` converts the raw parsed payload into the mutable
  dataclasses.
- `_validate()` re-checks every one of those invariants in code (cardinality,
  referential integrity, leaf outcomes, acyclicity via `networkx`, hop depth,
  each unknown reaching an outcome) — the prompt is the first line of
  defense, this function is the authoritative one.
- `extract_graph()` calls the model, validates, and — if validation fails —
  retries exactly once with the specific problems fed back into the prompt.
  Two failures raise `ExtractionError`.

**`debate.py`** — the one-round challenge/repair cycle, plus deterministic
diffing and evidence verification.
- `select_critic_role()` *(no LLM)* — a fixed keyword/regex heuristic that
  picks `contrarian` (policy/regulatory language), `evidence` (quantitative +
  claims exist), or `causal` (default).
- `critique_graph()` *(1 LLM call)* — the chosen critic role names concrete
  weaknesses (`CritiqueFinding` per node pair); it is explicitly told a
  finding is not a repair.
- `adjudicate_graph()` *(1 LLM call)* — the only place the graph itself can
  change after `extract_graph`. Returns one repaired `Graph` plus an
  `AdjudicationReport` (accepted/changed/rejected/unresolved). There is no
  loop back to the critic.
- `graph_diff()` *(no LLM)* — compares the pre- and post-adjudication edge
  sets locally (added/removed/changed-field) for the audit trail.
- `verify_load_bearing_edges()` *(1 batched LLM call)* — takes the small set
  of edges `sensitivity.py` flagged as consequential and asks the model to
  label each `supported`/`mixed`/`contradicted`/`assumption`/`unverified`
  against only the evidence ledger; every edge not in that set is force-reset
  to `unverified` first, so nothing looks verified by default.

**`sensitivity.py`** — deterministic, no LLM, no I/O.
- `load_bearing_edges()` flips one edge's sign at a time (on a deep copy),
  re-runs `propagate()` across all four scenario assignments, and records
  which edges actually change an outcome's sign. Ranked by how many
  scenarios/outcomes they move, capped at 6 — that capped list is what
  `debate.verify_load_bearing_edges()` spends its one LLM call on.

**`propagate.py`** — the deterministic core; pure function, no LLM, no I/O.
The file's own docstring is blunt about this: *"If you ever find yourself
importing an LLM client here, that is a bug."*
- `propagate(graph, assignment)` deep-copies the graph, seeds the
  intervention node (+1/high) and the two unknowns per the scenario
  assignment, walks the rest in topological order, and for each node: sign is
  an integer-weighted vote across incoming edges (`low=1, med=2, high=3`,
  so a few weak links can't outvote one strong mechanism), magnitude is the
  strongest incoming edge strength decayed one bucket per hop, and `contested`
  marks nodes with a net-zero result despite real opposing pushes. Every
  node's `trace` is filled with a human-readable line per incoming edge for
  the audit UI.

**`synth.py`** — resolved outcomes → one 3-sentence scenario note.
- `synthesize()` *(1 LLM call)* sends only the resolved **outcome** nodes
  (not the full graph) — direction/magnitude translated to plain English via
  `_ARROW`, plus each node's `trace` — and asks for exactly three sentences:
  what happens, the one driving mechanism, and what observation would
  falsify the scenario.
- `synthesize_all()` *(4 parallel LLM calls)* runs `synthesize()` for all
  four scenarios concurrently via `ThreadPoolExecutor` and returns narratives
  in input order.

**`pipeline.py`** — framework-neutral orchestration; the one file that calls
every other engine file. Deliberately synchronous — callers (`web/app.py`,
`legacy/main.py`) decide whether to run it in a thread.
- `run_pipeline(brief, mode, on_progress)` runs the fixed stage order from
  the runtime-flow diagram above, reports `(step_id, message)` progress
  through the `on_progress` callback, and returns one dict containing every
  intermediate artifact (sources, claims, both graphs, critique, report,
  diff, impacts, resolved scenarios, narratives, and any recoverable-stage
  error strings). Research, debate, and verification failures degrade in
  place (see "Failure behavior" below); builder and synthesis failures
  propagate to the caller so a bad run never overwrites the previous good
  result.

**`presentation.py`** — pure formatting, no LLM, no I/O. Shared by both UI
shells.
- `scenario_name()` / `short_label()` turn an unknown's yes/no question into
  a compact scenario label (e.g. "Oil holds above $90 ✓").
- `all_assignments()` returns the fixed four `{unknown_id: ±1}` combinations.
- `cell()` maps a resolved node to its comparison-table glyph (`↑↑ ↑ ▴ · ▾ ↓
  ↓↓ ⚠`); `impact_class()` returns the matching CSS class.
- `graph_to_dot()` renders a styled Graphviz DOT string (colors by node type,
  dashed edges for unknowns, wrapped labels) that the browser then draws —
  no server-side Graphviz binary involved.
- `edge_robustness()` wraps `sensitivity.load_bearing_edges()` as a
  `pandas.DataFrame` for direct display in either UI.

### `web/` — current UI (FastAPI)

**`app.py`** — HTTP shell around `pipeline.run_pipeline()`.
- `POST /analyze` validates the brief, creates a `JobState`, and hands it to a
  `ThreadPoolExecutor` worker (`_run_job`) so the request returns immediately
  with a `job_id`.
- `GET /events/{job_id}` streams that job's progress as Server-Sent Events by
  polling the in-memory `JobState.events` list.
- `GET /result/{job_id}` renders the finished analysis as an HTML fragment
  once the job is `completed`.
- `GET /` renders the form plus the last completed result, if any — a failed
  new run never clears `_last_completed`.
- All job state is a plain in-memory dict guarded by one `threading.Lock`;
  nothing survives a restart, and `_trim_finished_jobs()` bounds memory to
  `MAX_JOBS`.

**`templates/index.html`** — the page shell (form, styles, scripts) and
**`templates/partials/result.html`** — the result fragment (comparison
matrix, scenario cards, sources/claims, critique/diff, graph, sensitivity
table) that `/result/{job_id}` returns and the page swaps in.

**`static/app.js`** — submits the form to `/analyze`, opens an `EventSource`
against `/events/{job_id}` to show live progress, then fetches
`/result/{job_id}` and injects it into the page; also drives
`renderGraph()`, which feeds the server-rendered DOT string to Viz.js.

**`static/viz-standalone.js`** — vendored Viz.js 3.9.0 (see
`docs/THIRD_PARTY_NOTICES.md`), so DOT graphs render client-side with no
`dot` binary and no CDN request.

**`static/app.css`** — all visual styling for both the form and the result
view.

### `legacy/` — older UI (Streamlit)

**`main.py`** — a Streamlit rendering shell that calls the exact same
`engine.pipeline.run_pipeline()` and `engine.presentation` helpers as
`web/app.py`, just rendered with `st.*` widgets instead of Jinja templates
(sidebar form, `st.status` for progress, custom CSS injected via
`st.markdown(unsafe_allow_html=True)`). Kept for side-by-side comparison
with the FastAPI shell; not the primary UI.

### `tests/`

- **`test_propagate.py`** — hand-built graph fixtures exercising the pure
  arithmetic core in `propagate.py` only (sign voting, magnitude decay,
  contested detection). No LLM, runs in milliseconds.
- **`test_slim_pipeline.py`** — contract tests across research, extraction,
  debate, sensitivity: claim-passage verification, counterevidence planning,
  strength-weighted direction voting, one-round critique/adjudication,
  `graph_diff`, load-bearing edge selection, and selective verification —
  all with mocked/fixture data, no live API key required.
- **`test_pipeline.py`** — failure-semantics tests for `pipeline.run_pipeline`
  itself: research degrading to brief-only, debate failure keeping the
  builder graph, verification failure clearing every edge back to
  `unverified`. Uses `unittest.mock.patch.object` on the `engine.pipeline`
  module to stub out each stage.

Each test file also runs standalone (`.venv/bin/python tests/test_x.py`) via
a small self-check runner at the bottom of the file — no `pytest` dependency
required.

## Stage contracts

### 1. Research planning

`research.plan_research()` returns a structured `ResearchPlan`. Query groups
have an explicit intent (`evidence`, `counterevidence`, or `context`). Local
normalization guarantees two counterevidence groups survive the mode's hard
query cap.

### 2. Retrieval and ranking

`DuckDuckGoSearchProvider` implements the one-method `SearchProvider` protocol.
Retrieval then:

1. searches query groups concurrently;
2. canonicalizes URLs and removes tracking parameters;
3. deduplicates deterministically;
4. rejects local/private targets before fetch;
5. fetches public HTML/text with size and timeout bounds;
6. extracts visible clean text;
7. ranks by authority, explicit URL freshness, and lexical relevance.

Every `SourceRecord` keeps its URL, title, publisher, retrieval timestamp,
clean text, and ranking buckets. Unknown publication dates stay unknown rather
than being guessed.

### 3. Evidence ledger

`research.extract_claims()` sends at most ten sources per independent structured
call. Every retained `EvidenceClaim`:

- names a real source ID;
- includes a passage that is deterministically checked against source text;
- is typed as `fact`, `forecast`, `inference`, or `assumption`;
- retains supporting, contradicting, or contextual stance.

The claim list is the evidence ledger; no extra synthesis stage rewrites it.

### 4. Graph construction

`extract.extract_graph()` receives the brief and ranked claim ledger. It remains
one structured builder call, with one validation retry. Expanded `Edge` fields
include confidence, time lag, conditions, evidence status, and supporting and
contradicting claim IDs.

Validation enforces node/outcome cardinality, referential integrity, signs,
non-empty mechanisms, leaf outcomes, a root intervention, DAG topology, a
three-hop maximum, exactly two unknowns, and an outcome path for each unknown.

The builder uses a 2,048-token thinking budget and a larger 16,384-token output
ceiling so reasoning does not truncate the structured graph.

### 5. One critic and one adjudicator

`debate.select_critic_role()` deterministically selects:

- `contrarian` for policy/regulatory questions;
- `evidence` for quantitative questions with retrieved claims;
- `causal` otherwise.

`critique_graph()` writes only `GraphCritique.findings`. `adjudicate_graph()`
returns one repaired graph and one `AdjudicationReport`. There is no retry loop
or send-back to the critic. `graph_diff()` compares the builder and final edge
sets locally.

If debate fails, the candidate graph remains visible and the unresolved failure
is recorded. It is never silently presented as adjudicated.

### 6. Sensitivity and verification

`sensitivity.load_bearing_edges()` flips edge signs one at a time across all
four scenarios and names the links that change at least one outcome. It ranks
them by changed scenarios/outcomes and caps verification at six edges.

`debate.verify_load_bearing_edges()` verifies that set in one structured call.
All non-selected edges are explicitly `unverified`. If research is unavailable,
verification performs no model call and every edge remains `unverified`.

### 7. Deterministic propagation

`propagate.propagate()` deep-copies the graph, seeds the intervention and
unknown assignments, and walks nodes in topological order. Direction votes use
integer strength weights (`low=1`, `med=2`, `high=3`); magnitude remains a
three-bucket hop-decay lookup. It performs no I/O and no model calls.

### 8. Scenario narratives

The two unknowns produce four assignments. `synth.synthesize_all()` sends only
resolved outcome states and traces to four parallel narrative calls. It does
not change graph or propagation results.

## Failure behavior and session state

- Research failure degrades to brief-only graph construction and is shown in
  the research panel.
- Builder failure aborts only the new run.
- Critic/adjudicator failure retains the builder graph and exposes the failure.
- Verification failure leaves edges `unverified`.
- A failed new run never overwrites the process's last completed analysis; the
  previous result remains on screen.
- FastAPI stores bounded job state in memory. No data survives a server restart.

## UI transport

The HTML shell runs long analyses without holding a form request open:

```text
POST /analyze
  → background pipeline worker
  → GET /events/{job_id} (SSE progress)
  → GET /result/{job_id} (autoescaped HTML result)
```

`pipeline.run_pipeline()` reports framework-neutral `(step_id, message)`
progress events. The FastAPI worker appends them to a bounded in-memory job
record; the legacy Streamlit shell writes the same callback messages to
`st.status`.

## UI artifacts

The result screen renders:

1. the four-world comparison matrix;
2. scenario narratives and outcome traces;
3. source cards and classified claim ledger;
4. critic findings, adjudication decisions, unresolved disagreements, and
   deterministic graph diff;
5. graph visualization plus edge evidence fields;
6. exact-edge structural sensitivity.

The causal diagram is rendered in the browser by the vendored Viz.js bundle.
No system Graphviz installation is required.

## Verification

Offline checks:

```bash
.venv/bin/python tests/test_propagate.py
.venv/bin/python tests/test_slim_pipeline.py
.venv/bin/python tests/test_pipeline.py
```

`test_propagate.py` covers the pure arithmetic core. `test_slim_pipeline.py`
covers expanded schemas, counterevidence planning, exact-passage claims,
strength-weighted direction, one-round critique/adjudication, graph diff,
load-bearing selection, and selective verification.
