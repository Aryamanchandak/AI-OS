# Consolidated notes

This file merges the seven documents that used to sit as separate "copy"
files in this folder. They split into two unrelated subjects, kept as two
parts below. `PORTING_FROM_V7_GATEWAY.md` is intentionally **not** included
here — it's the one live, unactioned proposal in this folder and stays on
its own.

- **Part 1 — `glc` reference guides** (architecture, policy, voice). These
  are exact duplicates of `docs/ARCHITECTURE.md`, `docs/POLICY_GUIDE.md`,
  and `docs/VOICE_GUIDE.md`, which already exist in this repo's `docs/`
  folder — kept here only for a single-file record.
- **Part 2 — V7 gateway change history** (cleanup + three dated change
  notes). These describe a different, already-archived codebase (the plain
  V7 chat+embed proxy at `../Outdated LLM_gateway/llm_gateway old old/`),
  not this repo. Kept here as historical record, in chronological order.

---

# Part 1 — `glc` reference guides

## 1.1 Architecture

Session 11 §7 names six architectural moves that distinguish GLC v1
from OpenClaw's default posture. Each is a direct response to a
documented OpenClaw failure mode. The mapping below names the move,
where it lives in this repository, and which incident it answers.

### 1. The agent does not get host execution authority by default

The runtime is the S9 multi-agent DAG plus the typed skill catalogue.
Tools live as named typed handlers; there is no generic `shell.exec`
endpoint that the agent can reach by default. Channel adapters speak
typed Pydantic envelopes (`ChannelMessage`, `ChannelReply`) — they
never hand a Discord embed or a Telegram InputFile to the agent.

Lives in: `glc/channels/envelope.py`, `glc/channels/base.py`.
Answers: ClawJacked.

### 2. The policy engine runs outside the LLM context

`glc/policy/engine.py` is a small declarative evaluator. Rules are
specified in `glc/policy/policy.yaml` (or `~/.glc/policy.yaml` to
override). Every tool call is intercepted before dispatch and evaluated.
First matching rule wins; ties resolve to deny. The defaults for
`owner_paired` and `untrusted` are allow and deny respectively. The
yaml hot-reloads on `SIGHUP`.

Lives in: `glc/policy/`.
Answers: the Summer Yue email-deletion incident, where the "confirm
before acting" rule lived inside the conversation context and was
erased by context compaction. Yaml does not compact.

### 3. Memory is classed with per-class write permissions

The audit store (`glc/audit/`) is append-only: only `append()` is
exposed; no `update`, no `delete`. The pairing store, the channels
configuration, and the policy rules all live outside the LLM's
write reach. Sessions 12 and onward expand the memory taxonomy to
working / episodic / semantic / procedural classes; the
write-permission discipline begins here.

Lives in: `glc/audit/`, `glc/security/pairing.py`, `glc/config.py`.
Answers: persistent-prompt-injection attacks that would otherwise
mutate the agent's own constraints.

### 4. The control plane has an out-of-band path

`/v1/control/kill`, `/v1/control/pair`, `/v1/control/presence` are
authenticated by a per-installation token (`~/.glc/install_token`)
and isolated from the channel traffic. The kill endpoint binds
127.0.0.1 by default; bypassing this requires `GLC_KILL_ALLOW_REMOTE=1`
and a deliberate operator decision. The intent is to make "STOP"
reachable through a phone-friendly URL the user can hit when the
agent has gone off the rails inside the channel.

Lives in: `glc/routes/control.py`.
Answers: Summer Yue having to physically reach the Mac mini.

### 5. Every channel envelope carries a trust level

`TrustLevel` is `owner_paired | user_paired | untrusted`. Adapters
classify inbound messages via `glc/security/trust_level.py`, which
consults the pairing store. The policy engine reads the trust level
before authorising any tool action; the lecture's default rule
denies all tools for `untrusted`.

Lives in: `glc/channels/envelope.py`, `glc/security/trust_level.py`,
`glc/policy/`.
Answers: confused-deputy and indirect-prompt-injection. An email
scraped from the inbox can carry instructions, but it arrives with
`trust_level=untrusted` and the policy engine rejects everything.

### 6. Every action is logged append-only

