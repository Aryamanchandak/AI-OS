# Cascade / escalation — what it is, what it does, part by part

Date: 2026-09-06. Grounded in `glc_v5/glc/routing/policy.py` (`assess`,
`should_escalate`, `next_tier`/`prev_tier`, lines 401-499) and the actual
retry loop in `glc_v5/glc/routes/chat.py` (lines 722-980).

## What problem this solves

Given a request that went through tier/role routing (see the other two
docs), the answer might come back bad — empty, truncated, failing a JSON
schema — from whichever provider answered. Cascade is the retry policy for
that case: **try cheap first, and only pay for something more expensive when
the cheap answer actually looks wrong**, rather than either (a) always
starting at the expensive tier "just in case," or (b) accepting a bad cheap
answer with no recourse. This is the FrugalGPT idea — escalate on demand,
not by default.

## Confirmed: it is inert unless a tier was resolved — i.e. unless `auto_route` ran

This was worth verifying precisely rather than assuming, because it matters
to your "paying twice" concern. When a request has no `auto_route` (or an
explicit `provider`), `tier` is never set — it stays `None` all the way
through `chat.py`. Down in the cascade check,
`pol.should_escalate(req.auto_route, tier or "", ...)` is called with an
empty string. Tracing what that does:

- `rank("")` (`policy.py:223`) returns `len(rungs)` because `""` isn't a
  real tier — i.e., one past the end of the ladder.
- `next_tier("")` (`policy.py:416`) computes `r = rank("") = 3` (for a
  3-rung ladder) and checks `r + 1 < len(rungs)` → `4 < 3` → **False** →
  returns `None`.
- `should_escalate` sees `next_tier(...) is None` and returns
  `(False, "<tier> is the top of the ladder")` immediately
  (`policy.py:492-494`), before it even looks at confidence.

So a request that never went through the classifier or a role **cannot**
escalate — not "unlikely to," structurally cannot, because there's no tier
to escalate *from*. The only cost that runs regardless is `pol.assess()`
scoring the answer for telemetry (a confidence number gets logged either
way) — that's a free structural check, no extra LLM call, no extra spend.

## The parts, in the order they run

1. **Confidence scoring — `assess()` (`policy.py:437`).** After a worker
   call returns, this looks at *structural signals only* — never a second
   LLM call to "judge" the first answer, because paying a judge model to
   grade a cheap answer often costs more than just paying for the expensive
   answer up front. Signals checked, each with its own configurable score:
   - empty response → 0.0 (the strongest signal there is)
   - schema validation failed → 0.1
   - truncated (`stop_reason == "max_tokens"`) → 0.55 — deliberately scored
     just *above* the default 0.5 threshold, because truncation almost
     always means the caller under-budgeted `max_tokens`, and a bigger model
     hits the same wall; escalating here pays twice for the same cut-off
     answer.
   - shorter than `min_response_chars` → 0.3, but **disabled by default**
     (`min_response_chars: 0`) — the config file's own comment records why:
     it was set to 8 during testing and immediately escalated "Paris" (a
     correct one-word answer) as if it were bad, making cost-per-resolved-
     task worse for no quality gain. Only turn this on for a task class
     whose correct answers are known to be long.
   - a hedge/refusal phrase from `hedge_markers` → default confidence minus
     a penalty — empty by default for the same reason (a wrong marker
     escalates good answers).
   - The final score is the **lowest** of whichever signals fired — one bad
     signal is enough, it doesn't average out against good ones.
2. **`should_escalate()` (`policy.py:478`) — the actual gate.** Escalates
   only if *all* of: escalation is enabled globally, the current role
   permits it (`escalate: true` in its `routing.yaml` spec), the
   per-request escalation count hasn't hit `max_escalations` (default 1),
   there **is** a next rung to escalate to, and either a configured trigger
   fired (`empty_response`, `provider_failure`, `low_confidence`,
   `schema_failure`) or the score is below `confidence_threshold` (default
   0.5) and `low_confidence` is in the trigger list.
3. **The retry itself, in `chat.py`'s outer `while True` loop
   (line 727).** On escalation: `tier` moves to `next_tier(tier)`,
   `escalations` increments, a fresh candidate list is built for the new
   tier via `_tier_candidates()`, and the loop re-enters — this is a real
   second attempt against a real second (more expensive) provider, billed
   like any other call. The loop is bounded by `max_escalations`, so it
   cannot spin indefinitely.
4. **A schema-validation failure gets one extra chance before this even
   triggers**: the gateway already retries once in-place with a
   "your JSON didn't match the schema, fix it" follow-up message
   (`chat.py:884-899`) *before* considering escalation — cascade only comes
   into play if that in-place fix also fails (`chat.py:900-911`).

## The real cost tradeoffs — your concerns, specifically

- **"Paying twice with a cloud model."** Confirmed accurate: an escalation
  is a full second billed call to a second (pricier) provider. There's no
  discount or partial-credit mechanism — the cheap call's cost is sunk, and
  the expensive call is paid in full on top of it. This is inherent to the
  approach, not a bug to fix; the only lever that limits it is
  `confidence_threshold` (how often it fires) and `max_escalations` (how far
  it can go per request).
- **Free/hosted models for the escalation target — security question.**
  Same shape as the classifier's version of this question (see
  `CLASSIFIER_AND_ROUTER.md`): whichever provider a role's next rung
  actually names in `routing.yaml` is who receives the prompt on escalation.
  If that's a free-tier vendor, the same "is this specific prompt OK to
  send to that vendor" question applies here too.
- **No local capacity right now.** Noted — a local model can't be an
  escalation target today if there isn't RAM to run one; that's an
  infrastructure constraint on top of the config, not something the
  cascade logic itself needs to know about (it just tries whatever's in the
  next tier's candidate ring — if nothing's reachable there, the escalation
  attempt fails and falls back exactly like any other empty candidate
  ring would).

None of the three sides of this bind have a resolution in the code today —
correctly, per your instruction, this doc is for you to think about them,
not a proposal to fix them.

## Open questions / things worth your comment

- Is a single escalation (`max_escalations: 1`) enough headroom for what you
  need, or would some roles want more (at correspondingly more cost risk)?
- Should some roles be allowed to escalate on `low_confidence` but not on
  `truncated_response` (or vice versa) — right now `triggers` is one shared
  list for every role, not per-role.
- Given the pay-twice reality, is there a role shape where escalation should
  just be off (`escalate: false`) permanently, and the "quality" need is
  instead met entirely by the role's `min_tier` floor (no retry, no
  double-spend, just start high) — this already works today with zero
  extra code, e.g. `adjudicator`'s current config.
