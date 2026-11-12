# AI Agent — Memory, Artifacts & Vector Index: Deep Dive

**Purpose:** companion to `docs/CONCEPTUAL_ARCHITECTURE.md` and
`docs/LOOP_RESTRUCTURE_PLAN.md`, but for the storage side instead of the
PLAN/EXECUTE/REVIEW loop. This doc answers "how does this actually work"
and "why was it built this way" for the three components underneath
Memory: the artifact store, the vector index, and Memory itself. Every real
bug/gap found while writing this is cross-referenced to `TODO.md` §7 —
this doc explains the *why*, TODO.md tracks the *what's broken*.

**Status:** written 2026-07-07 from reading the actual code
(`src/agent/services/artifacts.py`, `src/agent/services/vector_index.py`,
`src/agent/cognition/memory.py`, `src/agent/cognition/action.py`,
`src/agent/cognition/decision.py`, `src/agent/agent7.py`), not from the
design docs. Nothing here has been changed in code — this is explanation
only. Comment inline wherever you want, same as the other two docs.

[MY COMMENTS ARE WRITTEN IN CAPS IN BRAKCETS []]

> **A:** answers below are marked with `> **A:**` blockquotes, added
> 2026-07-07 after re-reading `memory.py`, `artifacts.py`,
> `vector_index.py`, `decision.py`, `action.py`, `perception.py`, and
> `TODO.md` §7 to ground every answer in the actual code rather than
> restate the prose above it. Where a claim needed checking, it's cited by
> file:line.

---

## 0. The big picture — how the three pieces relate

Three components, three different jobs, one shared purpose: keep the LLM's
prompt small while still letting the agent "remember" things. [AND REMEMBER THINGS SMARTLY NOT JUST REMEMBER THEM, AND HAVE ACCESS TO THEM WHEN NEEDED AND NOT HAVE TOO MUCH INFORMATION WHEN NOT NEEDED]

> **A:** Agreed, and worth being precise about where "smart" actually lives
> today vs. where it's just accumulation. The only place anything decides
> "is this the right thing to surface" is the cosine-similarity ranking at
> read time (`memory.py:_vector_search`) plus the top-12/top-10 truncation
> in `perception.py`/`decision.py`. There is **no** write-time judgment
> ("is this worth keeping") and **no** decay ("is this still relevant") —
> see §3.6 and the new fact-expiry discussion under §1.6 below. So today
> "remember smartly" really means "retrieve smartly from an
> indiscriminately-written pile," not "write smartly." That's a legitimate
> phase-one design (see §3.6), but it's not the same thing you're asking
> for, and it's worth naming the gap explicitly rather than assuming
> retrieval ranking is doing more curation than it actually is.

'[THATS FINE JUST ADD THIS TO THE TODO]'

- **Artifacts** — a dumb bytes locker. Give it bytes, get back a handle.
  It has no idea what memory or the loop are.[MAKE SENSE BUT WHO IS TRACKING HOW THE INFORMATION IS STORED, HOW ITS FED BACK, THE KEYS WHO TRACKS THEM ?]

  > **A:** Memory tracks the keys. Every `MemoryItem` that came from a tool
  > result carries an `artifact_id` field (set in `record_outcome()`,
  > `memory.py:395`) that points at the artifact handle. Memory is the only
  > "directory" of which artifact belongs to which run/goal/tool-call —
  > `artifacts.py` itself has no index, no list, no reverse lookup (see the
  > "no delete, no list, no GC" gap in §1.5). So concretely: Memory is the
  > catalog, Artifacts is the warehouse with no front desk. If Memory's
  > record of an `artifact_id` is ever lost (e.g. `memory.clear()`), the
  > bytes still exist on disk but nothing anywhere can enumerate or find
  > them again — they become unreachable by id even though `art:<hash>` is
  > deterministic, because nothing kept a list of which hashes exist.

  [I THINK WE SHOULD CHANGE THIS, HAVE A SMALL SUMMARY ON THE ARTIFACTS, STORE THE METADATA AS I HAD ORIGINALLY SUGGESTED, KEEP THEM ON DISK FOR A MOTH, AND LET LLM SEARCH ALONG SIDE WITH REMEMEMBER, ADD TO TO DO, A TASK FOR LATER]

- **Vector Index** — a dumb math structure. Give it a vector, get back the
  nearest other vectors. It has no idea what an "item" means beyond a
  string id. [YES AND ALL THIS IS SOTRED DIRECTLY IN MEMORY ? FED INTO EVERY CONTEXT RUN ? IN WHICH CASE HOW DOES THE MODEL KNOW WHAT MEMORY HAS NA DHOW TO ACTUALLY VENE READ IT WITHOUT GETTING TO THE FAISS WHICH I HAVE NO IDEA HOW IT DOES] [[THIS REALLY NEEDS TO BE OPTIMISED, AS THIS IS A SILENT FAILURE WAITING TO HAPPEN, AS IS THE CASE WITH THE ARTIFACTS]]

  > **A:** Important clarification: the model **never touches FAISS,
  > ever, at all.** The stack is three separate things: (1) `memory.json`
  > — the actual records (descriptor + structured `value` + an optional
  > embedding vector); (2) `index.faiss` + `index_ids.json` — just the
  > embedding vectors plus a parallel list of ids, nothing else, no text;
  > (3) the LLM's prompt — plain text that `decision.py:_format_hits()`
  > builds from whichever `MemoryItem`s got returned. The model is not fed
  > "into every context run" wholesale — it is fed the **top 8** items
  > `memory.read()` returns for the current query (`agent7.py:179`,
  > `top_k=8` default), formatted as text, once per round. It has no way
  > to ask FAISS anything directly, and never needs to — retrieval is
  > entirely mechanical Python code (`_vector_search` → `_index()` →
  > `idx.search()`) that runs *before* the LLM call, and the LLM only ever
  > sees the already-resolved, already-formatted result. So the specific
  > "silent failure waiting to happen" you're worried about (model
  > confused about FAISS internals) isn't a real failure mode — that
  > boundary is already clean. The *actual* silent-failure risks in this
  > stack are the ones documented below: the `record_outcome()` descriptor
  > bug (§3.4), the missing `kinds=` filter allowing cross-run bleed
  > (§2.1), and no minimum-similarity gate on vector hits (§2.2) — i.e.
  > FAISS will happily return its "best" match even when that match is a
  > bad one, with no signal to the model that it's a weak match.

  [YEAH MY QUESTION IS ONLY HOW DOES THE CODE KNOW WHAT TO SURAFCE?? HOW DO YOU KNOW WHAT THE RIGHT HING TO BRING UP ? HOW DOES VECTOR SEARCH MAKE SURE ITS GOT THE RELAVNT MEMEORY OUT?]