`glc/audit/store.py` writes to `~/.glc/audit.sqlite`. Each row carries
session id, channel, sender id, trust level, event type, tool, policy
verdict, params, result. The S8 replay viewer reads from the same
store. Each insert commits immediately so the trail survives a hard
kill.

Lives in: `glc/audit/`.
Answers: the recovery scenario after a bad outcome — the operator
can replay exactly what the agent saw and did.

### What S12 works on

The S11 policy engine is the application-level enforcement layer.
S12 moves this gateway onto Modal containers and then hardens it. The
environmental layer it needs, container isolation per component,
short-lived scoped credentials in place of one shared secret, and
network egress filters, is not built yet. Building it is the
assignment. The two layers should run independently, so that a
failure in one does not invalidate the other.

## 1.2 Policy guide

The policy engine is the deterministic safety layer that runs outside
the LLM context. Lecture §10 documents the five default rules; this
guide explains how to extend them.

**Where policy lives.** `glc/policy/policy.yaml` ships with the lecture's
five defaults. To override on your installation, drop a `policy.yaml`
into `~/.glc/`. The engine prefers the user file when present.

Hot-reload by sending `SIGHUP` to the gateway process:

```sh
kill -HUP $(pgrep -f "uv run glc serve")
```

Malformed YAML does not crash the gateway: the engine falls back to
a deny-everything safe default and logs the parse error.

**Rule shape:**

```yaml
rules:
  - tool: email.send                # literal or "*"
    channel: telegram               # literal or "*" (default "*")
    trust_level: owner_paired       # literal or "*" (default "*")
    condition:
      recipient_type: external      # exact match
      path_glob: "~/Documents/**"   # fnmatch glob
      command_matches: ["sudo"]     # substring (any-match if list)
      foo_regex: "^bad-.*$"         # re.search
      something_in: ["a", "b"]      # set membership
    action: deny                    # allow | deny | require_approval
    reason: "external recipient requires approval"
```

**Evaluation order.** For each tool call, the engine walks rules top to
bottom:

1. The first rule whose `tool` / `channel` / `trust_level` / `condition`
   all match determines the verdict.
2. If any matching rule has `action: deny`, that overrides — deny
   wins on ties.
3. If no rule matches, the default is `allow` when `trust_level ==
   owner_paired`, otherwise `deny`.

This means: a permissive `tool: "*", action: allow` rule at the top
makes the engine essentially open for everyone whose `trust_level`
makes it through earlier deny rules. Use sparingly.

**`require_approval`.** When the verdict is `require_approval`, the
agent runtime sends an approval-request message back through the
originating channel and blocks on confirmation. The S11 runtime stub
does not implement the confirmation loop yet — it will land alongside
the S12 agent runtime work.

**Audit trail.** Every verdict is written to `~/.glc/audit.sqlite` as
part of the `tool_dispatch` event row. Use `glc.audit.query()` or open
the S8 replay viewer to inspect.

**Testing your policy:**

```sh
uv run python scripts/validate_policy.py
```

The script loads `policy.yaml` and runs one evaluation per rule. Any
parse error or schema mismatch fails CI.

## 1.3 Voice guide

Session 11 §9 names the current free-tier picks for STT and TTS in
mid-2026. This guide covers the API keys, model downloads, and
gotchas per provider.

**STT (`POST /v1/transcribe`)**

| `prefer`     | Provider                       | Setup                                                     |
|--------------|--------------------------------|-----------------------------------------------------------|
| `default`    | Groq Whisper Large v3 Turbo    | Free signup at `console.groq.com`; export `GROQ_API_KEY`. |
| `local`      | whisper.cpp + base model       | `./daemon/install.sh --models` fetches the base model.    |
| `streaming`  | (intentionally returns 400)    | Streaming STT belongs on the Gemini Live WebSocket; S12.  |

The Groq free tier covers thousands of minutes per month; the model
runs on Groq's LPU hardware so latency stays sub-second for short
clips. Local whisper.cpp is the offline fallback at ~200 MB on disk.

**TTS (`POST /v1/speak`)**

