# AI Agent — Memory / Artifacts / Vector Index: Implementation Plan

**Status:** 🔧 concrete, sequenced work plan. Written 2026-07-08 out of the
deep-dive in `docs/MEMORY_ARTIFACTS_DEEPDIVE.md` and its answered comments.
This is the "do these, in this order" doc. Everything here is a **bounded
fix or a small, agreed improvement** — the bigger open design questions live
in `docs/MEMORY_ARTIFACTS_CONCERNS.md`, and net-new features are indexed in
`TODO.md` §8.

**Scope:** mostly `src/agent/` (`cognition/memory.py`,
`cognition/decision.py`, `cognition/action.py`, `services/artifacts.py`,
`schemas.py`). Phase 0 touches the sibling `mcp_server/` repo and is called
out as out-of-this-repo.

**How to read this:** each item has the same shape —
- **What** (one line)
- **Why** (the problem, in plain English)
- **Where** (exact file + line so you can look at it yourself)
- **The change** (what the code becomes)
- **Verify** (how we prove it worked)
- **Risk** (what could go wrong)

[TALK TO ME AS IF I DON'T READ CODE. BRACKET-COMMENT ANYTHING, SAME AS THE
OTHER DOCS. I WILL REORDER PRIORITIES IF I WANT.]

**Guiding rules carried over from the loop docs:** correctness before
efficiency; legible logs are first-class; no special cases. Every change
below keeps those.

---

## The order at a glance

| Phase | Item | Type | Risk | Blocks anything? |
|---|---|---|---|---|
| **0** | mcp_server import fix | unblock | med | blocks ALL live verification |
| **1** | `record_outcome` preview bug + dead `result_preview` + truncation cliff | bug | low | — |
| **2** | `temperature=0` try; widen hash 16→64 | tweak | low | — |
| **3** | `content_type` detection; atomic+locked `put()` | hardening | low | — |
| **4** | min-similarity gate; `kinds=` filter | retrieval | low-med | needs Phase 0 to tune |
| **5** | artifact `list`/`delete`/GC; `clear()` also wipes artifacts | feature | med | — |

Phases 1–3 are self-contained in `src/agent/` and can land **without**
Phase 0. Phase 4's *mechanism* can land without Phase 0, but *tuning the
number* needs a live trace, which needs Phase 0. Phase 5 is a real feature
but its policy is already decided (see §5).

---

## Phase 0 — Unblock the whole system (sibling repo)

**What:** fix the two broken imports that crash the `mcp_server` subprocess
at startup.

**Why:** Right now, in a live run, the MCP subprocess dies the instant it
starts, because of a module-level `import` pointing at a directory that no
longer exists after the repo restructure. A module-level import that fails
takes down the *entire* subprocess — so **every** tool is unavailable
(`fetch_url`, `read_file`, `time`, `currency`, `index_document`,
`search_knowledge` — all of them), not just the two knowledge tools. Until
this is fixed, nothing in this whole plan can be verified by actually
running it — only by reading code. This is why it's Phase 0.

**Where:** (all in the sibling `mcp_server/` project, not this repo)
- `mcp_server/mcp_server.py` line 23 — `sys.path.insert(0, .../"AI Code/agent")`
  points at a dead path (`AI Code/agent` no longer exists; code is now at
  `AI Agent/src/agent/`).
- `mcp_server/tools/knowledge/memory/tool.py` — `import memory as _memory` /
  `import artifacts as _artifacts` (flat imports that no longer resolve).

**The change:**
1. Retarget the `sys.path` insert to `AI Agent/src` — ideally by copying the
   walk-up-to-a-known-sibling pattern `gateway.py` already uses
   (`_find_workspace_root`, `gateway.py:21-40`) instead of hardcoding one
   more brittle relative path.
2. Change the two imports to the real module paths:
   `from agent.cognition import memory as _memory` and
   `from agent.services import artifacts as _artifacts`.
3. **Do NOT** touch `knowledge_graph`'s `KGStore` import in this phase — that
   one pulls from a *different* sibling project (`Database/knowledge-graph`)
   with its own venv, and is a dependency decision (vendor in / add to path /
   disable that tool), not a path typo. Tracked separately in `TODO.md` §7.