- **Memory** — the layer that actually understands the domain (facts,
  preferences, tool outcomes). It decides what to embed, calls the vector
  index to store/search those embeddings, and calls the artifact store
  when something is too big to keep inline. [NUT WHATS THE INDICATOR FOR THIS IS THE THING WE NEED TO PULL OR WE DO CHUNK SEARCHES ?? IN WHICH CASE HOW DO WE DECIDE WHICH CUNKS TO SEARCH FOR ?]

  > **A:** There is no separate "chunk search" concept — chunking already
  > happened at write time, so read time is just normal vector search.
  > Concretely: `index_document` (an MCP tool, not shown in the files this
  > doc covers, but it's what feeds `add_fact()`) splits a document into
  > overlapping slices and calls `add_fact()` once per slice — each slice
  > becomes its own independent `MemoryItem` of kind `fact`, each with its
  > own embedding. There is no parent "document" object and no
  > chunk-selection logic layered on top. A query just runs cosine
  > similarity against *every* embedded item (facts, preferences, and
  > tool_outcomes all mixed together — see §2.1's `kinds=` gap), and the
  > top 8 by score win, whether those 8 happen to be document chunks, past
  > tool outcomes, or standalone facts. So "which chunk gets pulled" and
  > "which fact gets pulled" are literally the same mechanism with no
  > distinction between them today.

[THE LOOP NEEDS TO KNOW ABOUT THIS ITS VERY IMPORTANT THAT WE BUILD THEM TO WORK WITH THE LOOP, AND HOW WE DO THAT WILL REQUIRE A LOT MORE INFO, ITS SIMELE WIRING I GUESS BECAUSE THE LOOPS MADE I THIN PRETTY WELL BUT WE USE THIS AS A WAY TO IMPROBE TH EINDIVIDUAL PARTS]

> **A:** Agreed — and this is already partly true today, it's just thin.
> §4 below is the existing seam: `perception.py` decides *when* artifact
> bytes attach to a goal, `decision.py` mechanically resolves that
> attachment. The wiring exists; what's missing is the loop ever telling
> Memory/Artifacts anything about run boundaries, goal identity beyond a
> single id, or "this run is done, here's what mattered." Worth treating
> as its own short design pass once the mcp_server break (§4, TODO.md §7)
> is fixed and a live trace is actually possible.

None of the three know about `Goal`, `Block`, or the PLAN/EXECUTE/REVIEW 
loop — that connection is made one level up, in `perception.py` (routes
`needs_artifact_ids` onto goals) and `decision.py` (resolves those ids back
into bytes right before an LLM call). So the mental model is a stack:

[DO WE NEED A MODEL TO EXTRACT TO THE OUTPUT FROM THE TOOLS TO CONVERT IT INTO BYTES NO RIGHT ?]

> **A:** Correct, no model involved. `action.py:_result_to_text()` pulls
> `.text` off the MCP tool result (it's already a Python string — MCP
> tools return text today, full stop), and `action.py:execute()` just does
> `text.encode("utf-8")` before handing it to `artifacts.put()`. That's
> the entire "conversion" — a built-in string method, not an LLM call.
> Bytes was chosen as the storage type not because text needs converting,
> but so the store isn't hardcoded to text-only forever (e.g. a future
> tool that fetches an image or a PDF could reuse `put()` unchanged). The
> gap this creates today is `content_type` always being written as
> `"text/plain"` regardless — see §1.5/§1.6 below.


```
Perception / Decision       <- knows about goals, decides WHEN to use bytes
        |
     Memory                 <- knows about kinds (fact/preference/...),
        |                       decides WHAT to embed and WHERE to store it
  Vector Index   Artifacts   <- both dumb, no domain knowledge, just plumbing
```

---

## 1. Artifacts — the bytes locker

### 1.1 Why it exists at all

The one sentence that matters is the comment already in the file: *"The 50
KB of HTML touches exactly one LLM call across a run."* Every LLM call
costs money and time proportional to how much text is in the prompt. If a
tool fetches a 50KB web page, and that page's full text got pasted into
every subsequent prompt in the run "just in case," you'd be paying for it
5, 10, 20 times over a multi-round run for no benefit — the LLM only
actually needs the full text on the *one* call where it does the reading
work (extract, summarize, compare). Every other call just needs to know
"there is a thing called `art:a1b2c3`, here's a one-line description of
it." That's the entire reason this module exists: separate "knowing
something exists" (cheap, always in the prompt) from "having the actual
content" (expensive, only when needed).

[YEAH AND MY ONLY QUESTION IS HOW DOES IT DECIDE WHICH IS THE CORRECT ARTIFCAT TO PULL ?]
[HOW DO WE CONVERT THE WORDS TO BYTES ? FROM THE OUTPUT, AND FROM THE OUTPUT WHY DO WE NEED BYTES AND HOW DO WE STORE THE BYTES ? ]
[DO WE USE AN LLM FOR BYTES CREATION, IS BYTES TH EBEST WAY TO STORWE THIS ?]

> **A:** Which artifact to pull is decided in `perception.py`, not here —
> two mechanisms, tried in order (`perception.py:160-167`,
> `_goals_from_plan`):
> 1. **LLM index choice** — the PLAN/REVIEW prompt shows the model a
>    numbered list of artifact-bearing memory hits (`_snapshot_hits`,
>    `perception.py:104-127`) and asks it to fill in `artifact_indices` on
>    each proposed goal. `_artifact_ids_for_indices` (`perception.py:130-138`)
>    turns those numbers back into real `art:` ids.
> 2. **Keyword-overlap fallback** — if the LLM left `artifact_indices`
>    empty, `_artifact_ids_for_text` (`perception.py:141-157`) does a crude
>    token-overlap match between the goal's own text and each hit's
>    descriptor/keywords, and if that also finds nothing but the goal text
>    looks like a synthesis/summarize request, it just grabs the most
>    recent artifact-bearing hit.
>
> So it's "an LLM guess, backstopped by a heuristic," not anything
> Artifacts or Memory decide. On the bytes question: no LLM, no
> conversion step worth naming — see the answer right above this one.
> Bytes is simply the most general container a filesystem-backed store can
> hold (works for text today, would work for images/PDFs later without
> changing `put()`'s signature); it's not "the best way" in some deep
> sense, it's just the standard choice for a content-addressable blob
> store and nothing here depends on it being smarter than that.


### 1.2 Why content-addressable (hash-based ids) instead of a counter or a database

Three reasons this shape was chosen over the obvious alternatives:

- **Free deduplication.** If the same URL gets fetched twice, or the same
  file gets read twice, the hash is identical, so the second `put()` is a
  no-op — `if not bin_path.exists(): write it`. A counter-based id (`art:1`,
  `art:2`, ...) would store the same bytes twice. [ HOW IS THIS IMPLEMENTED, IMPORTANT TO KNOW SO THATS ITS NOT JUST TRIPPING]

  > **A:** It's exactly the one line shown — `artifacts.py:27`,
  > `if not bin_path.exists(): write it`. `bin_path` is
  > `STORE / f"{digest}.bin"` where `digest` is the sha256 hex of the
  > content. There's no separate "have I seen this hash" table — the
  > filesystem itself *is* the lookup table, because the filename is the
  > hash. That's the whole mechanism: no database, no in-memory set, just
  > "does a file with this exact name already exist." (This is also why
  > there's no locking on the check-then-write — see §1.5.)

- **No coordination needed across processes.** Both the main agent process
  and the `mcp_server` subprocess write to this same store. If ids were a
  simple incrementing counter, the two processes would need to coordinate
  who gets the next number (a shared counter with locking). With
  content-addressing, the id is a pure function of the bytes — two
  processes hashing the same content independently arrive at the same id
  with zero coordination. [NO I AGREE WIT THE HAS I GUESS IF YOU HAVE A FIXED HAS METHOD DEDUP BECOMES EASY]
- **The id doubles as an integrity check.** If you ever suspect a file got
  corrupted, you can re-hash it and compare — the id *is* the checksum.

  [WHY WOULD THIS HAPPEN ? AND I DONT SEEM YSELF DOIG IT, NOT IN REAL TIME ANYWAY MAYBE FOR DEBUGGING]

  > **A:** Correct, this is a manual/debugging capability, not something
  > that runs automatically anywhere in the code today. It would matter
  > if e.g. a disk error flipped a bit in a `.bin` file, or a partial write
  > happened (see the no-locking gap in §1.5) — re-hashing the file and
  > comparing to its own filename would catch that. Nothing currently
  > does this check proactively; it's a property you get for free, not a
  > feature that's been built on top of it. Fine to leave unbuilt for now.

### 1.3 The actual write path, step by step

This is genuinely the whole thing (see `src/agent/services/artifacts.py`):

```python
def put(blob: bytes, *, content_type, source, descriptor) -> str:
    digest = hashlib.sha256(blob).hexdigest()[:16]   # (1) 
    art_id = f"art:{digest}"
    bin_path = STORE / f"{digest}.bin"
    meta_path = STORE / f"{digest}.json" [SO EACH ARTIFACT IS STORED AT ITS OWN HASH DENOMINTAED PATH ? howo do we plan to put a delete function here ? ]
    if not bin_path.exists():                          # (2)
        bin_path.write_bytes(blob)
        meta = Artifact(...)                             # (3)
        meta_path.write_text(meta.model_dump_json(indent=2))
    return art_id
```

> **A:** Yes — each artifact is two files at a deterministic path,
> `STORE/{digest}.bin` and `STORE/{digest}.json`. A delete function is
> trivial to add *mechanically* (given an `art:<digest>` id,
> `(STORE / f"{digest}.bin").unlink()` and the `.json` sidecar too) — the
> hard part was never the delete function itself, it's deciding the
> *policy* of when it's safe to call it, because `memory.json` items can
> hold references to these ids forever (§1.6). See Open Question 1 for
> the recommended policy (reference-counted GC).

1. Hash the *whole* content — not the descriptor, not a summary, the raw
   bytes. Truncated to the first 16 hex characters (64 bits) purely to keep
   the id short and readable in logs; the full 256-bit hash isn't needed
   for uniqueness at this project's scale, but see the collision-risk note
   in §1.5 below — this is an implicit assumption, not some thing proven safe.

   [MAYBE WE GET THERE SOMEDAY, LET’S LEAVE IT FOR NOW I GUESS. SO WE ARE HASHING THE ENTIRE CONTENT AND THEN BRINGING THE HASH DOWN TO 16 HEX CHARACTERS, OR 64 BITS. WHY NOT EXPAND TO 256 HEX? WHAT COMPLEXITY DOES IT ADD? 16 IS BEING USED UP THERE, SO THAT CAN JUST AS EASILY BE MOVED TO 256. THE THING IS, WHAT ARE WE ACHIEVING BY SAVING THESE ARTIFACTS FOR SUCH A LONG TIME? IF THE AGENT EVENTUALLY BECOMES A LONG-RUNNING AGENT THEN SURE, BUT THEN WE WILL HAVE TO HAVE SOME OPERATIONAL EFFICIENCY FOR CLEANING UP THE CACHE—ESSENTIALLY, PROVERBIALLY, NOT ACTUALLY, CLEARING THE CACHE. SHOULD IT BE THAT THESE HASHES AND DESCRIPTIONS ARE MADE BETTER AND MORE DESCRIPTIVE, AND THEN WE KEEP THEM FOR A MONTH OR SOMETHING?]

   > **A:** You're right that widening to the full 64 hex chars (256 bits)
   > costs essentially nothing — it's a one-character change
   > (`hexdigest()` instead of `hexdigest()[:16]`), the only price is
   > slightly longer ids in logs/prompts. I'd make that change; there's no
   > real argument for 16 over 64 other than "logs look tidier," and
   > that's a bad trade against an unproven collision margin at unknown
   > future scale. But widening the hash doesn't touch the retention
   > question you're actually asking — that's a completely separate
   > design axis (how long bytes live) from how the id is computed. On
   > retention: I don't think "keep for a month" is the right lever either
   > — see Open Question 1's answer (reference-counted GC keyed off
   > whether `memory.json` still points at it, not a calendar). A
   > time-based expiry would delete artifacts that are still referenced
   > (breaking retrieval) or keep ones that are already orphaned
   > (wasting disk) — it's the wrong axis for *this* store. Time-based
   > decay is the right idea, but for *facts* in Memory, not for artifact
   > bytes — see the new discussion under §1.6 below.

2. Dedup check — if the bytes already exist under this hash, skip the
   write entirely.



3. A small sidecar JSON file records what the bytes *are* (type, size,
   where they came from, a one-line description) without needing to open
   the `.bin` file. This is what lets something list/describe artifacts
   without reading potentially large blobs. [THIS IS A PART OF THE METADATA SUGESSTION I HAVE ABOVE]

  > **A:** Right — the `.json` sidecar already *is* per-item metadata; what's
  > missing (per §1.5) is anything that enumerates *all* the sidecars at
  > once (a `list()` function), which is what would actually let you build
  > a directory/GC on top of this metadata that already exists.


`get_bytes()` and `get_meta()` are the mirror image — strip the `art:`
prefix, read the file. `exists()` is a cheap existence check used by
Decision before trying to attach something (see §1.6). [WHEN YOU SAY MIRROR IMAGES YOU MEAN, THEY HAVE MOSTLY THE SAME FUNCTION BUT OPPOSITE BEHAVIOURS]

> **A:** "Mirror image" here just means same shape, inverse direction —
> `put()` writes bytes given content, `get_bytes()` reads bytes given an
> id; same file-path logic run backwards, not "opposite behavior" in any
> functional sense. Poor word choice on my part, sorry for the confusion.

### 1.4 Where artifacts actually get created — `action.py`, not `artifacts.py`

`artifacts.py` never decides *when* to create an artifact — that decision
lives in `src/agent/cognition/action.py`:

```python
ARTIFACT_THRESHOLD_BYTES = 4096   # "roughly one A4 page of text"[ANYTHING MORE THAN THIS INTO THE ARTIFACTS RIGHT ?][MAYBE THIS IS TOO GENEOUROUS ? NOT SURE ?][THIS REMINDS ME THAT WE NEED TO MAKE SURE THE MODEL MAKES A SMART CHOICE AND DOESNT ASSUME THAT EVERYTHIGN IN THE ARTIFACTS STORE IS GOSPEL]

if nbytes > ARTIFACT_THRESHOLD_BYTES:
    art_id = artifacts.put(text.encode("utf-8"), ...)
    descriptor = f"[artifact {art_id}, {nbytes} bytes] preview: " + text[:240] + "..."
    return descriptor, art_id
return text, None   # small enough — just pass it through directly
```

> **A:** Yes, `nbytes > 4096` is the entire rule — nothing more nuanced
> (no per-tool overrides, no content-type sensitivity). On "the model
> shouldn't assume the store is gospel" — agreed, but note the artifact
> store never claims correctness either; it stores exactly what the tool
> returned, verbatim, including a tool's own errors or bad data. The
> model's job of judging whether fetched content is trustworthy is
> unrelated to and unaffected by whether that content happens to live
> inline or behind an `art:` handle — that trust judgment isn't (and
> shouldn't be) artifact-store's job to enforce. Whether 4KB is "too
> generous" is genuinely just a tuned constant with no strong argument
> either way at current scale — not worth spending time on until you have
> evidence it's wrong in practice.

Why 4KB specifically? It's a rough proxy for "roughly one printed page" —
small enough that a handful of small tool results (a time lookup, a
currency conversion, a short file) can sit directly in the prompt without
noticeably bloating it, large enough that anything bigger (a full fetched
web page, a long file read) is worth the overhead of a separate artifact
lookup. It's a tuned constant, not a principle — reasonable, but arbitrary,
and it's the exact number that creates the truncation-cliff bug described
in §3.5 below. 

### 1.5 Known gaps (full detail in `TODO.md` §7)

- **No delete, no list, no GC.** The store only grows. There is currently
  no way to even ask "what's in here," let alone clean it up. [THIS IS IMPORTANT, I THINK WE SHOULD MAINTAIN A DIRECTORY OF INFOMRATION RIGHT ? THAT ALLOWS US TO BASICALLY PULL INFORMATION FROM DIFFERENT RUNS INSTEAD OF HAVING TO RE RUN IT, AND ONE OF THE THINGS WE NEED TO DO IS MAKE SURE THE TOOLS HAVE CLEAR INFROMATION OF WHATS ALREADY , SO WE DONT DUPLICATE WORK] [THIS HOWERVER IS HARD TO BUILD CORRRECTLY AND SOMETHING THAT NEEDS TO BE LOOKED AT IN CLEAR GOOD DETAIL]

  > **A:** Agreed on both counts — a directory is genuinely valuable (it's
  > effectively the "list" function you'd need for GC anyway, §1.3), and
  > agreed it's a real design task, not a quick add. Note this partially
  > already exists in spirit: Memory *is* a directory of artifacts, just an
  > incomplete one (only forward pointers from `MemoryItem.artifact_id`,
  > no reverse index, no dedup-awareness at the "have we already fetched
  > this URL" level — that check would need to hash the *input*, e.g. the
  > URL, which is a different key than the content hash `artifacts.py`
  > uses today). Worth scoping as its own follow-up rather than folding
  > into this session's fixes.

- **`memory.clear()` doesn't touch this store.** Every time memory gets
  wiped, every artifact that memory used to reference is orphaned —
  unreachable, but still sitting on disk forever.

[ YOU MEAN THE ARTIFACTS STORED, STORE ?] [THERE NEEDS A DECAY RIGHT ? EVENUTALLY I GUESS DPEENDS ON HOW TIME INCREASES]

> **A:** Yes, the artifact bytes store (`state/artifacts/`). And yes to
> decay in principle, but see the distinction I'm drawing in §1.6 below:
> I think artifact decay should be *reference-driven* (delete once nothing
> in Memory points at it anymore), not *time-driven* — an artifact
> referenced by a 6-month-old fact that's still true should still be
> fetchable; an artifact from 5 minutes ago that nothing references
> anymore is already garbage. Time is the wrong axis for bytes; it's the
> right axis for *facts* (see below).

- **No locking on `put()`.** Compare to `memory.py`'s `_save()`, which
  writes to a temp file and atomically renames it under an `fcntl` lock —
  `artifacts.put()` does neither. Two processes racing to write the same
  new hash at the same time isn't guaranteed crash-safe.

[NEED MORE DETAILS ON THIS]

> **A:** Concretely, `artifacts.put()` (`artifacts.py:21-37`) does
> `if not bin_path.exists(): bin_path.write_bytes(blob)` with no lock
> around the exists-check-then-write pair, and `write_bytes()` itself is
> not an atomic write (no temp-file-then-rename, unlike `memory.py:_save()`
> at `memory.py:61-64`). The realistic failure: the main agent process and
> the `mcp_server` subprocess both fetch the same URL at nearly the same
> moment, both compute the same hash, both see `bin_path.exists()` is
> False, and both call `write_bytes()` on the same path concurrently. Since
> the content is identical (same hash ⇒ same bytes by definition, modulo an
> actual hash collision), the *end state* is very likely fine either way —
> but a torn/interleaved write from two processes writing to the same file
> handle at once is not something Python or the OS guarantees is safe
> without coordination, so a corrupted `.bin` file for that one artifact is
> a real, if low-probability, outcome. It's not "will definitely break," it's
> "isn't guaranteed not to" — a real gap, low severity given content is
> always identical when this race happens at all, but worth the same
> temp-file-then-rename pattern `memory.py` already uses if this ever gets
> touched.

- **16 hex chars (64 bits) of the hash is an unproven assumption**, not a
  calculated safety margin — fine at hundreds/thousands of artifacts, but
  it's never been written down as a deliberate choice with a stated ceiling.

  [HAVE ADDRESSED THIS ABOVE]

- **`content_type` is hardcoded to `"text/plain"`** in `action.py` no
  matter what the tool actually returned.

  [THIS IS A BIG ISSUE AND SOMETHNG I MENTIONED ABOVE, HOW DO YOU KNOW A TEXT IS ALWAYS RETRUNED, I MEAN SEEMS UNLINKELY ANYTHIGN ELSE WILL BE PULLED BUT YOU NEVER KNOW MY IMAGINATION AND BOUNDS SHOULDNT LIMIT HERE, TELL ME MORE]

  > **A:** Confirmed at `action.py:24-35` (`_result_to_text`) — it only
  > ever reads `getattr(c, "text", None)` off each content part of the MCP
  > result; if a part has no `.text` attribute it falls back to
  > `str(c)`, which for any structured/binary MCP content type would
  > produce a useless stringified repr, not actual usable bytes. So today
  > it's true that every *current* tool returns plain text — that's a fact
  > about the current tool set, not a guarantee the interface makes. The
  > moment someone adds a tool that returns an image, a PDF, or structured
  > JSON meant to stay structured, this silently mislabels or mangles it
  > with no error raised anywhere — `execute()` would happily write
  > `str(<ImageContent object>)` to disk and call it `text/plain`. This is
  > a real, if currently dormant, correctness gap, not a hypothetical one
  > you're overreaching on — worth fixing whenever the tool surface grows
  > beyond text, by reading the actual MCP content-part type instead of
  > assuming.

### 1.6 The core tension you raised: should artifacts outlive a run?

Memory (the JSON record) is **never** cleared automatically — it's designed
to persist forever, across every run, so the agent can recall something
from last week. Artifacts were never designed with the same lifetime
question answered explicitly — they just accumulate. The moment you build
deletion for artifacts (per-run or otherwise), you run into this: any
`tool_outcome` memory item from an *earlier* run may still hold that
artifact's id. Delete the bytes, and that memory item's `artifact_id`
silently points at nothing.

[YES BUT THATS WRONG RIGHT, WHY IS MEMORY FOREVER, IT ABSOLUTELY SHOUDLNT BE ARTIFACTS SHOULD HAVE A LONGER SHELF LIFE THAN MEMORY SURELY, IF MMEORY STORED THE DATE AND TIME, WHY IS THAT RELEVANT PAST THE HOUR EVEN FORGET FOREVER. AND TALK ABOUT CONTEXT BLOAT

THIS NEEDS TO BE CHANGED AS IT DOESNT MAKE ANY SENSE, ATLEAST TO ME CURIOUS TO HEAR WHAT YOU THINK]

> **A:** I think you're conflating two genuinely different problems here,
> and separating them resolves the "this doesn't make sense" feeling:
>
> 1. **Should raw artifact *bytes* be garbage-collected?** Yes — this is
>    the doc's framing, and it's a straightforward reference-counted-GC
>    question (Open Question 1). Nothing controversial here once you
>    accept Memory records are the reference-holders.
> 2. **Should every *fact* in Memory really persist forever, regardless of
>    what it's about?** This is the sharper point you're actually making,
>    and I think you're right that the current code gets this wrong. Look
>    at `memory.py` end to end: there is **no timestamp-based expiry
>    field anywhere on `MemoryItem`**, no distinction between "the user's
>    mom's birthday is 15 May" (durable — true indefinitely) and "it's
>    currently raining" or "the stock is at $142" (perishable — true for
>    minutes/hours). Both get written via the exact same path
>    (`remember()` or `record_outcome()`), embedded the same way, and kept
>    forever with zero decay. That's not a considered design choice
>    anywhere in the code — it's an absence. I don't think "memory forever"
>    is wrong as a *default* (you do want durable facts like preferences
>    and identity facts to survive indefinitely — that's the whole point
>    of having a memory at all, and pruning that would be the actual
>    regression), I think what's actually missing is **per-item
>    volatility**: some notion (a `volatile: bool`, or an `expires_at`
>    timestamp) that lets perishable facts age out of retrieval while
>    durable ones don't. That's a real gap this doc didn't previously call
>    out, and it's more consequential than the artifact-GC question,
>    because a stale, retrieved-with-high-confidence fact actively
>    produces wrong answers, whereas orphaned artifact bytes just sit on
>    disk unread. I'd treat this as its own short design task, not
>    something to bolt onto the artifact-GC fix — see Open Question 1 for
>    how I'd sequence it. On "context bloat" specifically: bloat today
>    comes from `top_k=8` truncation working fine at read time regardless
>    of store size (FAISS brute-force search doesn't get slower fast at
>    this scale, §2.2), so growth mostly costs disk and eventually
>    retrieval *quality* (irrelevant stale hits crowding out relevant
>    ones) rather than prompt size directly — which is exactly the
>    failure mode volatility-aware expiry would fix.

`decision.py`'s `_resolve_attached()` already defends against this
gracefully — it checks `artifacts.exists()` first and just logs "missing
artifact" if not, rather than crashing. So the failure mode isn't a crash,
it's silent capability loss: the agent remembers *that* it once fetched
something, but not *what* it said. [AND WHAT DOES TH EAGENT DO WITH THIS INFO ?]

> **A:** Today, nothing — and that's itself a small gap worth naming.
> `_resolve_attached()` (`decision.py:124-133`) just skips the missing
> artifact and prints a log line; the LLM's prompt simply doesn't get an
> `ATTACHED ARTIFACTS` section for that id, with no explicit note in the
> prompt saying "you asked for X, it's gone." The model has no way to
> distinguish "I didn't ask for an artifact" from "I asked and it's
> missing" — both produce the same absence in the prompt. A cheap
> improvement, if artifact GC ever ships: when `_resolve_attached` finds a
> requested id missing, surface that explicitly in the prompt (e.g.
> `--- art:xxx: no longer available ---`) instead of silently omitting it,
> so the model can at least say "I recall fetching this but the content
> has expired" instead of just not mentioning it.

Two honest options, not a decision made for you here:
- **Reference-counted GC** — periodically delete only artifacts nothing in
  current `memory.json` still points to. Never creates a new dangling
  reference, because anything still referenced survives. [THE THING IS IF YOU CREATE GOOD META DATA,AND SUMMARIY OF THE ARTIFACT, IT CAN BE USED BY ANY AGENT, AS DEEMED NECESSARY. WHILE THE THETHER IS GOOD, THE ARTIFACT HAS MORE SCOPE OF USE, ALSO I WANT TO SEE WHAT THIS TETHER LOOKS LIKE]

  > **A:** Fair point — good metadata does give an artifact standalone
  > value beyond whatever one Memory item happened to reference it. The
  > "tether" concretely is just the `artifact_id` string field on
  > `MemoryItem` (`schemas.py`, set in `record_outcome()` at
  > `memory.py:395`) — a plain string pointer, nothing fancier. Ref-counted
  > GC as I'd implement it: load `memory.json`, collect the set of all
  > non-null `artifact_id` values across every item, then for every
  > `art:<hash>` pair of files on disk, delete it if its hash isn't in
  > that set. This doesn't conflict with your "more scope of use" point —
  > an artifact stays alive exactly as long as *any* Memory item
  > (regardless of which run wrote it) still names it, which is already
  > the broadest tether you can build without inventing a second,
  > separate metadata-driven retention system. If you want artifacts to
  > outlive their last reference on the strength of good metadata alone
  > (i.e. survive even with zero referencing Memory items, purely because
  > the sidecar `.json` looks reusable), that's a different, stronger
  > policy — effectively "never GC, rely on the directory/list feature
  > from §1.5 instead" — which is also legitimate but is a distinct choice
  > from reference-counting and should be made explicitly, not by
  > default.

- **Blind per-run wipe** — simpler, but guarantees the dangling-reference
  problem starts on the very next run for anything referenced from a prior
  run. Only really safe if you're also okay with `tool_outcome` memory
  items effectively becoming "descriptor only, forever" the moment their
  run ends.
  
[I DONT UNDERSTAND THIS ENNOUGH TO COMMENT TELL ME MORE]

> **A:** In plain terms: "blind per-run wipe" would mean, at the end of
> every run, delete every artifact created *during that run*, no
> exceptions, no checking whether anything still needs it. The problem:
> Memory is permanent (per the discussion above), so a `tool_outcome` item
> written during run #1 that points at `art:abc123` still exists in
> `memory.json` in run #2, #3, #50 — but if run #1's artifacts got blindly
> wiped the moment run #1 ended, that pointer has been dead since run #2
> even started. So this option guarantees the "descriptor only, artifact
> gone" state (§1.6 above) happens immediately and permanently for
> everything, rather than reference-counted GC's "only happens once
> genuinely nothing points at it anymore." It's simpler to implement (no
> reference scan needed) but strictly worse for exactly the reason you
> flagged above — memory being forever means a per-run wipe is really a
> per-run-plus-one-more-run wipe of usefulness. I don't recommend this
> option; see Open Question 1.

---

## 2. Vector Index — the search structure

### 2.1 What FAISS actually is here, in plain terms

Think of it as a filing cabinet built for one operation: "given this new
piece of paper, hand me the N most similar papers already filed." Every
memory item that gets embedded (turned into a list of numbers that
represents its meaning) gets added to this cabinet. A search just means:
embed the query the same way, then ask the cabinet for the nearest matches
by that same numeric representation.

[YES I UNDERSTAND BUT MEMORY STORES RUN INFROMATION, CONTEXT FOR THAT RUN, SMALL DETAILS, NOT REPORDUCIBLE INFORMATION, THE INFORMATION MEMORY STORES IS TOO CONTEXTUALISED AND VERY SPECIFIC FOR THAT PATICULAR RUN, AS IT SHOULD BE, THATS WHAT IT SHOUDLD BE LIKE AS IT MAKES THAT RUN THE BEST PEROFMRING RUN AS IT GETS AS MUCH CONTEXT AS POSSIBEL BUT THEN DO YOU NOT RISK SHIFTING THE CONTEXT AND DIRECTION OF THE NEXT RUN IN A DIRECTION OF THE PREVIOUS RUN ? WORKS A LITTLE BIT LIKE A SELF LEARNING TAILORED LOOP MAYBE A BIT LIKE HERMES AGENT, BUT NOT AS WELL AS THAT SO IS DOING MORE DAMAGE THAN GOOD MAYBE ? ]

> **A:** This is the sharpest catch in the whole document, and it's not
> hypothetical — I checked, and it's confirmed in the live code path.
> `agent7.py:179` calls `memory.read(query, history, query_vec=query_vec)`
> at the top of every round with **no `kinds=` filter at all**. That means
> `_vector_search` (`memory.py:170-198`) ranks `fact`, `preference`, and
> `tool_outcome` items together, indiscriminately, against whatever the
> current query embeds to — with zero recency weighting and zero
> run-scoping. So yes: a completely unrelated `tool_outcome` from a
> previous run (e.g. "checked the weather, it was rainy" or "fetched
> exchange rate X") can outrank something actually relevant to the current
> run purely because it happens to be the nearest cosine match among a
> currently-small item set, and there is no signal anywhere telling the
> model "this hit is from a different run, three days ago, possibly
> stale." Your Hermes-agent comparison is apt — this is structurally a
> self-conditioning loop (past runs bias future retrieval) without any of
> the safeguards a system like that would need (no recency decay, no
> run-boundary awareness, no volatility flag — see §1.6's new fact-expiry
> discussion). At today's scale (few hundred items, presumably one user)
> it likely doesn't bite often because there just isn't enough volume to
> produce confidently-wrong matches. It will start to matter as the store
> grows, and it compounds directly with the missing fact-expiry gap: an
> old, stale, but confidently-embedded fact is exactly the kind of thing
> that would win a `kinds=`-unfiltered, decay-free vector search. I'd treat
> "add `kinds=` filtering at call sites where the goal type is known" and
> "add basic recency-awareness to scoring" as real, not cosmetic, fixes —
> worth scoping alongside the fact-expiry work in §1.6, since they're the
> same underlying problem (memory has no sense of time) showing up on the
> write side and the read side respectively.

### 2.2 Why `IndexFlatIP` specifically, and why that's *not* a shortcut

FAISS offers many index types. This code uses the simplest one:
`IndexFlatIP` — "Flat" means no approximation, no clustering, no tree
structure; every single stored vector is compared against the query,
every time. "IP" means inner product, which (once every vector is
length-normalized, which `_l2_normalize()` does) is mathematically
identical to cosine similarity — the standard way to measure "how similar
are these two pieces of meaning."

The alternative — approximate indexes like HNSW or IVF — trade a small
amount of accuracy for a lot of speed, but that trade only starts paying
off once brute-force comparison actually becomes slow, which happens at
tens of thousands to millions of vectors. At the scale this project
actually has (one person's memory — hundreds to low-thousands of items),
exact brute-force is not just adequate, it's *strictly better*: same
speed in practice, zero approximation error, zero tuning parameters to get
wrong. This is a case where the simple choice is the correct choice, not a
corner cut for later.

[THE ONLY ISSUE IS THAT WHATS THE GATING, SO DO WE PULL THINGS WITH COSINE SCORES GREATER THAN 0.80 THAN 0.7 WHATS THE GATE, AS RARELY IS SOMETHING GOING TO BE EXACTLY THE SAME RIGHT ?, I REALLY WANT TO DO A BETTER ANALYSIS ON WHAT THIS DOES AND CONTRIBUTES TO THE LARGER PICTURE]

> **A:** There is **no gate at all today** — worth stating plainly since
> it wasn't called out explicitly before. `VectorIndex.search()`
> (`vector_index.py:110-121`) returns the top `min(k, ntotal)` results
> ranked by score, full stop; there is no minimum-similarity threshold
> anywhere in `search()`, `_vector_search()`, or `read()`. Concretely:
> if the vector index has 3 items in it and none of them are remotely
> related to the query, `search(k=8)` still returns all 3, sorted best-to-
> worst, with (say) a top score of 0.31 — and because `_vector_search`
> treats any non-empty hit list as success (`if vec_hits: return vec_hits`,
> `memory.py:210-213`), the keyword fallback never even gets a chance to
> run, since a weak vector hit still counts as "vector search found
> something." So a bad match can both (a) get surfaced to the model with
> no indication it's a bad match, and (b) actively suppress the keyword
> fallback that might have found something better. This directly
> compounds the §2.1 cross-run-bleed risk. I don't have a principled
> number for you (0.7 vs 0.8 is genuinely dataset- and embedding-model-
> dependent, and picking one without real query/hit examples to tune
> against would just be a guess dressed up as a decision) — but I'd
> treat "add *some* minimum-score floor below which a hit doesn't count as
> found" as a real, checkable fix, separate from picking the exact number,
> which should come from looking at actual score distributions once you
> have a live trace (blocked on the mcp_server fix, §4).

### 2.3 The id-mapping trick

FAISS only knows vectors by their integer position (vector #0, #1, #2...).
It has no concept of "this is memory item `mem:a1b2c3`." So `VectorIndex`
keeps a plain Python list, `self._ids`, in the exact same order vectors
were added — position 47 in that list is the string id for vector #47 in
FAISS. This is why `add()` appends to both structures together, and why
`search()` translates FAISS's returned integer positions back through
`self._ids` before handing results to the caller. It's a simple parallel
array, not a database join — deliberately minimal. [THIS IS USEFUL FOR RETRIEVAL ?? WHAT IS IT ACTUALLY USED FOR ?, PULL NUMBER 47 ? BUT COSINSE SIMILARITY SHOULD RETURN SIMILAR INDEX VECTORS RIGHT ? WHICH JUST NEED TO BE DECRYPTED, SORRY NOT SURE ABOUT THIS ]

> **A:** Nothing needs "decrypting" — it's a plain lookup, not encoding.
> Walk through `search()` (`vector_index.py:110-121`) concretely: FAISS's
> `self._index.search(...)` returns two parallel arrays — `scores`
> (similarity numbers) and `idxs` (integer *positions*, e.g. `[47, 12, 3]`
> meaning "the 48th, 13th, and 4th vectors ever added were the best
> matches"). FAISS has zero concept of what a "memory item" is — it only
> ever speaks in these bare integer positions. So the code does
> `self._ids[idx]` for each returned position — e.g. `self._ids[47]` might
> be the string `"mem:a1b2c3"` — turning "position 47" into "the actual
> memory item id that was the 48th thing ever embedded." That's the whole
> trick: FAISS's output is integers with no meaning outside this process;
> the parallel list is what re-attaches meaning to them. It's used for
> *every* search, not a special case — without it, `_vector_search`
> (`memory.py:189-195`) would have no way to turn "vector #47 is the best
> match" into "here's the actual `MemoryItem` to show the LLM." Cosine
> similarity does return the *positions* of the most similar stored
> vectors (correct instinct), it just doesn't know or care what those
> positions "mean" — the id list is what supplies the meaning after the
> math is done.

### 2.4 Two files, and why they're rebuilt from scratch on drift

Persistence is two separate files: `index.faiss` (FAISS's own binary
format) and `index_ids.json` (the parallel id list). They're written
together, atomically (temp file + rename, same pattern as `memory.py`).
`memory.py`'s `_index()` function checks, on every read, whether the
FAISS file's vector count and id list still line up with what
`memory.json` currently says should be embedded — if they've drifted (say,
`mcp_server` wrote new items to `memory.json` but the index file is stale),
the whole index gets rebuilt from `memory.json` rather than trying to
patch the difference incrementally. This is a "when in doubt, start over"
design — safe, a bit wasteful, but drift should be rare and the rebuild
cost is small at this scale.

[HOW DO YOU DECIDE WHATS DRIFT, HOW DOES AGENT KNOW XXXVVVCCC IS NUMBER 16 NOT 15 ? WHATS THE PROOF ? WHATS THE BREADCRUMBS USED ?]

> **A:** The exact check is `memory.py:99-106`:
> ```python
> embedded_ids = [item.id for item in _embedded_items(items)]   # from memory.json
> idx = VectorIndex(STATE_PATH.parent)                          # loaded from disk
> if idx.size != len(idx.ids) or idx.ids != embedded_ids:
>     idx = _rebuild_index(items)
> ```
> There's no "proof" involved and no per-item position tracking beyond
> what's already described in §2.3 — "drift" is detected by comparing two
> whole lists: the list of ids the FAISS index currently claims to have
> (`idx.ids`, loaded from `index_ids.json`), and the list of ids
> `memory.json` says *should* be embedded right now (`embedded_ids`,
> computed fresh from the JSON file). If those two lists aren't
> identical — same ids, same order — something's out of sync (e.g. the
> `mcp_server` subprocess appended a new fact to `memory.json` but hasn't
> also updated the FAISS files, or vice versa), and rather than figuring
> out exactly *which* item is missing/extra, the code just throws the
> whole FAISS index away and rebuilds it from `memory.json` from scratch
> (`_rebuild_index`, `memory.py:76-83`) — re-embedding nothing (embeddings
> are already stored on each `MemoryItem`, so rebuild just re-adds
> existing vectors to a fresh `IndexFlatIP`, no LLM calls involved). So
> there's no "how does the agent know xxx is #16 not #15" question to
> answer — when in doubt, the position-to-id mapping isn't patched at all,
> it's regenerated wholesale from the one source of truth (`memory.json`),
> which is why this drift-detection can afford to be this blunt.

### 2.5 The one real inefficiency (parked-tier, not urgent)

`_index()` reloads the entire FAISS file from disk and re-checks the full
id list on *every single* `memory.read()` call, even within the same
process, same run. It's correct, but it's redoing work that could be
cached in-process. Not worth fixing until this is actually measured as
slow — flagged in `TODO.md` §7 as parked-tier. [THIS IS MORE COMPLEX BUT STILL SOMETHING WE NEED TO LOOK AT, HOW DO WE EFFICIENTLY CACHE THIS ? HOW IS IT READ AND IF THERES ANY VALUE TO THE ADDED COMPLEXITY ?]

> **A:** The read path today, concretely: every call to `memory.read()` →
> `_vector_search()` → `_index()` (`memory.py:86-108`) does a full disk
> read of `index.faiss` + `index_ids.json` and a full `_load()` of
> `memory.json`, *every single time*, even if nothing changed since the
> last call ten milliseconds ago in the same process. A simple in-process
> cache would be: keep the loaded `VectorIndex` and the drift-check result
> in a module-level variable, and only re-run `_load()`/drift-check when a
> write happened (i.e. invalidate the cache inside `_persist_item()`
> instead of on every read). The complexity that adds: you now need to
> make sure every write path that touches these files (including the
> `mcp_server` subprocess writing independently) properly invalidates that
> cache, which reintroduces exactly the kind of cross-process coordination
> problem content-addressing was designed to avoid elsewhere in this doc
> (§1.2). Given the current scale (loading a few-hundred-item JSON file
> and a small FAISS index is genuinely cheap — low milliseconds), I'd
> agree with parking this: the correctness risk of a subtly-stale
> in-process cache is a worse trade than the CPU cost of reloading small
> files repeatedly. Worth revisiting only once real profiling shows
> `_index()` actually costing meaningful time in a live run.

---

## 3. Memory — the record layer

[A LOT OF THE COMMENTS I HAVE FOR THIS LAYER HAVE BEEN WRITTEN IN VECDB SECTION, ASSUMING THAT THEY ARE BOTH THE SAME FUNCTION AND WORK HAND IN HAND]

> **A:** Reasonable assumption and mostly right — Memory is the layer that
> *calls* the vector index and interprets its results, so most of your
> vector-index questions really were Memory questions wearing a §2
> costume. I've answered the vector-specific mechanics in §2 and focused
> the answers below on what's actually specific to Memory: the four
> kinds, the three write paths, and the concrete bug in §3.4.

This is the biggest of the three, because it's the one component that
actually understands what's being stored, and it's where the real bug
lives.

### 3.1 The four kinds, and why four instead of one generic type

- **`fact`** — something learned about the world or the user (a birthday, a
  document's content chunk). Persistent, meant to be found again by topic.[FACT MEANS FACT THAT IS TRUE, AND FACT MEANS SOEMTHING THAT IS TRUE AT THAT MOMENT, BUT NOT TRUE FOR MUCH LONGER AFTER THAT, TIME IS TRUE AT THAT MINUTE, BUT NOT AFTER THAT, DAY GOING WELL IS TRUE ON FOR THAT DAY, ANXIOUS FEELING/STOCK PRICE IS TRUE FOR THAT SECOND/WEATHER FOR THOSE RFEW HOURS AND TRAVEL PLANS FOR THAT WEEK (SAD FACT. BUT TRUE)]

  > **A:** This is exactly the fact-volatility gap I flagged under §1.6 —
  > you've independently landed on the same problem from the kind-taxonomy
  > side. The `kind: "fact"` label in the code carries none of the
  > distinctions you're drawing here (birthday vs. stock price vs.
  > weather vs. travel plans currently all get written identically, as
  > plain `fact` items with no expiry). I think the fix isn't a 5th kind
  > though — it's an orthogonal attribute *on* the existing kinds (a
  > volatility/expiry field that `fact`, `preference`, and `tool_outcome`
  > can all carry), since your own examples span multiple existing kinds
  > (a stock price is a `fact`, "day going well" sounds more like a
  > `scratchpad`-ish transient observation) — see the consolidated
  > recommendation under §1.6.

- **`preference`** — something learned about how the user wants things done.
  Same persistence as `fact`, kept separate so retrieval/prompting could
  someday treat "the user prefers X" differently from "the user told me Y
  happened" — right now they're handled identically at read time, but the
  kind label keeps that door open.

[YES TRUE AND USEFUL, BUT HOW DO YOU SEGREGATE THESE FROM AN INTERACTION, HOW DO YOU KNOW WHATS A FACT AND WHATS A PREFERENCE? HOW DO YOU KNOW THAT THIS SHOUDL BE STORED HERE AND IN THIS WAY, VS THIS SHOUDL BE STORED HERE AND IN THIS WAY. YES EXACTLY YOUR EXAMPLE Y HAPPENED ITS A FACT TRUE ONLY FOR A SMALL PERIOD OF TIME VS THIS IS HOW I REACTED TO THIS, THATS USER PREFERES Y, THIS IS HOW HE REACTS, THIS IS HOW THEY WORK, USER HAS SAID THAT HE WANTS TO CHANGE THIS ABOUT HIS REACTION, OR HE REACTS THIS WAY.]

[ITS A GOOD IDEA, BUT REALLY A BLACK HOLE IN TERMS OF IMPLEMENTATION, BECAUSE THE SURFACE AREA, IS TOO LARGE, FOR THINGS TO BREAK]

> **A:** The segregation is a single LLM judgment call, nothing more
> structured than that. In `remember()` (`memory.py:277-326`), the
> classifier prompt (`_llm_classify`, `memory.py:329-355`) literally asks
> the model to pick `kind ∈ {fact, preference, tool_outcome, scratchpad}`
> for whatever free-form text it's given, with no worked examples of
> fact-vs-preference in the prompt beyond a birthday-descriptor example
> that doesn't touch preference at all. So there is no deterministic rule
> distinguishing "user reacted this way" (arguably a `fact` about a past
> event) from "user prefers to be told things this way" (a `preference`
> about future behavior) — it's whatever the classifier LLM decides,
> unaudited, on a single pass, at `temperature=1.0` (see §3.8). I think
> your "black hole" instinct is correct and important: this is the exact
> kind of surface where trying to formalize a clean taxonomy invites
> exactly the kind of scope creep you'd want to avoid (per your own answer
> to Open Question 2 — no filter/ranker for now). My recommendation is the
> same one as elsewhere in this doc: don't build a stricter taxonomy or
> more classifier examples speculatively; if fact/preference confusion
> shows up as an actual retrieval problem once there's a live trace to
> look at, fix it with concrete examples from what actually went wrong,
> not in the abstract now.

- **`tool_outcome`** — a record of "this tool ran with these arguments and
  produced this." Written automatically, not by LLM judgment — see §3.3.

[YES AND THE TOOL OUTCOME SHOULD BE STORED, THIS TAG SHOULD BE PRESENT IN MEMORY AND ARTIFACT, AND SHOULD BE SUFFICIENTLY DIFFERENTATED, FROM LLM OUTPUT OR DECISION THOUGHT PROCESS, OR PERCEPTION THOUGHT PROCESS, OR LLM CALL OUTPUTS]

> **A:** It already is differentiated, structurally, today — worth
> confirming this one's in good shape. `record_outcome()`
> (`memory.py:358-401`) is the *only* path that ever produces
> `kind="tool_outcome"`, and it's called from exactly one place
> (`agent7.py`, right after `decision.py`'s `_run_goal` returns a tool
> result) — never from Decision's synthesis answers, never from
> Perception's planning output, never from a raw LLM chat reply. Synthesis
> answers (the LLM just answering directly, no tool call) don't get
> written to Memory as `tool_outcome` at all — they only show up as
> `output_descriptor` on the transient `GoalResult` object, which lives
> only for the duration of the current run's `prior_results` list
> (`decision.py:_format_results`), not persisted to `memory.json`. So
> "LLM output / Decision's own reasoning" already isn't mixed into
> `tool_outcome` — the confusion risk isn't cross-contamination between
> kinds, it's the separate `record_outcome()` bug in §3.4 (the descriptor
> discarding the useful preview) — that's the thing actually worth fixing
> here, not the tagging/differentiation itself.

