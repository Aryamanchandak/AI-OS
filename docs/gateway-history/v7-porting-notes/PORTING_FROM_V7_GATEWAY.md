 # Porting selected changes from `llm_gateway old`

[HAVE ADDED MY COMMENTS IN CAPS AND BRACKETS]

## Why this isn't a straight diff-and-apply

[SO THE ONLY IDEA IS THAT WE NEED TO PORT OVER FUNCTIONALITY, THAT HAS BEEN BUILT UPON BY MY CODE, MAKING SURE THAT IT IS STILL RUNNING THE WAY IT SHOUD, THE NEW GATEWAYS ARE BEING ADDED TOO MAKE USE OF THE GOOD WORK ALREADY DOEN ADN EXPAND MY SCOPES.]

[I HAVE NO ISSUE WITH AUTOMATIC ROUTING, ITS JUST THAT I DONT NEED THAT MUCH OF IT, I DONT WANT YOU TO DELETE THE CODE JUST YET INSTEAD I WANT YOU TO MAYBE REFACVTOR CODE IN A WAY THAT BUILDS ON TOP OOF THE EXISTING GATEWAY.

I NEED ROUTING TO BE INTRODUCED FOR EMBEDDINGS AND CHAT, AND THE MODELS FRO ANTHROPIC, OPENAI AND GEMINI SINCE THATS WHAT I USE, NOW THE CURRENT CODE DOES ROUTING BASED ON WHAT WAS NEEDED TO DO WHAT NEEDED TO BE DONE TO THE QUALITY THAT IT NEEDED, RIGHT NOW THE MODELS WILL CALL AND TRIGGER USE OF SPECIFIC MODELS BY NAME SO THATS NEEDS TO BE LOOKED INTO, I DONT WANT TO USE GROQ OR CEREBRAS, BUT ITS FINE TO ME IF THE CODE IS THERE AS LONG AS IT DOEST BREAK ANYTHING AND IMPORTANTLY DOES REDUCE THE QUALITY AS I WONT GIVE IT AN API KEY, SO THERE IS NO WAY IT WILL WORK. OTHER THAN THAT WE WILL USE NOMIC EMBED TEXT, AND THE BACK UP OF GEMINI EMBEDDING MODEL NEEDS TO BE REMOVED OR BASICLALHY UN USABLE]

[ONE MORE THING IS THAT I WANT TO DOCUMENT EVERY CHANGE, TO RECREATE THE CHANGE SON THE NEXT VERSION OF THE GATEWAYM INSTEAD OF REDOING THE CHANGES.]

`llm_gateway old` (V7) and this repo (`glc_v3`) share a common ancestor but
solved different problems after that. V7's cleanup pass *removed* the V3
classifier/router/channel machinery to become a plain chat+embed proxy over
paid-tier providers (Gemini, OpenAI, Anthropic). This repo went the other
way: it kept and built on the V3 architecture — `auto_route`,
`RouterDecision`, a separate router-provider pool — and grew it into
"Gateway for LLMs and Channels used by EAG V3" (see `README.md:3`), with
channels, voice, policy, security and audit layers V7 never had. It also
targets a completely different provider set: free/cheap-tier (Groq,
Cerebras, Nvidia, OpenRouter, GitHub Models) plus Gemini and Ollama —
`glc/providers.py:271-943` has no OpenAI or Anthropic provider class at all.

So most of V7's "V3 removal" changes would *break* this gateway, not clean
it up. What follows was decided by diffing the actual files, not by reading
the summary at face value — `glc/embedders.py` and `glc/db.py` turned out to
already share code history with V7's versions almost verbatim.

