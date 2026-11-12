# routing.yaml — what it is, what it does, part by part

Date: 2026-09-06. Written so you can comment inline like you did on
MIGRATION_SCOPE.md. Everything below is grounded in the actual file
(`glc_v5/glc/routing/routing.yaml`) and the code that reads it
(`glc_v5/glc/routing/policy.py`, `glc_v5/glc/routes/chat.py`), not a
paraphrase — file:line pointers throughout so you can jump straight to the
source.

## What problem this file solves

Every `/v1/chat` call has to answer one question: **which provider and model
actually answers this?** Before this file existed (glc_v3), that answer was
a hardcoded Python dict (`TIER_TO_ORDER`) with three fixed failover rings.
`routing.yaml` replaces that dict with data, so changing a provider order,
adding a role, or adding a new tier is a YAML edit, not a code change and
redeploy. Nothing in the Python code knows the name of a role or tier — it's
all read from this file at request time.

If this file is missing or fails to parse, the gateway does **not** go down —
it falls back to the old hardcoded `TIER_TO_ORDER` dict and prints a warning
(`glc/routes/chat.py:85-95`). That fallback only knows two tiers (TINY,
LARGE), not the newer capability ladder below.

## Part 1 — Tiers (TINY / LARGE / HUGE): size-based routing

```yaml
tiers:
  TINY:  { order: [...7 providers...] }
  LARGE: { order: [...7 providers, different order...] }
  HUGE:  { order: [...5 providers...], min_ctx: 8000 }
```

These three answer "how big is this prompt" — nothing about quality. Each
tier is just a fallback order: try the first provider, if it's rate-limited
or down, try the next. `HUGE`'s `min_ctx: 8000` additionally filters out any
provider whose context window can't actually hold the prompt (this is what
makes HUGE prompts servable at all — previously they got a flat 503).

**Who decides which tier a request lands in:** either the classifier (see
the separate `CLASSIFIER_AND_ROUTER.md` doc), or a role's `default_tier`
(Part 4), or nothing at all if the caller passes an explicit `provider` —
in which case tiers never come into it and this whole file is bypassed
(`_tier_candidates` is only called when a tier was resolved at all).

## Part 2 — The capability ladder (CHEAP / STANDARD / FRONTIER): quality-based routing

```yaml
ladders:
  capability: [CHEAP, STANDARD, FRONTIER]

CHEAP:    { order: [ollama, openrouter], strict: true, objective: order }
STANDARD: { order: [groq, gemini],       strict: true, objective: order }
FRONTIER: { order: [github, cerebras],   strict: true, objective: order }
```

This is the direct answer to "when a complex model is needed, use a complex
model" — each rung names a **specific, different model** (not just a
provider), measured and priced (see the comments in the file for the actual
$/Mtok and latency numbers recorded 2026-07-30). `strict: true` is what
makes a rung mean something: without it, any other configured provider gets
appended as a last-resort tail, and a CHEAP request could silently end up
answered by the frontier model. With `strict`, if none of the rung's own
providers are reachable, the request is refused rather than upgraded for
free.

## Part 3 — Two ladders, one tier vocabulary

`ladder: [TINY, LARGE, HUGE]` is the classifier's ladder (unchanged from
v3). `ladders: { capability: [CHEAP, STANDARD, FRONTIER] }` is a second,
independent one. A tier belongs to exactly one ladder. `next_tier`/
`prev_tier`/`rank` (used by escalation, see the cascade doc) always resolve
*within* whichever ladder the current tier belongs to — so escalating a
`worker` role walks CHEAP → STANDARD → FRONTIER, while escalating a
`perception` role walks TINY → LARGE → HUGE, and the two never cross.

## Part 4 — Roles: the thing that actually answers your "cheap vs complex" question

```yaml
roles:
  perception: { default_tier: TINY,     max_tier: LARGE, escalate: true }
  decision:   { default_tier: LARGE,    min_tier: LARGE, escalate: true }
  bulk:       { default_tier: CHEAP,    max_tier: CHEAP, escalate: false }
  worker:     { default_tier: STANDARD,                  escalate: true }
  adjudicator:{ default_tier: FRONTIER, min_tier: FRONTIER, escalate: false }
```