- **`scratchpad`** — explicitly run-scoped, and the *only* kind that skips
  embedding entirely (`_EMBEDDABLE_KINDS = {"fact", "preference",
  "tool_outcome"}`). The idea is that scratch content is only useful within
  the run that created it, so there's no point paying for an embedding that
  will never usefully match a future query.

  [YES IT IS, THIS IS USEFUL, JUST THE THING IS THAT THE LINES ARE GETTING MURKY, BETWEEN THE 4 AND I WANT TO KNOW HOW THE DIFFERENTIATION IS HAPPENING AND HOW IS THE ROUTING HAPPENING.]

  > **A:** Worth being precise about which kinds are actually
  > LLM-classified vs. structurally guaranteed, because they're not the
  > same risk level. `tool_outcome` and `fact`-from-documents (via
  > `add_fact()`) are **never** ambiguous — they're set by construction in
  > code, not by LLM judgment (see §3.3's table). The *only* place "the
  > lines get murky" is inside `remember()`'s classifier call, which has
  > to choose between all four kinds including `scratchpad`, for
  > free-form text with no other signal. So the murkiness you're sensing
  > is real, but it's scoped to one write path, not spread evenly across
  > all four kinds — `record_outcome()` and `add_fact()` can't misfire on
  > kind at all, structurally. Where I'd focus concern: `scratchpad` vs.
  > `fact` inside `remember()`'s classifier, since getting that wrong in
  > either direction is costly — miss-classifying a genuinely durable fact
  > as `scratchpad` silently makes it permanently unsearchable (skips
  > embedding, per `_EMBEDDABLE_KINDS`), while miss-classifying transient
  > scratch content as `fact` feeds directly into the §1.6/§2.1 stale-fact
  > problem.

### 3.2 The read path — why vector-first, keyword-fallback, not vector-only

```python
def read(query, history=None, *, kinds=None, top_k=8, query_vec=None):
    vec_hits = _vector_search(...)
    if vec_hits:
        return vec_hits
    kw_hits = _keyword_search(...)   # only runs if vector search found nothing
    return kw_hits
```

Vector search is tried first because it understands meaning, not just
words — it can match "what's my mom's birthday" against a stored fact
about "Mom's birthday is 15 May" even if none of the same words overlap.

[HOW ? HOW DOES IT DO THIS ?]

> **A:** Mechanically, in three steps: (1) an embedding model (called via
> the gateway's `/v1/embed` endpoint, `_try_embed`, `memory.py:111-125`)
> converts each piece of text into a fixed-length list of numbers — this
> model was trained on huge amounts of text such that pieces of text with
> similar *meaning* end up as numerically nearby lists, even when they
> share zero literal words ("mom's birthday" and "May 15th, my mother's
> special day" would land close together numerically despite no word
> overlap). (2) the query "what's my mom's birthday" gets embedded the
> same way, at read time. (3) FAISS's `IndexFlatIP` (§2.2) finds which
> stored embeddings are numerically closest to the query's embedding by
> cosine similarity — a pure geometry operation, comparing angles between
> number-lists — and returns those. Nothing here understands English in
> the way a person does; the embedding model already did that work once,
> upstream, when it was trained, and everything downstream (FAISS,
> `_vector_search`) is just fast numeric comparison of the outputs of that
> one trained model.

Keyword search only runs as a fallback, for two reasons that are both real
failure modes, not defensive theater: (1) the embedding gateway call can
fail (network, provider outage) — `_try_embed()` catches that and returns
`None`, and a `None` query vector means vector search can't run at all;

[YEAH THATS TRUE BUT VECTOR SEARCH DOESNT THAT REQUIRE EMBEDDING?? HOW ARE YOU GOING TO SERACH A VEC DB WITH FAISS EMBEDDED MEMEORY LINES WITHOUT EMBEDDING THE QUERY?]

> **A:** You're right to catch this — the phrasing above was ambiguous,
> not wrong, but worth being precise: vector search absolutely still
> requires embedding the query; there's no way around that, and nothing
> in the code claims otherwise. What that sentence meant is narrower:
> `_try_embed()` (`memory.py:111-125`) wraps the embedding call in a
> `try/except` and returns `None` on failure instead of raising. `read()`
> passes that possibly-`None` `query_vec` down to `_vector_search`
> (`memory.py:170-179`), which checks `if qvec is None: return []` —
> i.e. if the embedding call itself failed, vector search doesn't crash,
> it just returns *zero results*, which `read()` then treats the same as
> "vector search legitimately found nothing" and falls through to keyword
> search. So it's not "vector search runs without an embedding" — it's
> "when embedding fails, vector search is skipped entirely (returns
> empty), and the *keyword* path becomes the only path that can still
> produce results," since keyword search (`_keyword_search`,
> `memory.py:144-165`) works off raw token overlap and needs no embedding
> call at all. That's reason (1) properly stated.

