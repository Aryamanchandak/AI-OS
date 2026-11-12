# Implementation plan: porting llm_gateway into glc_v5

Date: 2026-09-06
Status: plan agreed, no code changed yet. Execute phase by phase; each phase
ends with a concrete verification step before moving to the next.

Baseline decisions already locked in (see MIGRATION_SCOPE.md for the full
reasoning):

- glc_v5 is the base. Nothing gets deleted. Unused subsystems (policy,
channels, audit, economics, voice, the classifier/router, cascade/escalate)
stay in the code, dormant, and get activated individually later as real
projects need them.
- Direct Anthropic + OpenAI adapters, not proxy-only. 
- Every local model llm_gateway supports (gemma, phi4-local,
cover-vision-local) gets registered in glc_v5, not just the single `ollama`
entry.
- Gemini: code and routing.yaml/DEFAULT_ORDER entries stay exactly as they
are. We simply never set `GEMINI_API_KEY`/`GEMINI_API_KEY_1..N` in the new
deployment's environment. Resolved — see "API keys: easy-ignorable by
design" below for why this fully deactivates it with zero code changes.
- routing.yaml, the classifier/router, and cascade/escalate all need
individual fine-tuning sessions — explicitly out of scope for this pass.
- client.py's *behavior* moves into glc_v5; its old file path does not need
to be preserved — dependent projects get adapted later.

---



## Phase 0 — repo hygiene

`Final Gateway` is not currently a git repo. Before any cross-file surgery,
`git init` + first commit of the current state, so every phase below is a
reviewable diff and any phase can be rolled back independently.

**Verification:** `git log` shows one commit; `git status` clean. [COMMIT THE GATEWAY LOCALLY FOR NOW, ONCE WE MAKE SOME CHANGES TO IT WE THEN COMMIT IT TO FOLDER THAT I WILL TELL YOU ABOUT]

## Phase 1 — local model config + Ollama correctness fixes

- Add `glc/local_models.yaml`: one entry per local model (existing default
`ollama`, plus `gemma`, `phi4-local`, `cover-vision-local`), each carrying
`needs_think_false`, `vision`, `context_window`.
- `OllamaProvider.chat()` reads `think` from this config instead of nothing.
- Fix `stop_reason`: map Ollama's `done_reason in {"length","max_tokens"}` to
`"max_tokens"` (currently always reports `"end_turn"`/`"tool_use"`).
- Register the three new local models in the provider build step
(`build_providers()`), each pointing at the same Ollama daemon.

**Verification:** a request to each of the four local models returns
`stop_reason: "max_tokens"` when truncated (test with a tiny `max_tokens`),
and `/v1/providers` lists all four.

## Phase 2 — profiles (embedding + chat), config-driven, dual-mode

