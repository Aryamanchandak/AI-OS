# PDMA Agent — Investigation & Remediation Plan

**Scope:** the PDMA agent under `agent/` (Perception → Decision → Memory → Action,
plus the `gateway`/`artifacts`/`vector_index` support modules). The MCP server and
LLM gateway live one directory up (`AI Code/mcp_server`, `AI Code/llm_gateway`) and
are **out of scope** here except where the agent's paths point at them.

**Status:** investigation complete, nothing fixed yet (this is a plan). Findings are
tiered by *severity × confidence*, not lumped together.

---

## TL;DR — the headline

**As it sits on disk, the agent cannot complete a single iteration. It crashes in the
Decision layer on iteration 1** because `gateway.LLM` is `None` at import time.

This is not a subtle "sometimes" bug and it is **not** masked by the HTTP gateway being
up on port 8107. Every other finding below is downstream of this one — nothing past
Decision can be exercised until it is fixed.

### How I verified it (zero side effects)

| Check | Result |
|---|---|
| `python -c "import gateway; print(gateway.LLM)"` | `LLM = None` |
| `gateway.GATEWAY_V7_DIR` resolves to | `AI Agent/llm_gateway` → **does not exist** |
| Real dir is | `AI Code/llm_gateway` (one level higher) |
| `agent7.py` MCP paths (`parent.parent.parent`) resolve | correctly ✓ |
| Run state in `state/memory.json` | **14 distinct runs, exactly 1 tool_outcome ever recorded** |
| `index_ids.json` vs embedded items | **15 vs 14 — the vector index and memory store have drifted** |

The run-state numbers are the smoking gun: 14 runs each saved their opening user query
(the embed HTTP call succeeds) and then produced *no* work — precisely the signature of
a crash in Decision right after the query is remembered.

---

## Tier 1 — Blocker (confirmed by reading + execution)

### 1. `gateway.py` resolves its paths one directory too shallow → `LLM = None` → Decision crash

`gateway.py:21` and `:23`:

```python
GATEWAY_V7_DIR = Path(__file__).resolve().parent.parent / "llm_gateway"   # AI Agent/llm_gateway  ❌
ROOT_PYTHON    = Path(__file__).resolve().parent.parent / ".venv" / ...    # AI Agent/.venv        ❌
```

`agent7.py:46-47` uses `parent.parent.parent` and resolves correctly. `gateway.py` is
off by one `.parent`. Consequences, in order:

1. `GATEWAY_V7_DIR` points at a non-existent folder, so at **import time**
   `_client_path.exists()` is `False` → `LLM = None` (`gateway.py:64-71`). This happens
   unconditionally, independent of whether the HTTP service is up.
2. `perception.observe` and `memory.remember` wrap their `LLM().chat` calls in
   `try/except` and silently degrade to fallbacks — so they *hide* the failure.
3. **`decision.next_step` catches the `TypeError` and re-raises it** (`decision.py:186-188`),
   and `run()` has **no** `try` around `decision.next_step` (`agent7.py:145`). The run dies
   there, every time.
4. `ensure_gateway()`'s autostart is also broken (wrong `cwd`, wrong `ROOT_PYTHON`), so if
   the gateway is *not* already running it can't be launched either.

**Fix (one line, but verify the whole class — see below):** change `gateway.py` to
`parent.parent.parent` for both `GATEWAY_V7_DIR` and `ROOT_PYTHON`. Then re-run the import
check and confirm `LLM` is a class, not `None`.

> Note: `memory.json` proves the agent *did* run fully at some earlier point (there is one
> real `tool_outcome`). The most likely story is a directory move that shifted the nesting
> depth and broke only `gateway.py`. Don't claim "never ran" — claim "cannot run in the
> current layout," which the import check confirms.

---

## Tier 2 — Correctness & liveness (traced in code; #4 also observed)