Verdict key: **PORT** (do it, low risk) · **ADAPT** (port the mechanism,
not the specifics) · **SKIP** (would regress or doesn't apply here).

| # | V7 change | Verdict |
|---|---|---|
| 1 | V3 removal (classifier, `auto_route`, router pool, dashboard, web UI) | **SKIP** |
| 2 | Provider reorg into Gemini/OpenAI/Anthropic families | **SKIP** |
| 3 | Named chat profiles | **ADAPT** |
| 4 | Stable embedding profiles | **PORT** |
| 5 | Client preflight/status helpers | **SKIP** |
| 6 | Structured output improvements | already present / partly **SKIP** |
| 7 | Tools narrowed to protocol translation | already true, no action |
| 8 | Logging/rate-state fields | **PORT** (one column) |

---

## 1. V3 removal — SKIP

`auto_route`, `RouterDecision`, and the router-provider pool are load-bearing
here, not legacy cruft:

- `glc/routes/chat.py:376-391` gates worker-tier selection on `auto_route`
  via `TIER_TO_ORDER`.
- `glc/routing.py:210-247` (`RouterPool`) is the dedicated failover ring for
  those classifier calls, separate from worker quotas by design.
- `glc/main.py:78-84` still serves the dashboard and help page, and
  `tests/test_dashboard.py` + `tests/test_v9_compat.py` assert this shape
  directly.

Removing any of this would fail existing tests and cut functionality
channels/agents depend on. Not a port candidate.

## 2. Provider family reorg — SKIP

V7's target list (`gemini-cheap/flash/pro`, `openai-cheap/mini/pro`,
`anthropic-haiku/sonnet/opus`) assumes providers this gateway doesn't have.
`glc/providers.py` only implements `OpenAICompatProvider` subclasses for
Groq/Cerebras/Nvidia/OpenRouter/GitHub, plus `GeminiProvider` and
`OllamaProvider` — all chosen for free/cheap tiers, not the paid frontier
models V7 standardized on. Porting this would mean adding Anthropic/OpenAI
provider classes from scratch, which is a scope decision, not a port. Flagged
as an open question at the end of this doc rather than assumed.

## 3. Named chat profiles — ADAPT

The *mechanism* is good and cheap to add; the *specific profiles*
(`knowledge-extraction-v1` → `anthropic-sonnet`, `document-segmentation-v1`
→ `phi4-local`) don't map onto providers that exist here and shouldn't be
copied verbatim.

What to port, concretely:

- Add `profile: str | None = None` to `ChatRequest` in
  `glc/llm_schemas.py:41-71`, next to the existing `agent`/`session` fields.
- Add a `CHAT_PROFILES: dict[str, str]` table and a `_resolved_chat_profile()`
  helper to `glc/routes/chat.py`, modeled on `llm_gateway old/main.py:32-38`
  and `:128-146`.
- Resolve the profile in `chat()` in the **same slot** the existing
  agent-pin logic already uses — `glc/routes/chat.py:368-372` currently does:
  ```python
  if req.agent and not req.provider:
      pinned = AGENT_ROUTING.get(req.agent)
      if pinned and pinned in rtr.providers:
          req.provider = pinned
          explicit_override = True
  ```
  A profile resolver goes right alongside this, before the `auto_route`
  check at line 376 (`if req.auto_route and not req.provider:`) — setting
  `req.provider` there automatically suppresses `auto_route`, which is the
  behavior you want, for free.
- **Availability check must use `rtr.candidates(name)`, not `name in
  rtr.providers`.** V7's flat membership test (`main.py:135`) doesn't work
  here: a logical name like `"gemini"` isn't a key in `router.providers` —
  it expands to `gemini_1`, `gemini_2`, ... via `Router.expand()`
  (`glc/routing.py:150-171`). A profile pinned to a logical name would
  falsely report itself unavailable under the old check.
- Port the mutual-exclusion guard (profile vs. explicit `provider`/`model`)
  from `llm_gateway old/main.py:152-157`.
- Extend `/v1/providers` (`glc/routes/chat.py:775-784`) with a
  `chat_profiles` block and add `GET /v1/chat/profiles/{profile}`, mirroring
  `llm_gateway old/main.py:503-527`.

What NOT to copy: the two specific profile names/targets. Pick profile
names and pins that make sense for this gateway's own providers — e.g. a
profile pinned to `"ollama"` with no fallback, for the same reason V7 pinned
`document-segmentation-v1` to local-only: guaranteed reproducibility, fail
loud instead of silently using a hosted model. Left as an open question
below rather than guessed.

## 4. Stable embedding profiles — PORT (flagship change)

This is the highest-value, lowest-risk port. `glc/embedders.py` is already
byte-for-byte identical to `llm_gateway old/embedders.py` except for one
missing block — confirmed by direct diff, not inference:

```
34,47d33
< PROFILES: dict[str, dict] = {
<     "chunker-v1": {"provider": "ollama", "model": "nomic-embed-text", "dim": EMBED_DIM},
< }
```

Everything the profile check depends on (`EMBED_DIM=768`,
`MAX_INPUT_CHARS=8000`, per-provider dimension in the returned dict) is
already there. Steps:

