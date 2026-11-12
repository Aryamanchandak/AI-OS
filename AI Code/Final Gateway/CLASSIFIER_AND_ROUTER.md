# The classifier/router — what it is, what it does, part by part

Date: 2026-09-06. Grounded in `glc_v5/glc/routes/chat.py` (`_classify_tier`,
lines 151-249) and `glc_v5/glc/routing/core.py` (`RouterPool`, lines
204-224).

## What problem this solves

`routing.yaml`'s tiers (TINY/LARGE/HUGE) need something to actually put a
prompt into one of those buckets. The classifier is that something: **a
separate, small LLM call whose only job is to read your prompt and answer
with exactly one word — TINY, LARGE, or HUGE.** That word then feeds into
`routing.yaml`'s role floors/ceilings (see `ROUTING_YAML.md` Part 4) to pick
the actual tier.

It is entirely **opt-in per request.** It only runs when the caller sets
`auto_route: "<role>"` on the request *and* does not also pass an explicit
`provider` (`glc/routes/chat.py:658`: `if req.auto_route and not
req.provider`). If you never set `auto_route`, this code never executes —
not "runs with no effect," literally never called.

## How it actually works, step by step

1. **Cheap pre-filter, no LLM call at all.** `_estimate_tokens()`
   (`chat.py:117`) sizes the prompt with `max(word_count * 1.4, char_count /
   4)` — the `/4` floor exists so dense content with no whitespace (base64,
   CJK text) doesn't score as artificially tiny. If that estimate is already
   over 8000, the answer is HUGE and **no LLM is called at all** — it's
   short-circuited (`chat.py:153-162`).
2. **Build a bounded sample.** `_build_sample()` (`chat.py:129`) takes the
   first 400 and last 400 characters of the prompt, with `...` in between,
   so the classifier call itself stays cheap and fast regardless of how
   long your actual prompt is.
3. **One real LLM call**, with a fixed system prompt (`ROUTER_PROMPT`,
   `chat.py:100`): "given a token_count and a content sample, output exactly
   one of TINY, LARGE, HUGE," `max_tokens=8`, `temperature=0`,
   `reasoning="off"`. This is a real API call to a real provider — it costs
   money and takes latency, same as any other call.
4. **Which provider answers the classifier call** comes from a *separate*
   pool from your actual worker providers: `RouterPool`
   (`glc/routing/core.py:213`), built from `DEFAULT_ROUTER_ORDER = [cerebras,
   groq, nvidia, github]` (`core.py:210`). Same API keys as your worker
   providers, separate rate-limit bookkeeping, so classifier traffic can't
   starve worker traffic's quota or vice versa. **This directly answers your
   security question**: today the classifier does not call some separate
   "free hosted LLM" — it calls whichever of your already-configured,
   already-keyed providers (Cerebras/Groq/NVIDIA/GitHub) has capacity. If
   you trust those providers with your worker traffic, the classifier isn't
   introducing a new vendor into the trust boundary — it's sending an
   800-character sample of the same prompt to one of the same vendors. The
   open question is narrower than "is a free LLM safe" — it's "is a 400-head
   +400-tail sample of this specific prompt OK to send to Cerebras/Groq/
   NVIDIA/GitHub," which may differ prompt-by-prompt if some prompts carry
   sensitive content and others don't.
5. **Parse the answer.** `_parse_tier()` (`chat.py:143`) just checks which
   of the three words appears in the reply. If the model answered HUGE but
   your own estimate said ≤8000 tokens, HUGE gets downgraded to LARGE
   (`chat.py:195-196`) — the classifier is trusted to escalate but not to
   invent a HUGE that the token math disagrees with.
6. **Fallback on failure.** If a provider in the pool is rate-limited, the
   loop tries the next one (`chat.py:168-193`). If every provider fails or
   is unavailable, it falls back to a **pure token-count heuristic**
   (`_tier_from_count()`, `chat.py:135`: >8000→HUGE, ≥1000→LARGE, else TINY)
   with no LLM call at all, and marks `fallback_used=True` on the response
   so you can tell classifier-driven and heuristic-driven decisions apart in
   the logs.
7. **Every attempt is logged** to the call-log DB with `call_role="router_
   <role>"` and `router_decision` set to the parsed tier or `"error"`/
   `"unparseable"` — separate from worker call logs, so router activity and
   worker activity can be reported on independently (this is what
   `/v1/routers`, below, reads).

## `/v1/routers` — status endpoint

Read-only, reports the router pool's live rate/cooldown state and the
current `tier_to_order` view (`chat.py:1280`). Exists for observability, not
for changing behavior.

## Why llm_gateway removed this (for context, not as a recommendation)

Documented rationale (`llm_gateway/CLEANUP_SUMMARY.md`): the gateway should
be small and "dumb" — no intelligence about *what to call* lives inside the
gateway, that decision belongs to the caller. Per your last message, we're
explicitly not following that reasoning here — different project, different
tradeoffs, you want a real mechanism for "this call is important, use a good
model," and role floors/ceilings (Part 4 of the routing doc) already give
you a deterministic version of that even without the classifier running at
all. The classifier only adds value on top of roles when you *don't* know
in advance which tier a given call needs and want an LLM to guess instead of
you declaring it.

## Cost of running this, concretely

Every auto-routed call becomes **two LLM calls**, not one: the classifier
call (tiny, `max_tokens=8`, cheap model) plus the actual worker call. This is
the "not wasting bandwidth on this" tradeoff you flagged — it's real, and
it's avoidable per-call by passing `auto_route` only on requests where you
actually don't already know the right tier, and skipping it (using an
explicit `provider`, or a role's `default_tier` with no classifier — not
currently a supported combination, see open questions) elsewhere.

## Open questions / things worth your comment

- Do you want a mode where a role's `default_tier` is used **without**
  running the classifier at all — i.e. "always route `bulk` to CHEAP,
  never spend a call finding out"? Today, setting `auto_route` always
  triggers the classifier call first; the role's floor/ceiling only clamps
  the result afterward. Skipping the classifier and going straight to
  `default_tier` would need a small code change (not present today).
- `DEFAULT_ROUTER_ORDER` currently reuses your worker-provider keys with
  smaller/faster models. Is that the trust boundary you want, or do you want
  the classifier restricted to an explicit allowlist independent of whatever
  the worker order happens to be?
- Given the "two calls per auto-routed request" cost — which roles, if any,
  actually need the classifier, versus just being pinned to a fixed
  `default_tier`/`min_tier`/`max_tier` with `escalate: false` and no
  classifier involvement at all?