A role is a label the caller declares (`auto_route: "decision"`, etc.).
`min_tier`/`max_tier` are a floor/ceiling that **override** whatever the
classifier guessed — this is the actual mechanism, and it's already built:
a `decision` call is floored at LARGE even if the classifier (wrongly)
called it TINY; a `bulk` call is capped at CHEAP even if the classifier
called it HUGE. `escalate: false` additionally means that role may never
cascade to a bigger model no matter what — `adjudicator` is pinned at
FRONTIER permanently, exactly the "when a complex model is needed, always
use one" case you described. Role names are free-form — adding one is a
YAML edit (`routing.yaml:152-206`), no Python change.

**This is the part I'd expect you to spend the most time tuning** — the
default roles are examples ported from the original design, not necessarily
the roles your actual projects need.

## Part 5 — Cost/quality selection

```yaml
selection:
  objective: cost_quality   # or: order | cost | quality
  tradeoff: 0.5             # 0 = pure cost, 1 = pure quality
  output_weight: 0.35
  pin_first: []
```

After a tier's candidate ring is built, this optionally **re-sorts** it.
`order` keeps the YAML's declared sequence untouched (this is what a
`strict` capability rung effectively forces, regardless of this setting —
see `order_for()`, `glc/routing/policy.py:372`). `cost`/`quality`/
`cost_quality` re-rank by numbers pulled from `pricing.yaml`. `pin_first` is
an escape hatch: names listed here are always tried first regardless of the
sort — meant for "always try my free local model before anything else."

## Part 6 — Benched providers & cooldowns

```yaml
unavailable: {}
backoff: { timeout: 600, queue: 15, rate_limited: 30, rpm: 60, rpd: 3600,
           upstream_5xx: 20, auth: 600 }
```

`unavailable` is a manual kill switch per provider name — add a line, that
provider drops out of every tier including the non-strict last-resort tail,
with the reason surfaced in the rejection list instead of a silent skip.
`backoff` is how long a provider stays benched after each *kind* of failure
(a `timeout` failure benches for 600s, a `rate_limited` one for only 30s).
The file's own comment documents a real incident this caught: an NVIDIA
model that accepted connections but never answered was burning the full
180s client timeout on every call and getting benched for effectively zero
time, because the old failure-matching logic didn't recognize a timeout's
error string. Worth reading if you want a feel for what these numbers are
actually protecting against.

## Part 7 — Budget interaction (⚠ declared but not wired up yet)

```yaml
budget:
  prefer_affordable: true
  block_escalation_on_breach: true
```

I checked: `RoutingPolicy` parses this block and stores it
(`glc/routing/policy.py:207`), and it's echoed back in the policy's
`describe()` output — but **nothing in the codebase currently reads
`prefer_affordable` or `block_escalation_on_breach` to change any routing or
escalation decision.** Grepping the whole `glc/` tree for either key finds
only the YAML and the one line that stores it. So today this section is
aspirational — it documents an intent that hasn't been implemented. Worth
knowing before you tune it, since tuning a number nothing reads is wasted
effort; this is really a "build this" item, not a "tune this" item.

## Gemini — explicit, so it doesn't get lost again

Per your instruction: **Gemini stays exactly where it is in this file.**
It's listed in `TINY.order`, `LARGE.order`, `HUGE.order`, and
`STANDARD.order`. None of that gets edited or removed. The earlier decision
to "end Gemini support" is implemented entirely outside this file — by not
setting `GEMINI_API_KEY` in the environment, Gemini simply never appears as
a live candidate anywhere these lists are expanded (see
`IMPLEMENTATION_PLAN.md`, "API keys: easy-ignorable by design," and
`order_for()`'s candidate expansion at `glc/routing/policy.py:335-343`,
which only ever includes names present in the live provider registry). If
you ever add the key back, every one of these rings picks Gemini back up
immediately with zero file changes.

## Open questions / things worth your comment

- Is the default role set (`perception`, `memory`, `decision`, `triage`,
  `bulk`, `worker`, `adjudicator`) the right shape for what you're actually
  building, or a placeholder to replace?
- The CHEAP/STANDARD/FRONTIER model picks (and their prices/latencies) were
  measured 2026-07-30 — worth re-measuring before relying on them, prices
  and model availability both drift.
- `selection.tradeoff: 0.5` and `output_weight: 0.35` are global defaults
  applied to every non-strict tier — do you want per-role overrides instead
  of one global dial?
- The budget-interaction block (Part 7) needs actual implementation before
  it does anything — worth deciding if/when that's built.