1. Add the `PROFILES` dict to `glc/embedders.py` (same shape as V7's,
   `chunker-v1` → `ollama`/`nomic-embed-text`/768 works unmodified since this
   gateway's Ollama embedder is configured identically).
2. Add `profile: str | None = None` to `EmbedRequest` and `EmbedResponse` in
   `glc/llm_schemas.py` (no `profile` field exists there today — confirmed).
3. Port the enforcement block into `glc/routes/chat.py`'s `embed()` handler
   at **`glc/routes/chat.py:679-739`** — not into `embedders.py`, which
   never sees the request and can't perform the pin/mismatch check. Mirror
   `llm_gateway old/main.py:386-464`:
   - resolve `req.profile` → pinned `(provider, model, dim)`, 400 on unknown
     profile, 400 if caller also passed a conflicting `provider`
   - after `embed_with_failover` returns, compare `result["model"]`/`["dim"]`
     against the pin; on mismatch, log an error row and raise `500` — fail
     loud rather than silently writing incompatible vectors into an
     existing index
4. Add `"profiles": E.PROFILES` to the `/v1/embedders` response at
   `glc/routes/chat.py:742-755` (mirror `llm_gateway old/main.py:489-500`).
5. Pass `profile=req.profile` through to `db.log_call(...)` in both the
   success and error paths of the embed handler (needs the db column below).

## 5. Client preflight/status — SKIP

No `client.py` exists anywhere in this repo, and `README.md:3` states the
design intent explicitly: *"Agent runtimes call it over HTTP; they do not
import its provider code or read its keys."* Bundling a Python client here
would contradict that boundary.

If a "preflight" check is still wanted, this repo already has the right
shape for it: `GET /v1/status` (`glc/routes/chat.py:806-814`) exists and
returns live rate-state per provider. If you want V7's stronger
guarantee — a *real* structured chat call and a *real* pinned-embedding
call, not just rate-state bookkeeping — that's a small addition to
`/v1/status` (or a new `/v1/preflight` route) rather than a client library.
Not implemented here; flagged as optional follow-up.

## 6. Structured output improvements — mostly already present

The one-repair-attempt-on-validation-failure flow V7 added
(`CHANGES_2026-07-29_anthropic_structured_output.md`) is **already
implemented** here, independently, at `glc/routes/chat.py:513-537` — same
shape: validate, on failure re-prompt once with the validation error, fail
with `503` if the repair also fails. No action needed.

The Anthropic-native `output_config.format` part does not apply — there is
no Anthropic provider in this codebase (see #2).

## 7. Tools narrowed to protocol translation — already true

Grepped for tool execution/registration/dispatch across `glc/` — nothing
found. This gateway only translates canonical `ToolDef`/`ToolCall` shapes
per-provider already (`glc/llm_schemas.py:8-25`); it doesn't run tools
itself. Nothing to port.

## 8. Logging fields — PORT one column

`glc/db.py` is already a superset of V7's schema in most respects — it has
`router_decision`, `agent`, `session`, `retries`, which V7 doesn't. The one
thing missing is the `profile` column V7 added
(`llm_gateway old/db.py` schema vs. `glc/db.py:38-72`), which only matters
if #3 or #4 above get implemented.

Also worth carrying over regardless: **V7's migration path.**
`llm_gateway old/db.py:47-52` does:
```python
cols = {r["name"] for r in c.execute("PRAGMA table_info(calls)").fetchall()}
if "embed_dim" not in cols:
    c.execute("ALTER TABLE calls ADD COLUMN embed_dim INTEGER")
```
`glc/db.py:38-72`'s `init()` only does `CREATE TABLE IF NOT EXISTS` — there
is currently no upgrade path for an existing `~/.glc/gateway.sqlite` if the
schema changes. Add the `PRAGMA table_info` → `ALTER TABLE ADD COLUMN`
pattern alongside the new `profile` column so existing installs don't need
their db deleted.

---

## Suggested order

1. **#4 embedding profiles** — self-contained, ~1 file + 1 route, files
   already 95% aligned. Do this first.
2. **#8 db migration + `profile` column** — needed by #4 and #3, five-minute
   change, unblocks both.
3. **#3 chat profiles (mechanism only)** — same shape as the existing
   agent-pin code, low risk, but needs you to pick real profile names/pins
   first (see below).
4. #1, #2, #5, #6 (Anthropic part) — leave as-is.

## Open questions before implementing #3

- What chat profiles do you actually want, and what should they pin to
  given this gateway's real provider set (ollama / gemini / groq / cerebras
  / nvidia / openrouter / github)? V7's two examples don't transfer.
- Do you want a local-only, no-fallback profile analogous to
  `document-segmentation-v1` (fail loud if Ollama is down, never silently
  fall back to a hosted model)? If so, which local model/task is it for?
- Is adding Anthropic/OpenAI provider classes (making #2 relevant) actually
  wanted, or is the free/cheap-tier provider set intentional for this
  gateway? Nothing above assumes an answer either way.