### 2. The final answer is overwritten per answer-goal — multi-part queries can lose answers *(traced, hedged)*

`agent7.py:156` sets `final_answer = out.answer` on **every** answer, and the loop returns
only the last one. For a multi-part question decomposed into several independent answer
goals, each goal overwrites the previous, so only the last goal's text is returned. The
Perception system prompt *tries* to mitigate this by forcing the last goal to be a
"synthesis" goal — so this bites only when decomposition produces parallel answer goals
without a final synthesis. Real risk, not a guaranteed failure.

### 3. An answered goal is never marked done in-loop → wasted round-trips and possible run-to-MAX_ITERATIONS

When Decision answers, `agent7.py:159` just `continue`s. The goal is marked done only if
*next* iteration's Perception LLM call notices the answer in history and flips `done`. That
is a full extra Memory-read + Perception + Decision cycle per answered goal. Worse, the
synthesis guard (`perception.py:238-249`) refuses to mark a synthesis goal done unless
history holds an answer **> 60 chars** for that exact `goal_id`. A short-but-correct answer
(≤ 60 chars — e.g. a single time or number) never satisfies the guard, so the goal loops
until `MAX_ITERATIONS = 20`, then returns the generic "unable to produce an answer" string.

### 4. FAISS index and `memory.json` have drifted out of sync *(observed)*

`index_ids.json` lists **15** vectors; only **14** memory items carry an `embedding`. The
two stores disagree. Root cause is structural: `_save()` writes `memory.json` atomically
(tmp + rename, `memory.py:61-64`) but `VectorIndex.persist()` writes `index.faiss` /
`index_ids.json` **non-atomically** (`vector_index.py:68-72`), and the index `add`/`persist`
in `_persist_item` happens **outside** the file lock (`memory.py:220-223`). A crash or a
concurrent MCP-subprocess write between the two persists leaves them inconsistent — which is
what the live state shows. A drifted `_ids` list means vector search can map a hit to the
wrong `MemoryItem`.

### 5. Stuck-loop detection only warns, never breaks

`agent7.py:164-169` counts repeated tool calls and prints `possible stuck loop`, but takes
no corrective action. Combined with #3, a stuck agent burns all 20 iterations (and 20× the
LLM/embims cost) before giving up.

---

## Tier 3 — Architecture (it works when unblocked, but is questionable)

### 6. Perception runs a full planning LLM call **every** iteration

`perception.observe` re-decomposes/re-emits the entire goal list on every pass
(`agent7.py:118`). Almost all of Perception's complexity — position-based goal identity,
the verbatim-copy rule, the dedup pass (`perception.py:215-224`), the force-attach safety
net (`:262-271`) — exists only to survive re-planning that arguably shouldn't happen each
loop. A plan-once / update-status-cheaply split would delete most of this machinery.

### 7. Structured planning at `temperature=1.0` with three bolted-on guards

Perception calls the LLM at `temperature=1.0` (`perception.py:184`) for a *structured*
planning task, then compensates with (a) the synthesis guard, (b) the append-dedup, and
(c) the force-attach net. Guards stacked on a high-temperature planner are a smell; lower
temperature would remove the need for most of them.

### 8. PDMA role mismatch

Despite the "PDMA" framing, **Perception is really a Planner** (it decomposes goals and
decides artifact attachment) and the actual reasoning/synthesis lives in **Decision**.
Worth naming explicitly so the layer boundaries match what the code does.

### 9. Synchronous embed on the write hot-path + repeated full-file loads

Every `record_outcome` / `remember` / `add_fact` blocks the loop on a synchronous embed
HTTP call. Every `memory.read` re-parses the entire `memory.json` (via `_load()`) two-to-
three times per iteration (`_vector_search` `by_id`, `_index()` cold-start rebuild, keyword
fallback). Fine at 15 items; it is O(n) per iteration and will not scale.

### 10. Over-broad `SYNTHESIS_KW` list

