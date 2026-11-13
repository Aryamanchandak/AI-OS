# Architecture note — Browser Comparison Agent + Replay Viewer

## The problem

`web_search` + `fetch_url` retrieve *documents*. A comparison task needs *state*:
the interesting rows on Hugging Face's model index do not exist until you set the
Tasks filter and change the sort order. Those are click-and-wait interactions
against a JavaScript-rendered page. A static fetch returns page chrome and an
empty results container — technically a successful HTTP 200, semantically nothing.

So the agent needs to *drive* a browser. The design question is not "can we
automate a browser" but **how much does each page cost to understand**, because
the naive answer — screenshot everything, send it to a vision model — is roughly
100× the cost of reading the HTML, and most pages do not need it.

## The cascade

The Browser skill answers that with a four-layer cascade, cheapest first, and
stops at the first layer that actually produces the goal:

| Layer | Mechanism | Cost | Wins when |
|---|---|---|---|
| 1 · extract | `httpx` GET → trafilatura | **zero LLM calls** | static article content |
| 2a · deterministic | caller-supplied CSS selectors → Playwright | zero LLM calls | the caller already knows the DOM |
| 2b · a11y | element legend `[id]<tag role>name</tag>` → text model | ~1 text call/turn | anything with labelled controls |
| 3 · vision | set-of-marks annotated screenshot → vision model | ~10× layer 2b | page has no DOM grip at all |

Escalation is triggered by a layer returning nothing useful, not by a
configuration flag. Layer 1 also refuses to answer when the *goal* contains an
interaction verb (`filter`, `sort`, `click`) — a 5,000-character extract of a
listing page is not an answer to "sort by likes", and accepting it would be the
subtle failure mode where the run looks successful and the data is wrong.

**Layer 2b does most of the real work.** That is the non-obvious finding, and it
is documented empirically in `S9/code/VALIDATION.md` §8: across six candidate
targets the cascade chose vision *once*. Modern canvas apps (Excalidraw, tldraw)
have properly aria-labelled toolbars, and the driver's `drag(x,y → x,y)` action
handles raw canvas without visual reasoning. Layer 3 earns its place only when
the page has no enumerable interactive elements **and** the goal forbids guessing
— the empty `turn_01_legend.txt` in a vision run is the artifact that proves it.

## Gateway blocks are a first-class outcome

CAPTCHA, Cloudflare interstitials, and login walls are detected by literal marker
strings — both on the raw HTML *and* again on the JS-rendered page, because a WAF
will often 405 a bare GET while serving the CAPTCHA only to a real browser
session. On a hit the skill returns `error_code="gateway_blocked"` **immediately**
and skips the remaining layers, so a blocked site costs ~1 second instead of a
full vision budget.

The orchestrator's recovery path reads that code, re-invokes the planner with a
failure report, and `planner.md` instructs it not to retry the same URL. The
result is an honest "I couldn't retrieve this" instead of a hallucinated table —
which is the actual reason the typed error code exists rather than a bare
exception.

## The constraint: the orchestrator is untouched

`flow.py` is not modified. New behaviour enters through exactly three doors:

1. **The skill catalogue** (`agent_config.yaml`) — one `browser:` entry.
2. **Prompts** (`prompts/*.md`) — where the comparison-table behaviour lives.
3. **New standalone scripts** — `report.py` reads persisted state and imports
   nothing from `flow.py`.

The comparison table is prompt work, not code, and that is deliberate. The
distiller emits `{columns, rows[], comparison}` with a `source_url` on every row;
the formatter renders those rows verbatim as a Markdown table; the critic — which
the orchestrator auto-inserts on every edge out of the distiller, because the
catalogue marks it `critic: true` — checks for ragged rows, fabricated cells, and
invented URLs. Table correctness is enforced by a node in the graph rather than
by a post-processing step, so a bad table fails the run instead of reaching the
user.

## The replay viewer

`report.py` is a **read-only** renderer. It is a separate script rather than a
hook inside the orchestrator for one reason: it is the cleanest possible proof
that the run was not altered to produce the report. Everything it shows was
already written to `state/sessions/<sid>/` by a run that had no knowledge a
report would ever be generated.

```
state/sessions/<sid>/
  query.txt                        → §1 original goal
  graph.json                       → §2 DAG (nodes, edges, per-node status)
  nodes/n_00N.json                 → §3 path, §4 actions, §6 data, §8 turns
    └ NodeState.prompt_sent          the exact bytes sent to the gateway
    └ AgentResult.output             BrowserOutput / distiller rows / verdicts
  browser/browser_<ts>/<layer>/    → §5 screenshots + page-state logs
    └ turn_NN_raw.png                what the page looked like
    └ turn_NN_marked.png             what the vision layer saw (numbered boxes)
    └ turn_NN_legend.txt             what the a11y layer saw instead
gateway SQLite ledger (HTTP)       → §8 cost, per agent tag
```

Two details worth calling out:

- **Artifact-to-node matching.** A session can hold several `browser_<ts>`
  directories. Each is assigned to the browser node with the largest `started_at`
  not after the directory's timestamp. Nearest-match would mis-assign when two
  browser nodes run concurrently; "started before this directory existed" does not.
- **The page is fully self-contained.** Screenshots are downscaled and inlined as
  base64 data URIs, the DAG is hand-rendered inline SVG. No CDN, no JS, no build
  step — the report survives being emailed as a single file. A test asserts zero
  external references.

The cost rollup is the one thing not on disk; it is fetched from the gateway at
report time. When the gateway is down the report still renders and the cost
section degrades to a note plus the locally-known turn counts, because a replay
of a finished run should not depend on a live service.

## What would break first

- **Layer 2b burning its 12-turn cap on a dropdown it cannot see.** The escape
  hatch is `metadata.selectors` (Layer 2a). Switching layers mid-demo is a
  legitimate demonstration of "cheapest correct path", not a workaround.
- **Element IDs are per-turn, not stable across turns** (`dom.py` uses `1..N`,
  browser-use uses CDP `backend_node_id`). Fine for short tasks; it would bite on
  a goal that needs the model to refer back to an element it clicked earlier.
- **No paint-order/occlusion filtering** — the model can pick an element sitting
  underneath a modal. Both gaps are catalogued with upgrade paths in
  `S9/code/browser/PARITY_AUDIT.md`.