**Verify:** launch the agent, confirm the MCP subprocess stays up and lists
its tools (a simple run that calls `time` or `read_file` proves the whole
subprocess is alive). Must be run **inside `mcp_server`'s own `.venv`** — it
has a separate dependency set (transitively pulls faiss/numpy/pydantic/httpx)
from the agent's, so a dry-run in the wrong env proves nothing.

**Risk:** medium — it's a sibling repo with its own environment, so "it
imports on my machine" isn't proof; the venv dry-run is the real gate.
Whoever owns `mcp_server/` should sign off.

[NOTE: THIS IS THE ONE PHASE THAT ISN'T IN OUR REPO. FLAG IF YOU WANT ME TO
HANDLE mcp_server SEPARATELY OR FOLD IT IN.]

---

## Phase 1 — Memory correctness (the real bug + its two neighbours)

All three sub-items live in `memory.py:record_outcome()` and
`decision.py:_format_hits()`. They're one coherent change to "how a tool
result is permanently recorded and later shown." Highest value, lowest risk,
fully inside `src/agent/`.

### 1a. Stop discarding the preview when an artifact exists

**Why:** when a tool result is big enough to be offloaded to an artifact,
`record_outcome` throws away the good 240-char preview it was handed and
stores a contentless descriptor like `fetch_url({...}) -> artifact art:abc`.
That contentless string is what gets embedded — so **any large tool result
becomes permanently unsearchable by what it actually said**, findable only by
tool name/arguments. (Full trace: `DEEPDIVE.md` §3.4.)

**Where:** `memory.py:377-381`
```python
descriptor = f"{tool_call.name}({json.dumps(tool_call.arguments)[:80]}) -> "
if artifact_id:
    descriptor += f"artifact {artifact_id}"        # <- result_text dropped
else:
    descriptor += result_text[:120].replace("\n", " ")
```

**The change:** keep the preview in *both* branches; the artifact id is
additive, not a replacement.
```python
preview = result_text[:200].replace("\n", " ")
descriptor = f"{tool_call.name}({json.dumps(tool_call.arguments)[:80]}) -> {preview}"
if artifact_id:
    descriptor += f" [artifact {artifact_id}]"
```
Now the embedded descriptor carries real content, so vector search can match
"what did that page say about pricing" against it.

### 1b. Make the `result_preview` field actually reachable

**Why:** `record_outcome` writes `value["result_preview"] = result_text[:400]`
on every single tool_outcome item — but `decision.py:_format_hits()`, the
function that decides what a memory hit shows the LLM, only ever reads
`value["raw"]` or `value["chunk"]`. So `result_preview` is written, persisted,
and **never displayed to anyone, ever** (`DEEPDIVE.md` §3.4 step 6).

**Where:** `memory.py:390-394` (writes `result_preview`) and
`decision.py:74-90` (only reads `raw`/`chunk`).

**The change — pick ONE (I recommend the first, it's smaller):**
- **Option A (rename the key):** store the preview under `value["raw"]`
  instead of `value["result_preview"]`. `_format_hits()` already renders
  `raw` (truncated to 2000 chars for display), so this makes it visible with
  zero change to `decision.py`.
- **Option B (teach the reader):** add a `result_preview` check to
  `_format_hits()` alongside `raw`/`chunk`. More explicit, one more branch to
  maintain.

**Verify (1a + 1b together):** construct a `ToolCall`, call
`record_outcome(...)` with a long `result_text` and an `artifact_id`, then
call `_format_hits([that_item])` and confirm the rendered string contains the
actual content preview, not just `artifact art:xxx`. No live MCP needed — this
is a direct unit-level check.

### 1c. Close the 400-byte–4KB truncation cliff

**Why:** for a tool result too small for an artifact (≤4KB) but bigger than
the caps (120-char descriptor, 400-char `result_preview`), the content
between ~400 bytes and 4KB is **permanently and silently truncated with no
backup copy anywhere** — it wasn't big enough to become an artifact, but too
big to survive the cap (`DEEPDIVE.md` §3.5). Your own note: "store the full
thing and truncate at display."

**Where:** same function, `memory.py:390-394`.

**The change:** when there's **no** artifact (result already ≤4KB, so it's
cheap to keep whole), store the full `result_text` under `value["raw"]`
untruncated. Display-time truncation is already handled by `_format_hits()`'s
`raw[:2000]` (`decision.py:76-78`). This does **not** turn small results into
artifacts — the 4KB artifact threshold in `action.py` is a separate decision
about the *inline prompt*, not about how complete the *disk record* is.
```python
value = {
    "tool": tool_call.name,
    "arguments": tool_call.arguments,
    "raw": result_text if artifact_id is None else result_text[:400],
}
```
(When there *is* an artifact, the full bytes already live in the artifact
store, so a 400-char preview here is fine.)