`perception.py:198-203` includes `find`, `list`, `tell`, `name`, `identify` — nearly every
goal matches. That makes the synthesis guard (#3) and force-attach net fire far more often
than intended, attaching up to 30 KB of artifact bytes to Decision on goals that don't need
it (cost + latency).

---

## Known / accepted S7 limitations — **do NOT treat these as defects**

The code explicitly labels these as intentional scope for "Session 7." Listing them as bugs
would undercut the credibility of the real findings. Leave them, or track them as future
work only:

- **Vector-only retrieval; hybrid + RRF deferred** (`memory.py:13-17`).
- **Heuristic sliding-window chunking** in `index_document` (`memory.py:16-18`).
- **Embedding model fixed at gateway level** — switching invalidates the index; treated as a
  project constant by design.
- **`_index()` reloads FAISS from disk every call** — the docstring calls this out as
  "cheap at S7 scale" (`memory.py:69-85`). It's a deliberate tradeoff, not an oversight
  (though it interacts with #9).

---

## Also worth a look — path/name drift is a *class*, not a one-off

The gateway bug is one instance of stale paths/names. Confirmed siblings:

- Docs and docstrings say **`llm_gatewayV7/`**; the real directory is **`llm_gateway`**
  (`gateway.py:1,41,44,85`; `OVERVIEW_REPORT.md`).
- Hardcoded **port 8107** and other constants embedded in the bridge.

Recommend a single sweep for hardcoded paths/ports/version names rather than fixing #1 in
isolation.

---

## Proposed task breakdown (the actual plan)

Sequenced so each task unblocks the next. Tasks A–B are the minimum to get a working agent.

| # | Task | Files | Depends on |
|---|---|---|---|
| **A** | Fix `gateway.py` path depth (`parent.parent.parent`); re-run import check until `LLM` is a class; verify autostart `cwd`/`ROOT_PYTHON`. | `gateway.py` | — |
| **B** | Sweep for path/name/port drift (`llm_gatewayV7` vs `llm_gateway`, 8107, 2-vs-3 parent resolutions). Centralize into one config/constants location. | `gateway.py`, `agent7.py`, docs | A |
| **C** | Liveness fix: mark a goal `done` in-loop when Decision answers it (don't wait for next Perception pass); relax/repair the >60-char synthesis guard so short correct answers count. | `agent7.py`, `perception.py` | A |
| **D** | Multi-part answer correctness: accumulate per-goal answers instead of overwriting `final_answer`; assemble the final reply from all answered goals. | `agent7.py` | C |
| **E** | Make stuck-loop detection *act* (break or escalate), not just warn. | `agent7.py` | A |
| **F** | Data-integrity: make `VectorIndex.persist()` atomic (tmp + rename) and move index add/persist **inside** the memory file lock; add a startup consistency check + rebuild when `index_ids` count ≠ embedded-item count. | `vector_index.py`, `memory.py` | A |
| **G** | (Architecture, optional) Split Perception into plan-once + cheap status-update; drop `temperature` for planning and remove the guards it required; narrow `SYNTHESIS_KW`. | `perception.py`, `agent7.py` | C, D |
| **H** | (Perf, optional) Cache `_load()` within an iteration; move embeds off the write hot-path or batch them. | `memory.py` | A |

**Suggested first PR:** A + B + C + D + F (blocker + the confirmed correctness/integrity
issues). G and H are follow-ups once the agent demonstrably runs end-to-end.

---

## Open questions for you (state-and-proceed, not blocking)

1. **Scope** — I kept this to `agent/`. Do you also want `mcp_server` and `llm_gateway`
   audited? (I deliberately did **not** assert the path-traversal / sandbox-safety questions
   for `read_file`/`list_dir`, because those live in the unread `mcp_server.py`.)
2. **Deliverable form** — this is a markdown plan. Want it as tracked tasks instead, or
   should I proceed to implement Task A once you approve?