| `prefer`     | Provider             | Setup                                                                                    |
|--------------|-----------------------|-------------------------------------------------------------------------------------------|
| `default`    | Kokoro-82M (local)   | `uv pip install kokoro`; model lazy-loads to `~/.glc/models/kokoro-82M/`.                |
| `quality`    | ElevenLabs Flash v2.5| Free tier 10k chars/month; export `ELEVENLABS_API_KEY` and `ELEVENLABS_VOICE_ID`.        |
| `streaming`  | Cartesia Sonic       | Free tier; export `CARTESIA_API_KEY` and (optional) `CARTESIA_VOICE_ID`.                 |
| `fallback`   | system TTS           | macOS `say`, elsewhere `pyttsx3`. Zero-config; useful when offline and no Kokoro model.  |

Kokoro is the daily driver: open weights, 82M parameters, runs
faster than realtime on a laptop CPU, voice quality close to
ElevenLabs for most uses. ElevenLabs covers the cases where Kokoro's
voice palette is too narrow. Cartesia is the latency play —
sub-50ms time-to-first-audio for streaming use cases like
`twilio_voice` outbound.

**Realtime full-duplex.** `webui` and `twilio_voice` adapters open a
Gemini Live WebSocket session through the gateway. This route is
**not** implemented in S11 — the adapter test suite mocks it. The real
session token is deliverable in S12.

**Cost reporting.** STT and TTS calls land in the per-agent ledger
under `agent: channel:<name>`. View with:

```sh
curl http://localhost:8111/v1/cost/by_agent
```

**Offline tests.** The voice routing tests under
`tests/test_voice_routing.py` inject fakes via `monkeypatch` and never
hit a real provider. CI runs offline and passes on a fresh checkout
with no API keys set.

---

# Part 2 — V7 gateway change history

These four documents describe `llm-gateway-v7`, the archived codebase now
living at `../Outdated LLM_gateway/llm_gateway old old/`. Not applicable to
this repo's `glc` code directly — kept as record of what that codebase's
cleanup and feature work looked like. `PORTING_FROM_V7_GATEWAY.md`
(kept separate, alongside this file) is the doc that actually evaluates
which of these V7 changes are worth carrying into `glc`.

## 2.1 Cleanup summary

**Context.** The gateway had grown around older V1/V2/V3 history. The
current direction is to simplify it into a small personal LLM gateway
while preserving the parts that are genuinely useful.

**Product decisions.** Keep:

- `POST /v1/chat`
- `POST /v1/embed`
- Explicit/configured provider selection
- SQLite call logs
- Rate/cooldown/backoff awareness
- Embedding status/config endpoint
- A small Python client
- Generic structured-output support for caller-provided Pydantic models
- Optional native tool-call protocol translation if the harness uses model
  emitted tool calls

Do not add:

- Gateway-owned tool registry
- Gateway-owned tool execution
- Agent loop inside the gateway
- Shared contracts package before repeated cross-project reuse exists

Remove or reduce during cleanup:

- Old V3 router/classifier history
- `auto_route` leftovers
- Web UI references
- Stale router-decision fields
- Broad historical README material
- Any compatibility path that only preserves old behavior and is not needed
  for the current gateway

**Tool-call clarification.** The MCP server and harness own tools. The
gateway should not register or execute tools. The only tool-related
behavior worth keeping is deterministic provider protocol translation:

```text
MCP/harness tool schema
        -> canonical gateway ToolDef
        -> provider-specific request shape
        -> provider-specific response shape
        -> canonical gateway ToolCall
        -> harness executes through MCP
```

This is useful because OpenAI, Anthropic, Gemini, and Ollama each expose
native tool/function calling differently. It is also a likely failure
point, so it now has focused offline tests.

**Structured output clarification.** Tool input contracts belong with
MCP tools. Structured output is separate — for cases where the caller
wants the model's final response, extraction, classification, or
decision as typed JSON. The useful future abstraction is a generic
client helper:

```python
decision = llm.structured(..., output_model=SomePydanticModel)
```

The gateway client should accept a caller-provided Pydantic model,
convert its JSON schema into `response_format`, validate the response,
and return a typed instance. The gateway should not own project-specific
contracts.

