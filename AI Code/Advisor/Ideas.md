# Recreating the advisor

First: the semantics you're copying, from the primary docs, because most reimplementations get these wrong.

The executor emits a `server_tool_use` block with `name: "advisor"` and an **empty input** — the executor signals *timing*, the server supplies the *context*. Anthropic then runs a separate inference on the advisor model, which runs under its own system prompt and receives the executor's full transcript as quoted context: your system prompt, tool definitions, prior turns and tool results, and the text the executor has produced so far in this turn. The advisor runs without tools and without context management; its thinking blocks are dropped, and only the advice text reaches the executor, which then continues generating inside the same request.

Four properties worth preserving, in priority order:

1. **Empty input.** The executor doesn't summarize its problem. Summarization is where the value leaks — the advisor's edge comes from seeing raw tool results the executor may have misread.
2. **Escalation, not delegation.** Cheap model drives; strong model is consulted. Inverse of the usual orchestrator pattern.
3. **Advice returns mid-turn**, not as a new user message. It reads as counsel, not instruction.
4. **Advisor is toolless and stateless.** It only reasons over the transcript.

## Fork: are you rebuilding or configuring?

If your agents run on the Anthropic API directly, there's nothing to rebuild — add the `advisor-tool-2026-03-01` beta header and a `{"type": "advisor_20260301", "name": "advisor", "model": "claude-opus-5"}` entry in `tools`. Done in ten minutes.

The rebuild is worth it if you want it provider-agnostic — Gemma-via-Ollama as executor escalating to Opus, or Gemini executor with a Claude advisor. The native tool is unavailable on Bedrock, Google Cloud, and Microsoft Foundry, so a gateway-level implementation is the only way to get it everywhere. That's the version below, built into your LLM Gateway so every client — including a phone — inherits it from config.

## Architecture

Gateway intercept, LiteLLM-style:

```
executor request
  → gateway injects advisor tool schema (empty input_schema) into tools[]
  → executor returns tool_use(name="advisor", input={})
  → gateway INTERCEPTS (never forwards to client)
  → gateway builds advisor prompt: advisor system prompt + full transcript as quoted context
  → separate completion to advisor model, no tools
  → strip thinking, take text
  → append as tool_result, re-request executor
  → loop until non-advisor stop
```

The one fidelity loss you can't avoid: you break the turn and re-request, where Anthropic continues generation in place. Costs you a re-read of the prompt each consult. Mitigate with prompt caching on the executor side, not by trying to be clever.

## Build phases

**P1 — Transcript serializer.** The hard part, not the loop. You need a faithful `messages[] → single quoted context block` renderer that keeps tool calls and results in order, including partial current-turn text. Write this first, test it standalone against a saved transcript. If this is lossy, everything downstream is theater.

**P2 — Advisor system prompt.** Yours, not borrowed. Anthropic's is hidden; you're writing a reviewer persona: blunt, verdict-first, names the specific failure mode, no restatement of the transcript.

**P3 — Intercept loop.** Config surface: `advisor_model`, `max_uses` (per-request cap), `max_tokens` (advisor output ceiling), `caching`.

**P4 — Executor prompting.** The docs publish their suggested timing block verbatim — take it as-is, it's free and measured. Core rule: call before substantive work, when stuck, when changing approach, and before declaring done.

**P5 — Accounting.** Mirror `usage.iterations[]` — per-iteration rows tagged executor vs advisor, billed at different rates. Your gateway already has SQLite logging; add a model-tagged column rather than a summed total, or your cost numbers will be wrong from day one.

## Non-obvious settings that decide whether this is cheap or expensive

Advisor output is the largest cost driver, and the executor's `max_tokens` does not bound it. Two levers: a `max_tokens` cap on the tool definition — 2048 cut mean advisor output roughly 7x with near-zero truncation and no detectable quality loss in Anthropic's testing, while 1024 truncated around 10% of calls; and a soft prompt constraint. Because the advisor sees your user messages as quoted context, a line addressed directly to it inside the user message ("Advisor: keep guidance under 80 words") is followed far more reliably than a third-person instruction — ask for ~80% of your true ceiling since it's soft.

On caching: the advisor's prompt on call N is call N−1's prompt with one segment appended, so the prefix is stable — but the cache write costs more than the reads save below roughly three advisor calls per conversation. Off for short tasks.