- Add `glc/profiles.yaml` (embedding profiles + chat profiles in one file,
same load pattern as `routing.yaml`/`agent_routing.yaml`).
- Add `profile` field to `EmbedRequest`/`EmbedResponse` and
`ChatRequest`/`ChatResponse` (`glc/llm_schemas.py`).
- Port the pin/verify logic: resolving a profile checks the live
provider+model+dim actually match the pin, hard-fails (503) if not.
- `profile` and `provider`/`model` stay mutually exclusive on the request —
this is what gives you "dynamic by default, specific when you want it."
- Add `GET /v1/chat/profiles/{profile}` (parity with llm_gateway's resolver).

**Verification:** `/v1/embed {"profile":"chunker-v1"}` returns the pinned
model/dim; feeding it a deliberately wrong dim (simulate) returns a clear 500,
not a silent wrong-shape vector. Same shape test for one chat profile.

## Phase 3 — direct Anthropic + OpenAI adapters

- `AnthropicProvider` / `OpenAIProvider` classes in `glc/providers.py`,
matching the existing provider interface.
- Port `_anthropic_clean_schema` for Anthropic structured output.
- Wire both into the provider registry using the exact same
`if k := os.getenv("ANTHROPIC_API_KEY"): out["anthropic"] = ...` pattern
every other provider already uses in `build_providers()` — see below.
- Real per-vendor rate limits (`LIMITS`) for both.

**Verification:** with keys set, one live minimal call to `provider=anthropic`
and one to `provider=openai` via `/v1/chat`, confirm 200 with `text`,
`stop_reason`, usage populated. With a key *unset*, confirm the provider is
simply absent from `/v1/providers` and nothing else breaks (startup, other
providers, routing.yaml's `order` lists that still name it).

### API keys: easy-ignorable by design

Checked `build_providers()` (`glc/providers.py:1245`): every provider except
Ollama is already registered conditionally —
`if k := os.getenv("X_API_KEY"): out["x"] = XProvider(k, ...)`. No key means
the provider is just absent from the registry dict; nothing errors, nothing
crashes. And `RoutingPolicy.order_for()` (`glc/routing/policy.py:298`) expands
a tier's declared `order` (e.g. `[gemini, groq, ...]`) against `available`,
which is that same registry — a name with no live instance just contributes
nothing to the candidate list. No special-casing needed anywhere.

Consequences for this migration, matching your instruction directly:

- **Gemini**: leave the code, leave `gemini` in every `routing.yaml`/
`DEFAULT_ORDER` list exactly as it is today. Just don't set
`GEMINI_API_KEY`/`GEMINI_API_KEY_1..N` in the new deployment's `.env`. It
goes fully inert with zero code changes and reactivates the instant a key
is added later.
- **Anthropic / OpenAI (new)**: follow the identical one-line pattern. We do
**not** port any API key values from either old codebase — the new `.env`
ships with `ANTHROPIC_API_KEY=` / `OPENAI_API_KEY=` empty (or the lines
simply absent). Until you add a real key, those providers silently don't
exist in the registry — no startup error, no broken endpoint, `/v1/chat`
just won't offer them as a candidate. Same for every local model added in
Phase 1/4 that needs no key at all (Ollama-backed), and the same for any
future provider — this is now the standing convention, not a one-off.



## Phase 4 — preflight as a first-class glc_v5 endpoint

- `POST /v1/preflight`: one real minimal chat call + one real minimal embed
call (using the default embedding profile), returns per-path pass/fail —
this is the thing `/healthz` doesn't do today (it only proves the process
is alive).

**Verification:** run it against a fully-configured dev environment (all
pass), then deliberately break one provider (bad key) and confirm it reports
that path's failure with a clear message rather than a 500.

## Phase 5 — client module

- New `glc/client.py` (or small standalone package) modeled on llm_gateway's
`LLM` class, but calling glc_v5's real routes: `chat`, `stream`, `embed`,
`preflight`, `resolve_chat_profile`.

**Verification:** exercise every method against a running dev server.

## Explicitly deferred (own sessions later, not part of this plan)

- routing.yaml tier/role/ladder tuning for your actual use cases.
- Classifier/router: whether it runs at all, and on what model, given the
free-hosted-LLM security question you raised.
- Cascade/escalate: the pay-twice-on-cloud / no-RAM-for-local /
free-model-security three-way bind has no resolution yet.
- Image-block wire format reconciliation between `/v1/vision` and inline
image blocks in `/v1/chat` (currently no conflict, revisit only if one
actually shows up).

---



## UI concept — "a prompt going outside" (per your request, design only, not built)

The idea: a live dashboard panel where the gateway is drawn as a hub in the
center, and every provider (Anthropic, OpenAI, Ollama, Groq, Cerebras,
OpenRouter, GitHub Models...) is a fixed node arranged around it. When a
request comes in:

1. A small pulse animates from the center outward toward whichever provider
  node the routing decision picked — labeled in-flight with the role/tier/
   profile that made the choice (e.g. "decision → FRONTIER → github").
2. The pulse's color encodes outcome once it resolves: green = ok, amber =
  escalated/retried (shows the cascade visually, when that's ever turned
   on), red = failed/fell back to the next provider in the ring.
3. A thin trailing line stays for a few seconds after the pulse lands, so a
  burst of traffic reads as a small starburst rather than single blips —
   this is what makes "many requests going out" legible at a glance instead
   of just a table of rows.
4. Hovering a node shows that provider's live rate-limit state (RPM/RPD used,
  cooldown remaining) — pulled from the same state `/v1/status` already
   exposes.
5. A side panel lists the last N calls as text (provider, model, tokens,
  cost, latency) for when you want the exact numbers instead of the
   animation.

This is a natural fit for glc_v5's existing `/v1/status`, `/v1/providers`,
`/v1/capabilities`, and `/v1/calls` endpoints — no new backend data is
needed to build a first version, it's purely a visualization layer on data
the gateway already reports. Best built once Phase 3 lands (there need to be
real Anthropic/OpenAI calls worth watching leave the hub).