(2) the vector index can legitimately be empty (nothing embedded yet, or
everything in it happens to be irrelevant to this query) and still return
zero results even though a keyword match would have found something.
Keeping the older keyword path alive as a fallback, instead of deleting it
once vector search was added, is what makes memory degrade gracefully
instead of going completely blind when the gateway is down. 

[YES BUT THEN HOW DO YOU TRIGGER THE FALLBACK AND WHENDO YOU TRIGGER THE FALLBACK, IS THE FLALBACK SHOULD BE A PARALLEL RUN ? TAKE BOTH, DEDUP ?]

> **A:** Today it's purely sequential, not parallel — `read()`
> (`memory.py:201-219`) calls `_vector_search()` first, and only calls
> `_keyword_search()` `if not vec_hits:` (i.e. the vector call returned an
> empty list, for *either* of the two reasons above — embedding failed,
> or embedding succeeded but zero hits came back, including the "weak
> match still counts as a hit" caveat from §2.2 which means this fallback
> triggers less often than you might want, since a bad-but-nonzero vector
> hit list currently blocks the fallback from ever running). Running both
> in parallel and deduping is a reasonable alternative design (classic
> hybrid/RRF retrieval, which the module's own docstring at the top of
> `memory.py` already names as a planned future step: "Vector retrieval
> only. Hybrid retrieval with RRF arrives in a future session.") — so this
> isn't an oversight, it's an explicitly deferred piece of the design, not
> yet built. I'd note that combining it with a minimum-similarity gate
> (§2.2) would probably get you most of the benefit of full hybrid/RRF
> retrieval more cheaply: fix "a bad vector hit blocks the keyword
> fallback" first, and evaluate whether you still need true parallel
> hybrid search after that.

### 3.3 The three write paths — why three, not one

[SO MY QUESTION IS THAT A LOT OF THE TOOLS REQUIRE LLMS, AND RUN WITH LLMS, CONVERT THIS INTO A SUMMARY, DO THIS, DO THAT, BUT IF WE LIVE BY THE DEIFINITION OF THE TOOL AND SAY THAT TOOLS CANT HAVE LLMS, HOW DO PEOPEL TRIGGER LLM CALLS ??]

> **A:** Worth separating two things that are getting merged here: MCP
> *tools* (the things `action.py:execute()` calls via `session.call_tool`
> — `fetch_url`, `read_file`, `index_document`, etc.) are pure I/O in this
> codebase today; none of them call an LLM internally — `index_document`'s
> chunking, for instance, is described in this doc's own docstring as
> "heuristic sliding-window," not LLM-driven summarization. The LLM calls
> in this whole stack happen at the *cognition* layer, above the tools:
> `decision.py` calls an LLM to decide which tool to call and to
> synthesize answers; `memory.py`'s `remember()` calls an LLM to classify
> free-form text. There's no architectural rule written down anywhere
> saying "a tool must never call an LLM internally" — it's just that none
> of the current tools happen to. If you wanted a tool that, say,
> summarizes a document using an LLM as part of its own execution,
> nothing here forbids building one — it would just be an MCP tool whose
> implementation happens to call the gateway itself, same as `decision.py`
> does. That would be a legitimate way to "trigger an LLM call from a
> tool," it's just not how any tool is built today.

| Function | Used for | LLM calls | Kind is... |
|---|---|---|---|
| `remember()` | free-form, ambiguous text (the user's raw query) | 1 (classify) + 1 (embed) | decided by the LLM |
| `record_outcome()` | a tool just ran | 0 | always `tool_outcome`, by construction |
| `add_fact()` | document indexing (`index_document`) | 0 | always `fact`, by construction |


[SO YOU HAVE REMEMBER AS WELL I DONT REMEMBER IT BEING MENTIONED WITH FACTS OR PERCEPTION OR ANTYHING WHATS NEW HERE ?]

> **A:** Nothing new — `remember()` isn't something added by this doc, it
> already exists and is already wired in: `agent7.py:153` calls
> `memory.remember(query, source="user_query", run_id=run_id)` once, at
> the very top of every run, on the user's raw incoming query specifically
> (not on Perception's or Decision's outputs). It's the module's oldest
> write path per its own docstring ("Session 6" service, vector retrieval
> added "Session 7") — it's just the one of the three write paths that
> hadn't come up yet in earlier discussion because it's the "boring"
> default path with no bug in it, unlike `record_outcome()` (§3.4).

The split exists because **only `remember()` actually has an ambiguous
input** — arbitrary text where "what kind of thing is this and what are
the important keywords" genuinely requires judgment. `record_outcome()`
and `add_fact()` already know their own kind and already have structured
inputs (a `ToolCall` object, a text chunk with a known source) — running
an LLM classification call over something whose shape is already known
would just be spending money and latency to re-derive information the
caller already has. This is a real efficiency-vs-correctness tradeoff
made correctly: skip the LLM exactly where it adds no information.

[I NEED MORE INFROMATION ON THIS OVERALL, JUST OVERALL EXPLANANTION, WHY DOES IT EXIST, HOW DOES IT WORK ?]

> **A:** Zooming out to the full picture: Memory needs, for every item it
> stores, three things — a `kind`, a `descriptor` (short text used both
> for display and for embedding), and a `value` (structured payload). The
> question each write path answers differently is *where those three
> things come from*:
> - `remember(raw_text, ...)` — called once per run on the user's raw
>   query (`agent7.py:153`). The input is just a string with no other
>   structure, so an LLM call (`_llm_classify`, `memory.py:329-355`) is
>   the only way to produce `kind`/`descriptor`/`value` from it. This is
>   the expensive path (2 LLM calls: 1 classify + 1 embed) and the only
>   one where kind is genuinely uncertain.
> - `record_outcome(tool_call, result_text, artifact_id, ...)` — called
>   once per tool call, from `agent7.py`, right after `decision.py`
>   returns a tool result. The caller already has a `ToolCall` (name +
>   arguments, a structured Pydantic object) and the tool's raw text
>   result — there's nothing to classify, `kind` is hardcoded to
>   `"tool_outcome"` (`memory.py:387`), and `descriptor`/`value` are built
>   by plain string formatting (`memory.py:377-393`, where the bug in §3.4
>   lives). Only 1 LLM call (embed only, no classify).
> - `add_fact(descriptor, value, ...)` — called once per document chunk
>   from the (currently broken, per TODO.md §7) `index_document` MCP tool.
>   The caller already knows it's indexing a document chunk, so `kind` is
>   hardcoded to `"fact"` (`memory.py:418`) and the descriptor/value come
>   straight from the chunking logic, not an LLM. Same 1-LLM-call
>   (embed-only) shape as `record_outcome`.
>
> So "why does it existःthree functions instead of one" comes down to:
> one function exists to handle genuine ambiguity (costs 2 LLM calls),
> and two exist to skip paying for a classification call the caller
> already has the answer to (cost 1 LLM call — embedding is unavoidable
> for any embeddable kind, classification isn't). All three ultimately
> funnel into the same `_persist_item()` (`memory.py:233-250`) for the
> actual disk/index write, so the split is purely about *how the record's
> fields get populated*, not about how it's stored.

### 3.4 The write path that actually breaks — full trace

This is the concrete answer to "how does a large thing get summarized to
fit in memory," and the honest answer is: for anything that got offloaded
to an artifact, **it doesn't get summarized — it gets discarded.** Here is
the exact chain, file by file:

[THATS BAD VERY BAD]

> **A:** Agreed, and confirmed by re-reading the exact lines — this is a
> genuine bug, not an exaggeration. See the fix recommendation at the end
> of this trace and in Open Question 3.

**Step 1 — `action.py` computes a genuinely useful preview:**
```python
descriptor = f"[artifact {art_id}, {nbytes} bytes] preview: " + text[:240] + "..."
return descriptor, art_id
```
240 characters of actual content, plus the handle. This is good — this is
exactly the kind of summary you'd want to persist.

**Step 2 — that preview flows up as `GoalResult.output_descriptor`** in
`decision.py`, unchanged.

**Step 3 — `agent7.py`'s loop hands it to Memory:**
```python
memory.record_outcome(
    tool_call=result.tool_call,
    result_text=result.output_descriptor,   # <- the 240-char preview, intact so far
    artifact_id=result.artifact_id,
    ...
)
```

[so record_outcome() is to read from the class defined data flowing upwards ?]

> **A:** Yes exactly — `record_outcome()`'s parameters
> (`tool_call`, `result_text`, `artifact_id`) are just the same
> `GoalResult` fields that flowed all the way up from `action.execute()` →
> `decision._run_goal()` → `agent7.py`'s loop, passed through unchanged at
> each hop. `record_outcome()` is the first place any of them get *used*
> to decide what to permanently write, rather than just carried along.

**Step 4 — and this is where it breaks, inside `record_outcome()`:**
```python
descriptor = f"{tool_call.name}({json.dumps(tool_call.arguments)[:80]}) -> "
if artifact_id:
    descriptor += f"artifact {artifact_id}"       # <- result_text is IGNORED here
else:
    descriptor += result_text[:120].replace("\n", " ")
```
[WE REDEFINE THE DESCRIPTOR ? WHY WHATS HAPPENING HERE ?]
[SO WE ARE DEFINING THE DESCRIPTOR, (NAME NEEDS TO BE CHANGED), CREATING WITH THE TOOL NAME, HAND THE DUMP OF, OF THE FIRST 80 CHARACTERS, ARE STORED IN THE MEMORY, AND TO THAT WE ADD THE ARTIFACT ID, OR WE ADD THE RESULTS TEXT ADDING THE FIRST 120 CHARACTERS ? WHATS THE LOGIC OF THAT]

> **A:** Your read of the mechanics is exactly right — that's precisely
> what the four lines do. What's happening is `record_outcome()` builds
> its *own*, brand-new descriptor from scratch, starting from
> `tool_call.name` and `tool_call.arguments` (which it has directly, as a
> `ToolCall` object — this is the "structured input, no need to reclassify"
> point from §3.3), and only *then* decides how to append the "what
> happened" part: if there's an `artifact_id`, it appends just the literal
> string `artifact art:xxx`; otherwise it appends the first 120 characters
> of `result_text`. The bug is exactly the branch you circled: when an
> artifact_id exists, `result_text` (the caller's whole point in passing
> it — the 240-char preview from Step 1) is never even looked at for the
> descriptor. There's no logical justification for this asymmetry visible
> anywhere in the code or comments — it reads like whoever wrote this
> branch assumed "if there's an artifact, the id is enough, the bytes are
> still there if anyone needs them," without noticing that `result_text`
> at that point *already contains* a rich preview specifically computed in
> `action.py` for exactly this purpose (Step 1), and it just gets dropped
> on the floor.

The preview that survived three layers intact gets thrown away in exactly
the one branch where it mattered most (the branch that only runs when the
content was big enough to be worth summarizing well in the first place).
What actually gets permanently stored as the descriptor is just
`"fetch_url({'url': '...'}) -> artifact art:a1b2c3"` — the tool name and
its arguments, nothing  about what was found.

[SO WHERE IT WAS FOUND WHAT WAS THE ARTIFACT ID TO CALL IT, BUT NOT WHAT WAS FOUND]

> **A:** Exactly right — that's the precise, accurate summary of the bug
> in one sentence.

**Step 5 — this contentless descriptor is what gets embedded:**
```python
embedding = _try_embed(descriptor, task_type="retrieval_document")
```
So vector search over this memory item can only ever match on the tool
name and argument text — never on the actual content that was fetched.
Searching "what did that page say about pricing" will never find this
item by meaning, only a literal match on the URL or tool name would.

[YEAH THIS IS STUPID]

> **A:** Agreed — no defense of this one, it's a straightforward bug with
> a straightforward fix (Open Question 3).

**Step 6 — there IS a field that keeps the fuller preview, but it's never
read:**
```python
value={
    "tool": tool_call.name,
    "arguments": tool_call.arguments,
    "result_preview": result_text[:400],   # <- the preview, up to 400 chars, IS here
},
```
[WHY IS IT NEVER READ??]

> **A:** Because `_format_hits()` in `decision.py` (the function that
> decides what gets shown to the LLM, `decision.py:66-92`) only ever
> checks two specific key names inside `value` — `val.get("raw")` and
> `val.get("chunk")` — and `result_preview` is neither of those names. It
> falls into the final `else` branch, which builds a `compact` dict that
> explicitly filters out any string field longer than 200 characters
> (`decision.py:85-88`): `not (isinstance(v, str) and len(v) > 200)`. A
> 400-character `result_preview` fails that filter every time, so it's
> stripped out of `compact` and never makes it into the prompt. This looks
> like two pieces of code written at different times that never got
> reconciled — whoever added `result_preview` to `record_outcome()`
> apparently didn't update `_format_hits()` to look for it, and whoever
> wrote `_format_hits()`'s `raw`/`chunk` check didn't know `record_outcome`
> would someday need a third key recognized.

But `decision.py`'s `_format_hits()` — the function that decides what a
memory hit actually shows the LLM — only ever looks at `value["raw"]` or
`value["chunk"]`:
```python
raw = val.get("raw")
chunk = val.get("chunk")
if isinstance(raw, str) and raw.strip(): ...
elif isinstance(chunk, str) and chunk.strip(): ...
else:
    compact = {k: v for k, v in val.items() if k != "chunk" and not (isinstance(v, str) and len(v) > 200)}
```
`result_preview` is neither `raw` nor `chunk`, so it falls into the
`compact` fallback branch [WHAT ACTUALLY IS RAW OR CHUNK ?] — which explicitly filters out any string field
longer than 200 characters. A 400-char preview never survives that filter.
**It is written on every single tool_outcome item and never displayed
anywhere, to anyone, ever.**

> **A:** `raw` is the key `_fallback_remember()` (`memory.py:268`) and the
> classifier path in `remember()` use when the LLM classifier didn't
> produce a more structured `value` — it's literally
> `{"raw": raw_text}`, the original, un-truncated free-form text the user
> or classifier gave. `chunk` is the key `add_fact()`'s caller
> (`index_document`, outside these files) is expected to put the actual
> document-chunk text under, based on `_format_hits()` explicitly checking
> for it and treating it as document content with a `source`
> (`decision.py:79-83`). So both are "the actual substantive text content
> of this memory item, under a specific expected key name" —
> `record_outcome()` is the one write path that invented a third key
> (`result_preview`) instead of reusing one `_format_hits()` already
> recognized, which is the root cause of it never displaying.

Net effect: for any tool result big enough to be offloaded to an artifact,
memory's permanent record of it is, for all practical purposes, blind —
findable only by tool name/arguments, describable only as "artifact
art:xxx," with a perfectly good 400-character preview sitting inert in a
field nothing reads.

[SO THIS IS ONLY HAPPENING WHEN THE ARTIFACT IS BEING STORED ? ELSE DOESNT HAPPEN ? ]

> **A:** Correct — confirmed by the exact branch in Step 4. When there's
> no `artifact_id` (result was ≤4KB, no artifact created), the `else`
> branch runs: `descriptor += result_text[:120]...` — so `result_text`
> *is* used for the descriptor in that case, just truncated to 120 chars
> (which is its own, smaller problem — see §3.5 right below). The
> descriptor-discarding bug specifically, only fires in the `if
> artifact_id:` branch — i.e. specifically and only for results big
> enough to have been worth summarizing well in the first place. Small
> results get a worse-but-present 120-char summary; big results
> (paradoxically, the ones that most needed a good summary) get none at
> all beyond the tool name/arguments.

### 3.5 The truncation cliff for results that *don't* get an artifact

Even when a tool result is small enough (≤4KB) to skip artifact creation
entirely, the *permanent* record is still capped — 120 characters in the
descriptor, 400 in `result_preview`. So a 3KB result (well under the 4KB
artifact threshold, so no backup bytes exist anywhere) still only survives 
long-term as 400 characters [THIS IS PORBABLY THE WORST OF THEM ALL I WONT LIE, I AM DEBATING IF IT MAKES SNESE TO NOT HAVE A RECORD OF MEMORY ?? IF ITS BETTTER THAT WE STORE THE FULL THING AND THEN TRUNCATE IT WHEN WE DISPLAY IT BUT THEN IT JUST BECOMES AN ARTIFACT, WHATS THE POINT OF THAT, ]. There's a real gap between "small enough that
we didn't bother making an artifact" and "small enough that we actually
kept all of it" — anything roughly 400 bytes–4KB loses information
permanently with no fallback copy anywhere.

> **A:** I don't think this is "the worst of them all" once you separate
> it from §3.4 — but your instinct that something's inconsistent here is
> right, and your proposed fix (store the full thing, truncate only at
> display time) is exactly correct and cheap. The reason "store full,
> truncate on display" doesn't just become "everything is an artifact":
> the artifact threshold (4KB) is about keeping the *inline prompt/JSON*
> small on every read, not about whether the *disk record* is complete.
> `memory.json` already stores full Python dicts with no fixed-size
> constraint of its own — the 120/400-char caps in `record_outcome()`
> are a self-imposed truncation at *write* time, not a structural limit of
> the storage format. So the actual fix is small: store
> `result_text` (the whole thing, up to whatever `action.py` already
> decided doesn't need an artifact — i.e. ≤4KB) in `value["raw"]`
> untruncated, and let `_format_hits()`'s existing `raw[:2000]` truncation
> (`decision.py:76-78`) handle the *display*-time cap, exactly the same
> pattern already used for `remember()`'s items. That closes the
> 400-byte–4KB gap with a one-line change (store the full string under a
> key `_format_hits()` already reads), without turning every small result
> into an artifact — "becomes an artifact" only happens when
> `action.py`'s own 4KB threshold decides it should, which is unrelated to
> how much of the *sub-4KB* result Memory bothers to retain.

### 3.6 "What gets remembered" — there is no filter, and that's a real design bet

Worth stating plainly because it's easy to assume a relevance gate exists
when it doesn't: every user query (`memory.remember()`, called
unconditionally at the top of every run), every tool result
(`record_outcome()`, called for every tool-kind result, every round), and
every document chunk (`add_fact()`, one call per chunk from
`index_document`) gets written, unconditionally, forever. There is no "is
this worth keeping" judgment anywhere in the write path. The design bet is:
**write indiscriminately, rely entirely on retrieval ranking to surface
what's relevant later.** That's a legitimate strategy — it trades storage
growth for never having to build a "should I remember this" classifier —
but it does mean the store has no natural ceiling, and it's worth
confirming that's the bet you intend, not something that crept in by
default.
[WAIT SO, WE GIVE THE USER QUERY AT THE TOP ALL TOGETHER? AND DODCUEMNT CHUNK IS THEN FED ?, THE MODEL OUTPUT? WHATS RETIRIEVAL RANKING HERE ? THE THING IS IF WE ARE JUST FEEDING THE CHAT, I AM TENDING TOWARDS MANINTAINING THIS FOR NOW, I DONT THINK BUILDING A RANKER OR CHOOSER OR SUMMARISER OF ANY KIND IS THE CORRECT STRATEGY RIGHT NOW ]

> **A:** To untangle the timeline concretely: at the very start of a run,
> `agent7.py:153` calls `memory.remember(query, ...)` once, on the user's
> raw incoming query only (not "the whole chat," just that one string).
> Separately and independently, whenever the (currently broken,
> TODO.md §7) `index_document` tool runs — which could be any run, not
> tied to "the top" of anything — it calls `add_fact()` once per document
> chunk. And separately again, every time a tool call finishes,
> `record_outcome()` writes one `tool_outcome` item. None of these are
> "fed together" — they're three independent triggers writing
> independently over the life of the whole system, all landing in the
> same flat `memory.json` list. "The model output" (Decision's synthesis
> answers) is *not* written to Memory at all today — it only exists
> transiently as `GoalResult.output_descriptor` for the current run (see
> §3.1's `tool_outcome` answer above) — so that's one category that
> *isn't* part of the "write everything forever" bet, whether or not that
> was deliberate. "Retrieval ranking" just means the cosine-similarity
> scoring in `_vector_search()` (§2.1/§2.2) — there's no separate ranking
> stage beyond "whatever FAISS returns as closest, in that order, top 8."
> On your bottom line: I agree with you, and said the same independently
> in my first-pass answer to Open Question 2 — don't build a
> ranker/chooser/summarizer right now. The one thing I'd still flag as
> different from "just feeding the chat" is the fact-volatility gap
> (§1.6/§3.1) — that's not a ranker, it's a much smaller thing (one
> optional field per item), and I'd treat it as worth doing precisely
> because it's small enough not to be the kind of surface-area risk you're
> rightly wary of.

### 3.7 Why locking matters here specifically

`memory.py` wraps every read/write of the FAISS index and every write of
`memory.json` in both a Python `threading.Lock` (in-process — FastAPI can
run multiple request threads)[WHY DO WE HAVE THIS? WHATS THE POINT OF MULIPLE THREADS ?] and an `fcntl` file lock (cross-process).
The cross-process lock is not defensive boilerplate [AGAIN WHATS THE POINT OF THSI?] — it's load-bearing,
because the `mcp_server` subprocess (a genuinely separate OS process,
started by `gateway.py`/`agent7.py`) writes to these *exact same* files
independently, whenever `index_document` or `search_knowledge` runs [WHY ?]. Two
separate Python processes appending to the same JSON file and the same
FAISS binary without coordination would corrupt both [AND WHYS THAT THE CASE ? WHY AR EWE RUNNING 2 FAISS PROCESSES ?]. This is the one
place in the whole storage stack where the "boring, mechanical, always-on"
design principle from the loop-restructure doc shows up on the storage
side too. [THE BORING I UNDERSTAND WHAT I AM STRUGGLING TO UNDERSTAND IS WHAT YOU ACHEIEVE WITH THIS?]

> **A:** Two different boundaries, two different locks, answering all of
> the above together:
> - **`threading.Lock`** protects against multiple threads *inside the
>   same process* racing on the same read-modify-write. Whether this
>   project's `mcp_server` process actually serves concurrent requests
>   over multiple threads today wasn't something I traced in this pass —
>   but the point of having the lock is defensive correctness regardless:
>   if anything in this process ever calls `memory.py` functions from more
>   than one thread at once (a thread pool handling concurrent tool calls,
>   for instance), this lock is what stops two threads from both loading
>   `memory.json`, both appending their own item, and one write silently
>   overwriting the other's.
> - **`fcntl` file lock** protects against a *second, separate OS
>   process* doing the same thing. This is where "why are we running 2
>   FAISS processes" gets its answer: there aren't two FAISS *processes*
>   running concurrently as a steady state — there are two separate
>   Python programs (the main agent, and the `mcp_server` subprocess that
>   `gateway.py`/`agent7.py` starts to host MCP tools) that each,
>   independently, import `agent.cognition.memory` and
>   `agent.services.vector_index` and each open the *same on-disk files*
>   (`memory.json`, `index.faiss`) whenever they need to read or write.
>   `STATE_DIR` is anchored by walking up to `pyproject.toml`
>   (`src/agent/__init__.py`), not by cwd, specifically so both processes
>   resolve to the identical physical files no matter which one launches
>   them (confirmed in `TODO.md` §7). **This is deliberate, and what it
>   achieves is a single shared store despite the tool provider being a
>   separate process** — that separation exists for isolation/dependency
>   reasons (the MCP server has its own venv, its own dependency set), not
>   because two copies of the data are wanted. If `index_document` runs
>   inside the `mcp_server` subprocess, its writes need to actually show
>   up when the main agent process later reads `memory.json` — that's the
>   whole point of the shared file, and the lock is what makes "two
>   processes, one file" safe instead of a race. Without the lock: process
>   A loads `memory.json` (say, 50 items), process B loads it too (same 50
>   items, before A's write lands), A appends its new item and writes 51
>   items to disk, B appends *its* new item to *its own* in-memory copy of
>   the original 50 and writes 51 items to disk — B's write clobbers A's,
>   and A's item is permanently and silently lost, no crash, no error,
>   just gone. That's the concrete thing the lock prevents, and it's why
>   it's load-bearing rather than boilerplate.

### 3.8 The temperature=1.0 question

`memory.remember()`'s classifier call runs at `temperature=1.0`:
```python
return LLM().chat(
    prompt=(...),
    response_format={...},
    temperature=1.0,
)
```
This is a structured-extraction task — "what kind is this, what's the
descriptor, what are the keywords" — the same *shape* of task
`decision.py` runs at `temperature=0` for its own tool-grounding call [I DONT UNDERSTAND THIS I WANT MORE INFORMATION]. High
temperature adds randomness that a classification task doesn't benefit [WHAT ARE WE CLASSIFYING?]
from; it only adds variance in cases where you'd want the *same* input to
reliably produce the *same* structured output. The code already carries a
visible symptom of this:
```python
# NOTES_RUNS §6 (2): the classifier at temp=1.0 sometimes returns an
# empty `value` dict (the C-run-1 birthday case), discarding the only
# structured handle to the raw content. If `value` is empty or missing,
# fall back to {"raw": raw_text} ...
```
I searched this whole repo and the entire surrounding `AI Code` workspace
for the `NOTES_RUNS` document this comment cites — **it does not exist
anywhere.** Whatever reasoning originally justified `temperature=1.0` here
is lost; what's left is a patch for the exact failure mode you'd predict
from unnecessary randomness in a classification call, rather than a fix at
the source. Worth trying `temperature=0` here and checking whether the
empty-`value` workaround becomes unnecessary.

> **A:** Two things to unpack. What's being classified: in `remember()`
> (`memory.py:277-326`), the classifier's whole job is to look at one
> piece of free-form text (e.g. the user's raw query) and answer four
> questions about it — which of the 4 kinds is this, what's a good
> one-line descriptor, what are 3-8 search keywords, and what structured
> fields (dates, names, entities) can be pulled out into `value`. That's
> "classification" in the sense of picking discrete categories/labels and
> extracting fixed fields from input, not open-ended writing. `decision.py`
> runs a comparably-shaped task at `temperature=0`
> (`decision.py:186-194`) — given a goal + context, pick exactly one of a
> fixed set of tools (or answer directly), i.e. also a discrete-choice
> task over structured output, not creative generation. The general
> principle: `temperature` controls how much randomness gets injected
> into next-token sampling. For open-ended writing (a story, a
> conversational reply) you often want some randomness so outputs aren't
> robotically repetitive. For a task where there's a *correct* structured
> answer implied by the input (this text is either a `fact` or a
> `preference`, this date is either "15 May" or it isn't), randomness only
> adds a chance of picking the wrong label or dropping a field it should
> have extracted — there's no "creative benefit" to weigh against that
> risk. `decision.py`'s own call is doing the same *kind* of task
> (structured, discrete, schema-constrained via `response_format`) and
> already runs at 0 — the inconsistency is that `remember()`'s equally
> structured call runs at 1.0 with no comment explaining why, plus a
> workaround for a bug pattern (empty `value` dict) that's exactly what
> you'd expect from unnecessary temperature on a schema-constrained call.
> That's why trying `temperature=0` here is a reasonable, cheap experiment
> (Open Question 4) — worst case it doesn't help and you learn the empty-
> `value` issue has some other cause; best case the workaround becomes
> unnecessary because the root cause is gone.

---

## 4. Where this connects back to the loop

Two threads tie this whole doc back to `docs/LOOP_RESTRUCTURE_PLAN.md`:

- **`needs_artifact_ids` on a `Goal`** is set by `perception.py` (PLAN or
  REVIEW), using either the LLM's own `artifact_indices` [HOW DOES THE LLM KNOW WHICH ARTIFACT TO PULL FROM? FROM MEMORY RUN?] choice or a
  keyword-overlap fallback (`_artifact_ids_for_text`). This is the only
  place artifact bytes ever get pulled back out of the store into an LLM's
  view — `decision.py`'s `_resolve_attached()` is purely mechanical, it just
  fetches whatever ids the goal already lists.

  > **A:** Same mechanism as the §1.1 answer above, restated in this
  > context: the LLM doesn't pull from "a memory run" directly, it's shown
  > a numbered snapshot of the current memory hits
  > (`_snapshot_hits`, `perception.py:104-127`, built from whatever
  > `memory.read()` already returned for this round) with an `i` index
  > next to each artifact-bearing item, and the PLAN/REVIEW prompt asks it
  > to pick which index numbers matter for each goal it's proposing
  > (`artifact_indices`, resolved back to real ids by
  > `_artifact_ids_for_indices`, `perception.py:130-138`). So "how does the
  > LLM know which artifact to pull" — it's shown a short menu (up to 12
  > items) with descriptors and previews, and picks by number; it's not
  > searching or reasoning about the whole artifact store, just choosing
  > from whatever this round's memory retrieval already surfaced.

- **The mcp_server import break** (full detail in `TODO.md` §7) sits
  exactly at the seam between Memory (this doc) and the tools that write to
  it from outside the main process (`index_document`, `search_knowledge`).
  Until that's fixed, the vector-search path described in §3.2 above has
  never actually been exercised end-to-end with real document-indexing
  traffic — everything in this doc is verified by reading the code, not by
  running it live.

[IS THE ENTIRE MCP SERVER BREAK ? OR IS THE VECTOR SEARCH MCP TOOL THATS BREAKING?]

> **A:** Confirmed from `TODO.md` §7: it's the **entire subprocess**, not
> just the knowledge tools. `mcp_server/mcp_server.py` line 23 does
> `sys.path.insert(0, .../"AI Code/agent")` — a directory that no longer
> exists after this repo's restructure (code now lives at
> `AI Agent/src/agent/`). That's a module-level import statement, and a
> failing module-level import crashes the whole subprocess at startup, not
> just the two tools (`index_document`, `search_knowledge`) that happen to
> depend on it — so today, in a live run, **every** MCP tool is
> unavailable (`fetch_url`, `read_file`, `time`, `currency`, all of them),
> not a targeted subset. There's a second, separate, previously-
> undocumented break in `knowledge_graph`'s tools (importing `KGStore`
> from an unrelated sibling project's own venv) that's a dependency
> decision, deliberately not folded into the same fix. Both are unfixed as
> of this doc's writing — see `TODO.md` §7 for the exact fix shape agreed
> but not yet applied.

---

## 5. Open questions for you to weigh in on

[HAVE ADDED EVERYTHING I NEED TO ADD HERE]

Same bracket-comment style as the other two docs, write your answer
inline wherever you want:

1. Reference-counted GC vs. blind per-run wipe for artifacts — §1.6.
   `[YOUR ANSWER]`

   > **A (recommendation):** Reference-counted GC. Blind per-run wipe
   > guarantees a dangling reference on the very next run, given Memory is
   > permanent by design — ref-counted GC never creates one, since
   > anything still referenced by any Memory item survives regardless of
   > which run wrote it. Implementation: walk `memory.json`, collect every
   > non-null `artifact_id`, delete any `art:<hash>` pair on disk whose
   > hash isn't in that set. Run it as a periodic sweep (e.g. on startup),
   > not on every write — no need for it to be hot-path.

2. Is "write everything, filter on read" the memory policy you actually
   want, or should some write-time filtering exist — §3.6.
   `[YOUR ANSWER]`

   > **A (recommendation):** Keep write-everything, no filter/ranker for
   > now — this matches what you said directly in your own comment at
   > §3.6, and I agree with the reasoning: a bad filter risks silently
   > dropping something that mattered, while over-storing just costs
   > retrieval noise, which is a cheaper failure mode to live with at
   > current scale. Revisit only if a live trace shows the store
   > genuinely degrading answer quality, not preemptively.

3. Fix `record_outcome()`'s descriptor-discarding bug (§3.4) by keeping the
   preview even when an artifact exists? This seems like a clear bug, not a
   design choice — confirm before it gets touched.
   `[YOUR ANSWER]`

   > **A (recommendation):** Yes, fix it — confirmed as a bug, not a
   > design choice, by tracing the exact code path in §3.4. Minimal fix:
   > in the `if artifact_id:` branch, append the truncated preview text in
   > addition to the artifact id, e.g.
   > `descriptor += f"{result_text[:120].replace(chr(10), ' ')} [artifact {artifact_id}]"`
   > instead of discarding `result_text` outright. Separately, worth
   > either renaming `value["result_preview"]` to `value["raw"]` (so
   > `_format_hits()`'s existing `raw`/`chunk` check picks it up for free)
   > or adding a `result_preview` check to `_format_hits()` directly — right
   > now that field is written on every single `tool_outcome` item and
   > never displayed anywhere, which is pure waste even after the
   > descriptor fix above.

4. Try `temperature=0` for `memory.remember()`'s classifier — §3.8.
   `[YOUR ANSWER]`

   > **A (recommendation):** Yes, try it — it's a one-line, fully
   > reversible experiment. `remember()`'s classifier is a structured-
   > extraction/classification task, the same shape as `decision.py`'s
   > tool-grounding call which already correctly runs at 0. The empty-
   > `value` workaround already in the code is a textbook symptom of
   > unneeded randomness on a schema-constrained call, and the `NOTES_RUNS`
   > doc the comment cites as justification for 1.0 doesn't exist anywhere
   > in the repo — there's no argument on record for keeping it at 1.0.

5. Priority order — which of the `TODO.md` §7 items do you want tackled
   first, if any, this session?
   `[YOUR ANSWER]`

   > **A (recommendation):** 1) mcp_server import fix first — it's what's
   > blocking live verification of literally everything else discussed in
   > this doc (§4); right now every conclusion here is "confirmed by
   > reading the code," not "confirmed by watching it run." 2) The
   > `record_outcome()` descriptor bug (§3.4/Q3) — small, clear, high
   > value, no design debate needed. 3) `temperature=0` try (§3.8/Q4) —
   > trivial to test. 4) Artifact reference-counted GC (§1.6/Q1) — design
   > is now settled above, just needs building. 5) The fact-volatility/
   > expiry gap (new discussion under §1.6/§3.1/§2.1) as its own follow-up
   > session — it's the most consequential long-term issue in this doc,
   > but it touches write-path, read-path, and retrieval scoring all at
   > once, so it deserves a dedicated design pass rather than being
   > squeezed in alongside the smaller fixes above.

---

## 6. New: the fact-volatility gap (surfaced by discussion, not in the original pass)

This section didn't exist in the first version of this doc — it's a
synthesis of three separate comments you made independently, in §1.6,
§2.1, and §3.1, all pointing at the same underlying hole from different
angles, which is worth naming as one thing rather than three.

**The gap:** `MemoryItem` has no concept of time-bounded truth. A fact
like "user's mom's birthday is 15 May" (true indefinitely) and "the stock
is at $142" or "it's raining right now" (true for seconds to hours) are
written through the identical code path, stored with identical structure,
embedded the same way, and retained with identical (infinite) lifetime.
Nothing in `remember()`, `record_outcome()`, or `add_fact()` asks "how
long should this stay true," and nothing in `_vector_search()` discounts a
hit for being old.

**Why it matters, concretely:** it's the mechanism behind two things you
independently flagged as concerning — §2.1's cross-run bleed (a stale
`tool_outcome` outranking something current, purely on cosine similarity)
and §1.6's "why is memory forever" objection. Both are really the same
root cause: no per-item notion of volatility or expiry.

**What I'd recommend, and what I wouldn't:** not a ranker, not a
relevance classifier, not a new `kind` — per your own instinct in §3.6/Q2,
that's too much surface area for what's actually a small, well-scoped
addition. Instead: one optional field (`expires_at: datetime | None`, or a
simpler `volatile: bool`) that `remember()`'s existing classifier call can
set alongside `kind`/`descriptor`/`keywords` (it's already making one LLM
judgment call per item — this is one more field on the same call, not a
new call), and a cheap read-time check (skip or downweight items past
their `expires_at` in `_vector_search`/`_keyword_search`). This is small
enough to fit alongside the other fixes above rather than needing its own
multi-week design effort, but it's real enough — and touches enough of
the read/write/scoring surface — that I'd still sequence it last (Q5)
after the smaller, more contained fixes land first.