On call rate — this is where a local Gemma executor will bite you. Anthropic found that appending a plain-text nudge before turn 2 when no advisor call has happened raised Haiku pass rates by ~7 points, but 74–98% of nudged attempts then called immediately at turn 2 — and if the baseline first call was naturally turn 7 or later, that early nudge correlated with a 3–4 point performance drop. So: measure your executor's baseline first-call turn *before* adding any nudge, and set the threshold above it. Don't ship the nudge and the "call sparingly" language together; they conflict.

## Eval

Ship a harness before you tune prompts. Fix ~30 tasks from your own workload — forensic-accounting pipeline steps are a good fit, since they have checkable outputs. Three arms: executor solo, executor+advisor, advisor solo. The claim you're testing is that arm 2 lands near arm 3 at close to arm 1's cost. If it doesn't on your tasks, the pattern isn't earning its complexity — the docs say plainly that results are task-dependent.

**Gap I'd flag:** I haven't verified how Ollama/Gemma handles a tool with an empty `input_schema` — some local runtimes reject or mangle zero-property schemas. Test that on day one, since the whole design rests on it. Fallback is a single dummy string field you discard.

---

## Decisions and implementation plan

### Items found in this document

1. **Empty input.** The executor doesn't summarize its problem. Summarization is where the value leaks — the advisor's edge comes from seeing raw tool results the executor may have misread.
2. **Escalation, not delegation.** Cheap model drives; strong model is consulted. Inverse of the usual orchestrator pattern.
3. **Advice returns mid-turn**, not as a new user message. It reads as counsel, not instruction.
4. **Advisor is toolless and stateless.** It only reasons over the transcript.
5. **P1 — Transcript serializer.** The hard part, not the loop. You need a faithful `messages[] → single quoted context block` renderer that keeps tool calls and results in order, including partial current-turn text. Write this first, test it standalone against a saved transcript. If this is lossy, everything downstream is theater.
6. **P2 — Advisor system prompt.** Yours, not borrowed. Anthropic's is hidden; you're writing a reviewer persona: blunt, verdict-first, names the specific failure mode, no restatement of the transcript.
7. **P3 — Intercept loop.** Config surface: `advisor_model`, `max_uses` (per-request cap), `max_tokens` (advisor output ceiling), `caching`.
8. **P4 — Executor prompting.** The docs publish their suggested timing block verbatim — take it as-is, it's free and measured. Core rule: call before substantive work, when stuck, when changing approach, and before declaring done.
9. **P5 — Accounting.** Mirror `usage.iterations[]` — per-iteration rows tagged executor vs advisor, billed at different rates. Your gateway already has SQLite logging; add a model-tagged column rather than a summed total, or your cost numbers will be wrong from day one.
10. **Eval**
11. **Gap I'd flag:** I haven't verified how Ollama/Gemma handles a tool with an empty `input_schema` — some local runtimes reject or mangle zero-property schemas. Test that on day one, since the whole design rests on it. Fallback is a single dummy string field you discard.

### Product and technical decisions

- Build the first release as a dependency-free Python 3.11 library, not an HTTP service. Provider SDK and transport integration will sit behind one small callable protocol so Ollama, Anthropic, Gemini, or LiteLLM adapters can be added without changing the loop.
- Use a compact canonical request/response model that preserves arbitrary provider content blocks as JSON-compatible mappings. Unknown blocks are serialized without interpretation so the transcript does not silently lose data.
- Render advisor context as canonical JSON inside explicit quote boundaries. Include the executor system prompt, injected tool definitions, prior messages, and the executor's partial assistant response in exact order.
- Inject a true zero-property JSON Schema advisor tool by default. Also expose an opt-in dummy-field compatibility mode for runtimes that reject empty schemas; the gateway discards that field.
- Keep the advisor toolless and stateless. Strip all non-text output blocks from its response before returning advice to the executor as an `advisor` tool result.
- Intercept only responses whose tool calls are all advisor calls. Mixed advisor and client tool calls return to the client unchanged because the gateway cannot fabricate results for client-owned tools.
- Enforce `max_uses` by returning a synthetic tool result explaining that the consultation budget is exhausted, then let the executor finish. This avoids leaking the internal tool call to clients and prevents an infinite loop.
- Default `max_uses` to 2, advisor `max_tokens` to 2048, caching off, and no automatic turn nudge. Caching and nudging need workload measurements first.
- Add optional SQLite accounting with one row per executor/advisor inference, model and role columns, token fields, and request/iteration identifiers. Do not collapse differently priced models into one number.
- Ship a deterministic three-arm evaluation harness interface now, but defer a real 30-task corpus and provider integrations because this empty repository contains neither workload examples nor credentials.

### Implementation Plan

#### Items in scope for this session