**Files added:** `AGENTS.md` (cleanup handoff note), `CLEANUP_SUMMARY.md`
(this summary), `tests/test_tool_translation.py` (offline unit tests for
deterministic tool schema translation and returned tool-call
normalization — OpenAI, Anthropic, Gemini, Ollama native + prompted
fallback, and canonical turns translated back per-provider).

Verified:

```text
uv run pytest -q tests/test_tool_translation.py
6 passed

uv run pytest -q tests/test_tool_translation.py tests/test_provider_registry.py
8 passed
```

**Recommended cleanup order:**

1. Rewrite `README.md` around the current gateway only.
2. Remove `auto_route` from `client.py` and stale docs/tests.
3. Add a lightweight `LLM.structured(...)` helper for arbitrary
   caller-provided Pydantic output models.
4. Split the large `/v1/chat` handler in `main.py` into smaller helpers.
5. Consider renaming `router.py` to something like `selection.py` or
   `provider_state.py` if it reduces confusion without too much churn.
6. Split `providers.py` by backend if provider code continues to grow.
7. Remove unused schema/database fields only after checking migration
   impact on the existing `gateway_v7.db`.
8. Keep tests focused on retained behavior: provider registry, no chat
   runtime failover after selected-provider errors, tool-call
   normalization, structured output validation/repair, embeddings, and
   rate-state behavior.

## 2.2 2026-07-27 — Preflight + embedding profiles

| Field | Value |
|---|---|
| **Version** | `llm-gateway-v7` bumped `0.1.0` → `0.2.0` |
| **Scope** | Two additive, backward-compatible features closing T3 items #2 and #3 from the ingestion-pipeline plan |

**Server side (`llm_gateway`).**

*Stable embedding profiles* (`embedders.py`, `schemas.py`, `main.py`):
new `embedders.PROFILES: dict[str, dict]` registry, currently one entry
(`"chunker-v1": {"provider": "ollama", "model": "nomic-embed-text", "dim": 768}`).
`EmbedRequest`/`EmbedResponse` gained an optional `profile` field.
`POST /v1/embed` with `profile` set: unknown profile → 400; profile +
conflicting `provider` → 400; profile resolves to a pinned
`(provider, model)`; if the provider's actual response model or dim
doesn't match the pin → 500, fail loud, no silent pass-through (both
checked, since model-name alone would miss a re-pulled/reconfigured
model returning a different width under the same name — the whole
point of a profile is to be a guarantee, not a hint). `GET
/v1/embedders` gained a `"profiles"` key. Nothing existing was renamed
or removed.

*No preflight-specific server changes* — preflight is a client-side
composition of two existing real calls (`POST /v1/chat`, `POST
/v1/embed`); `/v1/status` and `/v1/embedders` were rejected for this
purpose since they report rate-limiter bookkeeping, not actual
reachability.

**Client (`client.py`).** `LLM.embed()` gained `profile` (mutually
exclusive with `provider`). New `LLM.status()`, `LLM.embedders()`, and
`LLM.preflight(*, embedding_profile="chunker-v1", chat_provider=None)`
— makes one minimal structured `chat()` call
(`max_tokens=256, reasoning="off"`, `{"ok": boolean}` schema) and one
`embed(profile=...)` call, raises `GatewayPreflightError` (new
exception, `.checks` holds per-path failure detail) if either fails.
`max_tokens=256` and `reasoning="off"` are deliberate, not arbitrary
(see below) — don't lower `max_tokens` without re-running
`tests/test_client_preflight_live.py` against a reasoning-capable
provider.

**Tests added:** `tests/test_profiles.py` (6, 2 `local`),
`tests/test_client_preflight.py` (3, mocked, no `local` marker),
`tests/test_client_preflight_live.py` (2, real `uvicorn` server on a
free port, both `local`). Full suite after this change: 23 passed (was
12).

**What the real (`_live`) test caught that the mocked test alone
missed:**

1. **`max_tokens` too low for a reasoning-capable model.** First draft
   used `max_tokens=16` then `64` with a trivial schema.
   `gemini-2.5-flash` spends output-token budget on invisible
   "thinking" before the visible answer; at low `max_tokens` it would
   sometimes burn the whole budget mid-thought, truncate the JSON, and
   fail schema validation — a real gateway 503, correctly raised, but a
   false preflight failure against a healthy gateway. Fixed by adding
   `reasoning="off"` and raising `max_tokens` to 256: 10/10 clean
   structured completions in a row afterward.