**Risk (all of Phase 1):** low. It only ever *adds* content to what's stored
and shown; nothing existing depends on the descriptor being contentless or on
`result_preview` being hidden. Worst case is slightly longer memory hits in
the prompt, which is the point.

---

## Phase 2 — Two cheap, reversible tweaks

### 2a. Try `temperature=0` for the memory classifier

**Why:** `remember()`'s classifier (which decides kind/descriptor/keywords/
value for free-form text) runs at `temperature=1.0` — high randomness for what
is a structured-extraction task. `decision.py` runs the same *shape* of task
(pick one structured answer) at `temperature=0`. The code already carries a
workaround for the exact failure mode high temperature causes here (empty
`value` dict → fall back to `{"raw": raw_text}`), and the comment justifying
1.0 cites a doc (`NOTES_RUNS`) that **does not exist anywhere in the repo or
workspace** — the original reasoning is lost (`DEEPDIVE.md` §3.8).

**Where:** `memory.py:354` (`temperature=1.0` inside `_llm_classify`).

**The change:** set `temperature=0`. Leave the empty-`value` fallback in place
for now (belt-and-suspenders); after some runs, check whether it still ever
fires. If it stops firing, the fallback can later be removed as dead.

**Verify:** run `remember()` on a handful of representative inputs (e.g. "my
mom's birthday is 15 May", a preference, a random observation) a few times
each; confirm classification is stable and `value` is non-empty. Fully
reversible — it's one number.

**Risk:** low. If it somehow makes things worse, revert the one number.

### 2b. Widen the artifact hash 16 → 64 hex chars

**Why:** artifact ids use the first 16 hex chars (64 bits) of a sha256 — an
undocumented, unproven collision-margin assumption chosen purely so ids look
short in logs. Widening to the full 64 hex chars costs essentially nothing and
removes the silent assumption (`DEEPDIVE.md` §1.3).

**Where:** `artifacts.py:23` — `hashlib.sha256(blob).hexdigest()[:16]`.

**The change:** drop the `[:16]` (or make it a named constant if you want to
keep it tunable). The only visible effect is longer `art:` ids in logs/prompts.

**Verify:** put + get an artifact, confirm round-trip still works and the id is
the full-length hash. Note: this changes the id for *new* artifacts only;
existing 16-char ids in an old `memory.json` still resolve to their old files
(the code strips the prefix and reads by whatever digest string it's given),
so no migration is needed — but a `memory.clear()` before/after avoids mixing
the two lengths in one store if you care about tidiness.

**Risk:** low. Purely a length change; content-addressing semantics unchanged.

---

## Phase 3 — Artifact store hardening

### 3a. Detect `content_type` instead of hardcoding `text/plain`

**Why:** `action.py` writes `content_type="text/plain"` for every artifact
regardless of what the tool returned. True today only because every current
tool returns text — but the instant a tool returns an image, PDF, or
structured JSON, this silently mislabels it (and `_result_to_text`'s
`str(c)` fallback would mangle non-text content entirely). A dormant
correctness gap, not hypothetical (`DEEPDIVE.md` §1.5).

**Where:** `action.py:24-35` (`_result_to_text`) and `action.py:65-71`
(the `put()` call hardcoding `text/plain`).

**The change:** read the actual MCP content-part type when collapsing the
result, and pass a real `content_type` through to `put()`. If the part is
genuinely text, `text/plain` is correct; if it's a known other type, label it
honestly; if unknown, at least record `application/octet-stream` rather than
lying about it being text.

**Verify:** hard to fully verify until a non-text tool exists — for now, add a
unit check that a text result still labels `text/plain`, and leave a clear
`# TODO: non-text content types` marker at the `str(c)` fallback so the next
person adding a binary tool sees it.

**Risk:** low. For text (all current tools) behaviour is unchanged.

### 3b. Atomic + locked `put()`

**Why:** `artifacts.put()` does `if not bin_path.exists(): bin_path.write_bytes(blob)`
with no lock and no atomic write — unlike `memory._save()`, which does
temp-file-then-rename under an `fcntl` lock. Two processes (the agent + the
mcp_server subprocess) fetching the same URL at the same moment can race on the
same new hash. Because the content is identical when this race happens, the end
state is *usually* fine — but an interleaved write to the same path from two
processes isn't guaranteed safe, so a corrupted `.bin` is a real (if
low-probability) outcome (`DEEPDIVE.md` §1.5).

**Where:** `artifacts.py:21-37`.

**The change:** mirror `memory._save()`'s pattern — write to a temp file, then
atomically rename into place, and guard the whole exists-check-then-write under
an `fcntl` lock (a per-store `.lock` file, same idea as `memory.py`'s
`_LOCK_PATH`). Because writes are content-addressed and idempotent, the lock
can be coarse (one lock for the store) without hurting anything at this scale.

**Verify:** functional round-trip unchanged; the safety property is hard to
trigger on demand, so the verification is really "the code now matches the
same safe pattern `memory.py` already uses and trusts."

**Risk:** low. Adds coordination that only ever prevents a bad interleaving;
never changes a successful single-writer result.

---

## Phase 4 — Retrieval quality guards

These two are where "the retrieval is technically working" becomes "the
retrieval is trustworthy." The *mechanisms* are bounded and safe to add; the
*exact tuning* (what threshold, which call sites) wants a live trace, so this
phase pairs with Phase 0.

### 4a. Add a minimum-similarity floor to vector search

**Why:** today there is **no gate at all** — `VectorIndex.search()` returns the
top-k by score no matter how bad the best score is. If the index has 3
unrelated items, a query still gets all 3 back, top score maybe 0.3, and
because `_vector_search` treats any non-empty result as success, a weak match
both (a) gets shown to the model with no "this is a weak match" signal and
(b) suppresses the keyword fallback that might have done better
(`DEEPDIVE.md` §2.2).

**Where:** `vector_index.py:110-121` (`search`) and `memory.py:170-198`
(`_vector_search` / the `if vec_hits:` success test at `memory.py:210`).

**The change:** add an optional `min_score` floor — drop hits below it in
`search()` (or in `_vector_search`), so that a below-floor result set counts as
"found nothing" and correctly falls through to keyword search. **Do NOT pick
the number blind** — ship the *mechanism* with a conservative default (or
logging-only at first), then read actual score distributions from a live trace
(needs Phase 0) before committing to 0.7 vs 0.75 vs 0.8. Picking the number
without real hit/miss examples is a guess dressed as a decision.

**Verify:** with Phase 0 up, log every hit's score for a batch of real queries;
eyeball where good matches and junk matches separate; set the floor there.

**Risk:** low-med. Too high a floor silently hides good matches; that's exactly
why the number comes from data, not from the abstract. Start by *logging*
scores, not gating on them.

### 4b. Pass `kinds=` at call sites where the goal type is known

**Why:** `agent7.py:179` calls `memory.read(query, history, query_vec=query_vec)`
with **no `kinds=` filter**, so every round's retrieval ranks facts,
preferences, and tool_outcomes together with no separation and no recency
weighting. A stale `tool_outcome` from an old run can outrank something current
purely on cosine proximity (`DEEPDIVE.md` §2.1). The `read()` function already
*accepts* `kinds=` — the call sites just don't use it.

**Where:** `agent7.py:179` (and any other `memory.read` call sites).

**The change (bounded part):** where the caller knows what it's looking for,
pass `kinds=`. This is the small, safe slice of the bigger cross-run-bleed
problem — the deeper fix (recency weighting, run-scoping, volatility) is a
design question parked in `CONCERNS.md` §1/§2, not this phase. Do the cheap
filtering now; don't try to solve self-conditioning here.

**Verify:** confirm a query that should only match facts no longer surfaces
unrelated tool_outcomes from prior runs (needs Phase 0 for a realistic store).

**Risk:** low for the filtering itself; the *judgement* of which call site
wants which kinds is the only care-point, and it's reversible.

---

## Phase 5 — Artifact lifecycle (feature, but the policy is already decided)

This is net-new capability, but unlike the concerns doc items, the **policy is
settled** (reference-counted GC — see `DEEPDIVE.md` §1.6 / Open Question 1), so
it's plannable now rather than "come back to it."

### 5a. `list()` and `delete()` on the artifact store

**Why:** the store has no way to even enumerate what's in it, let alone remove
anything — it only grows (`DEEPDIVE.md` §1.5). Every other lifecycle feature
(GC, dedup, metadata audits) needs a `list()` to build on.

**Where:** `artifacts.py` (new functions).

**The change:** add `list_ids()` (glob the `*.bin`/`*.json` files, return the
`art:` ids + parsed sidecar metadata) and `delete(art_id)` (unlink the `.bin`
and `.json`). Pure mechanism, no policy.

### 5b. Reference-counted GC

**Why:** artifacts should be removable without creating dangling references.
Memory is permanent by design, so a blind per-run wipe would orphan any
`artifact_id` held by a prior run's memory item on the very next run. Ref-
counting never does that (`DEEPDIVE.md` §1.6, Q1).

**The change:** a `gc()` that loads `memory.json`, collects every non-null
`artifact_id`, and `delete()`s any artifact on disk whose id isn't in that set.
Run it as a periodic/startup sweep, **not** on the hot path.

### 5c. Make `memory.clear()` also clear the artifact store

**Why:** `memory.clear()` wipes `memory.json` + the FAISS index but never
touches artifacts — so every past `clear()` has already orphaned 100% of
referenced bytes on disk with no memory item left to route back to them
(`DEEPDIVE.md` §1.5, `TODO.md` §7).

**Where:** `memory.py:430-439` (`clear()`).

**The change:** after wiping memory + index, also clear the artifact store
(either delete all artifacts, or call `gc()` — but since memory is now empty,
GC would delete everything anyway, so a direct wipe is simplest and correct).

**Verify (Phase 5):** put a few artifacts, reference some from memory, run
`gc()`, confirm only unreferenced ones are gone; then `clear()` and confirm the
artifact store is empty.

**Risk:** medium — this deletes data. The ref-count set must be computed
correctly (miss an `artifact_id` and you delete something still referenced).
Guard: dry-run mode first (log what *would* be deleted), eyeball it, then arm
it.

---

## What is deliberately NOT here

These came up in the deep-dive but are **design questions**, not bounded fixes.
They live in `docs/MEMORY_ARTIFACTS_CONCERNS.md`:
- **Fact volatility / expiry** (true-forever vs. true-for-an-hour) — the big one.
- **Cross-run context bleed** as a philosophy (self-conditioning loop) — Phase
  4b does the cheap slice; the real fix is a design pass.
- **fact / preference / scratchpad taxonomy** ("black hole" surface area).
- **Artifact directory + dedup-by-input** (don't re-fetch a URL already fetched).
- **Hybrid / RRF retrieval** (run vector + keyword in parallel and merge).
- **`write-everything, filter-on-read`** bet — confirmed *keep for now*; the
  concern doc records the trigger for revisiting.

Net-new features (as opposed to design questions) are indexed in `TODO.md` §8
so the parked-items registry stays the single source of truth for "things not
yet built."

---

## Suggested first session

If you want a single high-value, low-risk starting point that doesn't depend on
the sibling repo: **Phase 1 (all three sub-items) + Phase 2** in one pass. It's
all inside `src/agent/`, it's the actual bug you reacted strongest to, and it's
verifiable without a live MCP subprocess. Then Phase 0 to unblock live traces,
then re-verify Phase 1 for real, then Phase 4 tuning.

`[YOUR PRIORITY CALL / ANY REORDERING HERE]`