1. Transcript serializer — preserve the full request and partial executor response in a stable quoted representation.
2. Advisor prompt and executor timing prompt — provide explicit, tested prompts for both roles.
3. Advisor intercept loop — inject the tool, invoke the executor and advisor, return advice mid-request, cap usage, and handle compatibility mode.
4. Iteration accounting — expose structured per-call usage and optional SQLite persistence.
5. Evaluation harness — run executor-only, executor-plus-advisor, and advisor-only arms over caller-supplied tasks.
6. Automated tests — cover serialization, tool injection, interception, thinking removal, usage limits, mixed tool behavior, accounting, and evaluation arms.

#### Items deferred to a future session

1. HTTP/OpenAI-compatible server — deferred until a target wire protocol and deployment environment are selected.
2. Concrete Anthropic, Ollama, Gemini, and LiteLLM adapters — deferred because no provider, credentials, or dependency policy is specified.
3. A fixed 30-task production evaluation corpus — deferred until real workload examples and checkable scorers are available.
4. Automatic call nudging and cache heuristics — deferred until baseline call timing and consultation counts are measured.

#### What I'll build

- **Core models:** typed request, response, usage, configuration, and gateway result objects.
- **Transcript serializer:** canonical JSON rendering with quote boundaries and support for arbitrary tool/result blocks.
- **Prompting:** a verdict-first advisor system prompt and an executor timing block.
- **Gateway:** a provider-neutral async intercept loop with empty-schema injection, dummy-field fallback, maximum-use enforcement, and text-only advisor results.
- **Accounting:** SQLite iteration storage and in-memory `usage.iterations` output.
- **Evaluation:** caller-supplied tasks executed across three comparable arms.
- **Tests:** standard-library `unittest` coverage with deterministic fake providers.

#### Assumptions I'm making

- Python 3.11 or newer is available.
- The embedding application can translate its provider's wire format into the library's canonical request/response objects.
- One response should not mix an internal advisor tool call with external client-owned tool calls; mixed calls are passed through unchanged.
- Updating this existing ideas document is explicitly requested; no additional documentation files will be created.

#### Questions I still have

None. The request authorizes sensible defaults, and the unresolved provider and deployment choices are isolated behind interfaces rather than guessed.

The plan above is approved for implementation by the request to make the decisions and make this a reality. Implementation will proceed in batch mode, followed by a file and test summary.

---

## v0.2 runnable vertical slice decisions (2026-08-07)

### Completed scope

1. Added a dependency-free, non-streaming OpenAI-compatible Chat Completions adapter for canonical text, tool use, tool results, function schemas, JSON arguments, token usage, and finish reasons.
2. Added sanitized provider-boundary errors for HTTP failures, timeouts, connection failures, malformed JSON, malformed response shapes, and invalid function arguments.
3. Added the `advisor-gateway run` CLI with prompt/stdin input, flag/environment configuration, local executor defaults, required model/advisor settings, consultation limits, dummy-field compatibility, optional SQLite usage recording, and plain or JSON output.
4. Hardened advisor interception: inputs must match the empty or configured dummy-field contract; duplicate advisor calls in one executor response share one inference; call IDs must be valid and unique; empty advisor text raises `AdvisorResponseError`.
5. Added executable documentation, privacy guidance, deterministic adapter/gateway/CLI tests, and a fake local HTTP end-to-end path.
6. Set the package version to `0.2.0` while preserving the provider-neutral library, accounting, serializer, prompting, and evaluation interfaces.

### Explicit v0.2 decisions

- Use only the Python 3.11 standard library and keep transport behind the existing async provider protocol.
- Treat a base URL as an OpenAI-compatible `/chat/completions` root and reject embedded credentials, query strings, fragments, and non-HTTP(S) schemes.
- Never expose response bodies, request URLs, prompts, or API keys in user-facing provider errors.
- Count simultaneous duplicate advisor tool calls as one consultation and reuse the same advice for every distinct tool call ID.
- Reject rather than silently repair malformed advisor arguments or empty advisor output.
- Keep stdin as the default input source when `--prompt` is absent; provide `--stdin` for explicit scripts and mutual-exclusion checking.
- Record only model-tagged token accounting in SQLite, never transcript content or credentials.

### Deferred after v0.2

1. Streaming responses and in-place continuation fidelity.
2. An OpenAI-compatible inbound HTTP proxy/server.
3. Provider-specific SDK features, retries, rate-limit backoff, and prompt-cache controls.
4. Automated redaction or data-loss-prevention policy enforcement.
5. Client-owned tool execution when mixed with advisor calls.
6. A production workload corpus and measured cache/nudge tuning.