2. **The gateway's default chat provider order tried `gemma` first**
   (local, small model) when no `chat_provider` was pinned, and it
   could fail even a trivial strict-JSON schema intermittently.
   Superseded 2026-07-27: Gemma is no longer built as a chat provider
   by default at all (`ENABLE_OLLAMA_CHAT=1` opt-in required), and
   `GatewayExtractor` in `merged-ingestion` now pins
   `profile="knowledge-extraction-v1"` (→ `anthropic-sonnet`) for all
   real extraction calls, so production no longer touches Gemma or the
   default chat order at all.

A third, irreducible source of intermittency was observed directly
against the Gemini API: real upstream `503 UNAVAILABLE` — genuine
transient cloud-provider unavailability, not a bug.

**Migration notes for `merged-ingestion`.** Nothing there was touched
by this change (non-editable path dependency, resynced only on demand).
Both changes are additive — nothing breaks by default. Adopting the
profile: switch `client.embed(text, provider="ollama")` +
manual model/dim validation to `client.embed(text, profile="chunker-v1")`
and drop the manual validation. Adopting preflight: call
`llm.preflight(embedding_profile="chunker-v1", chat_provider="anthropic-sonnet")`
once at the start of `run_ingestion()`, refuse the run if it raises
`GatewayPreflightError`. `preflight()` doesn't yet accept a chat
*profile* directly, only `chat_provider` — a `chat_profile=` parameter
resolving through `CHAT_PROFILES` would be a natural follow-up.

**What did NOT change:** chat routing, provider order, rate limits,
tool translation; the Gemini embedding fallback (`chunker-v1` stays
pinned to `ollama` only — a profile that tolerates failover would
defeat the point of pinning); batch APIs and the multimodal/VLM
contract (deliberately deferred).

## 2.3 2026-07-29 — Phi-4 document-segmentation profile

The gateway now exposes one dedicated local chat route:

```text
document-segmentation-v1
  -> phi4-local
  -> phi4:14b-q4_K_M
```

`phi4-local` is built only when `ENABLE_PHI4_CHAT=1`. Its model tag is
fixed in the provider registry and does not read `OLLAMA_MODEL`; that
variable continues to belong only to the optional `gemma` provider. The
profile has no fallback, so a disabled, missing, or unavailable Phi-4
fails instead of selecting a hosted provider.

`GET /v1/chat/profiles/{profile}` and `LLM.resolve_chat_profile(profile)`
expose the resolved provider and exact model. `/v1/providers` also
reports chat profiles and availability.

The Ollama adapter now translates native `done_reason="length"` to the
gateway contract `stop_reason="max_tokens"`.

Offline verification:

```text
.venv/bin/python -m pytest -q \
  tests/test_provider_registry.py tests/test_tool_translation.py

13 passed
```

No model was downloaded and no live model call was made by this change.

## 2.4 2026-07-29 — Anthropic native structured output

`AnthropicProvider.chat()` now honors schema-backed `response_format`
through Anthropic's native `output_config.format` API. The previous
adapter advertised `structured=True` but silently deleted the format
before making the request.

The raw HTTP adapter mirrors Anthropic's SDK behavior:

- unsupported grammar constraints such as numeric, string, and array
  bounds are removed from the provider copy and carried into
  descriptions;
- object schemas are closed with `additionalProperties: false`;
- the caller's original schema remains untouched and is validated by
  the gateway after the provider returns;
- schema-less structured formats fail loudly rather than degrading to
  ordinary chat.

Native direct-output constraints preserve the gateway's existing
`text -> jsonschema validation -> parsed` flow. No synthetic tool call
or `main.py` tool-branch exception was added.

Package version: `llm-gateway-v7` 0.2.1.

Verification:

```text
23 passed, 10 deselected
```

A bounded live `claude-sonnet-4-6` request returned schema-constrained
JSON and gateway-populated `parsed` output. The merged ingestion
pipeline's complete batch-extraction smoke then passed using its real
Pydantic schema.

Anthropic reference:
https://platform.claude.com/docs/en/build-with-claude/structured-outputs
