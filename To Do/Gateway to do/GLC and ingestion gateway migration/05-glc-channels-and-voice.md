# Plan 05 — GLC Channels and Voice

## Related decisions

Explicitly excluded from the "always-on, fail-hard" treatment Plan 03 gives
security/audit/control — see `00-program-roadmap.md`'s program rules and
Plan 03's "Related decisions." This is the one plan in the sequence where
"moved" and "activated" are deliberately different states.

## Goal

Move channel and voice capabilities beneath Gateway while preserving their
native contracts, long-running lifecycles, signature validation, trust policy,
and secret isolation.

## Decisions required before implementation

### 1. In-process versus worker boundary

Proposed default:

- Simple webhook adapters mount in the Gateway process.
- Long-running pollers and integrations with failure-prone native dependencies
may run as supervised workers.
- Both use the same Gateway-owned channel contracts and security services.

Grounding — today's 15 channel packages under `glc_v5/glc/channels/ catalogue/`: Discord, Gmail, IMAP, LINE, local mic, Matrix, Signal, Slack,
Teams, Telegram, Twilio SMS, Twilio Voice, generic webhook, web UI, and
WhatsApp. These aren't all the same shape — a webhook-style channel (e.g.
`twilio_sms/webhook.py`) just answers an HTTP POST, cheap to run in whatever
process already has an HTTP server; a polling channel (e.g. `imap`, or
Telegram's long-poll — see `telegram/dev/live_poll.py`) holds a long-running
loop that shouldn't share a crash domain with the main Gateway process, and
some depend on native/flaky libraries where an isolated worker means one
channel's crash doesn't take down chat, ingestion, and the shell with it.

- **Approve capability-based process boundaries**: pick the boundary per
channel based on what it actually is (webhook vs. poller vs.
native-dependency-heavy), using the same shared contracts either way.
- **Require every channel in-process**: simplest deployment (one process),
but a bad native dependency or an infinite-loop bug in one channel can
degrade or crash the whole Gateway.
- **Require every channel as a separate worker**: strongest isolation, but
now every channel — even a trivial webhook — needs its own process
lifecycle, which is unnecessary overhead for the simple cases.

- [x] Approve capability-based process boundaries.
- [ ] Require every channel in-process.
- [ ] Require every channel as a separate worker.

**How you'll verify this landed:** each channel's own documentation (moved
alongside it, per Work Package B) states which boundary it runs in and why;
Work Package C's shutdown-during-active-session test passes for both an
in-process webhook and a worker-based poller.

### 2. Channel migration order

Proposed default: first migrate one simple webhook channel and one long-running
or WebSocket channel to prove both lifecycle patterns; then migrate remaining
channels individually.

Reasonable concrete candidates from today's catalogue: `twilio_sms` (already
has its own `webhook.py` and `server.py`, and its own port-8111/`GLC_BASE_URL`
usage per Plan 01's caller inventory — a clean, self-contained webhook case)
for the simple-webhook slot, and `telegram` (has a documented long-poll dev
harness at `telegram/dev/live_poll.py`) or `discord` (has
`discord/tests/run_discord_bridge.py`) for the long-running/poller slot. This
is a suggestion to react to, not a requirement — naming the actual first two
below is the point of this decision.

- [x] Approve this proof-slice approach.
- [x] Name the first two channels below: **Twilio SMS** (webhook slot) and
  **Telegram** (long-poll/worker slot) — the plan's proposed default. Aryaman
  isn't actively using any channel today, so this is picked for being the
  safest, best-documented pair (existing dev harnesses, self-contained
  webhook case) rather than for matching current usage.

**How you'll verify this landed:** the two named channels are the first
`glc_v5/glc/channels/catalogue/*` entries to gain a Gateway-owned equivalent,
each with its own passing characterization tests, before any other channel's
migration starts.

### 3. Channel-to-agent bridge

GLC currently contains an S16 agent bridge. Its ownership and failure policy
must be explicit before channel movement.

Concretely, that's `glc_v5/glc/channels/agent_bridge.py`: its own docstring
calls it "the one HTTP seam between GLC channel envelopes and S16Code" —
every channel adapter's incoming message gets converted to a common
`ChannelMessage` and sent to S16 over HTTP (via `httpx`), and S16's reply
comes back as a common `ChannelReply`. S16 itself never imports any
channel-specific SDK (Telegram, Gmail, Twilio, etc.) — the bridge is what
keeps that decoupled.

- **Keep the bridge in Gateway channels as an injected downstream service**:
the bridge code moves under Gateway's channel domain unchanged in shape —
still one HTTP call out to wherever S16 runs — just owned by Gateway
instead of GLC.
- **Move it to the agent runtime and have Gateway publish canonical events**:
a bigger structural change — Gateway would emit `ChannelMessage` events
(e.g. onto a queue or event bus) rather than calling S16 directly, and S16
would own consuming them. More decoupled, but a real redesign, not a move.

- [x] Keep the bridge in Gateway channels as an injected downstream service.
- [ ] Move it to the agent runtime and have Gateway publish canonical events.
- [ ] Define another boundary below.

**How you'll verify this landed:** whichever option is picked, a test
proves S16 still never imports a channel-specific SDK directly — only the
common `ChannelMessage`/`ChannelReply` contract from `envelope.py` crosses
the boundary, exactly as it does today.

### 4. Voice transport

Proposed default: real-time voice redesign is separate because the current
documentation identifies portions of it as not yet implemented.

Concretely: today's voice code is `glc_v5/glc/voice/stt/` and `.../tts/`,
exposed via `glc_v5/glc/routes/speak.py` (`/v1/speak`) and
`glc_v5/glc/routes/transcribe.py` (`/v1/transcribe`) — simple
request-in/response-out calls, not a streaming session. "Real-time
voice/WebSocket redesign" would mean an ongoing bidirectional audio stream
(closer to a phone call than a file upload), which is a different, larger
feature than moving the existing routes.

- [x] Preserve current request/response STT and TTS routes first.
- [ ] Include real-time voice/WebSocket redesign in this plan; describe the
  ```
  desired contract below.
  ```

**How you'll verify this landed:** `/v1/transcribe` and `/v1/speak` behave
identically after the move — same request/response shapes, same audio
limits and timeouts — checkable against the fixtures Plan 01 captured for
"transcription and speech."

### 5. Activation state after migration

Aryaman is not using most channels today (e.g. WhatsApp) and doesn't want
code that's merely been moved to become live by default. This is a distinct
question from decisions 1–4 above (which decide *how* a channel would run if
active) and from whether it gets tested (it does, unconditionally).

Proposed default: every channel and voice adapter is registered with Gateway
but **not mounted / not started** by default after migration — enabling one
is an explicit, separate configuration action, not a side effect of the move
landing. Each still passes the same characterization tests before this
plan's exit gate as if it were active; "dormant" describes what's running,
not what's tested.

- [x] Approve dormant-by-default with characterization tests still required.
- [x] No channel should be active immediately upon migration — confirms
  `migration/baseline/activation-state.md`'s existing record without change.

**How you'll verify this landed:** cross-check against
`migration/baseline/activation-state.md` (Plan 01, Work Package E), which
already records this table — this decision should confirm or correct that
record, not silently disagree with it. After migration, starting Gateway
with default configuration should not open a WhatsApp/Telegram/etc.
listener or spawn a poller for any channel you didn't explicitly enable.

## Channel activation checklist

No channel is active on day one (decision 5) — every one of the 15 channels
under `glc_v5/glc/channels/catalogue/` is moved and characterization-tested,
but dormant by default. This checklist is what "activating" a specific
channel later actually requires; use it (or hand it to whoever's doing the
work) instead of re-deriving the steps each time:

1. Confirm its move landed (Work Package B) — schemas, its own
  signature/authentication check, provider client or injected transport,
   artifact handling, and setup tooling exist under its own Gateway-owned
   folder, with its original tests passing unmodified.
2. Provide its required secrets/credentials through its own environment
  adapter — never shared with another channel, never exposed through
   administration or diagnostics output.
3. If it runs as a separate worker (decision 1), register its address in
  `config/services.yaml` (Plan 02 decision #4) rather than hard-coding it.
4. Confirm its own signature/authentication check is wired and rejects a
  tampered payload — this stays in the channel's own package (Plan 03's
   decision to keep vendor signature schemes decentralized, not a shared
   Gateway-wide auth layer).
5. Flip its explicit enable configuration — the one deliberate step that
  turns "moved" into "active" (decision 5); nothing else should cause a
   channel to start listening.
6. Verify readiness: Gateway starts normally with it enabled, and it shows
  healthy (or clearly, non-silently degraded) in Plan 03's readiness
   diagnostics.



## Work packages



### A. Shared channel core

- Canonical message, attachment, reply, and error contracts.
- Channel adapter and transport protocols.
- Registry and discovery.
- Pairing, trust, generic rate limiting, and audit integration.
- Route/service boundary for send, webhook, WebSocket, and administration.



### B. Move channel packages vertically

For each of the 15 channels in `glc_v5/glc/channels/catalogue/`, keep
together (mirroring how each channel's own folder is already organized
today — this is a move, not a reshuffle):

- Native schemas and translation.
- Signature/authentication logic. *(E.g. Twilio's webhook signature check in*
`twilio_sms/webhook.py`*.)*
- Provider client or injected transport.
- Artifact handling.
- Setup tooling and environment adapter.
- Tests, documentation, and development harnesses. *(E.g.*
`discord/tests/run_discord_bridge.py`*,* `telegram/dev/live_poll.py`*,*
`whatsapp/demo_webhook_server.py` *— these dev/demo entry points move with
their channel, not into some shared "tools" folder.)*

Do not expose stored credentials through administration or diagnostics.

**How you'll know Work Package B is done, per channel:** the channel's own
tests pass unmodified from its new location; its signature/auth check still
rejects a tampered payload; grepping its diagnostics/admin output for any
credential value it stores comes back empty.

### C. Worker lifecycle

- Define registration, readiness, restart, shutdown, and backoff behavior.
- Resolve worker addresses from the service registry. *(The*
`config/services.yaml`*-based registry from Plan 02 decision #4 — a
channel worker's address is looked up there, not hard-coded.)*
- Test shutdown during an active poll, webhook, or WebSocket session.
*(Concretely: stop Gateway while a Telegram long-poll or Discord bridge
session is mid-flight and confirm it shuts down cleanly rather than
hanging or losing an in-flight message silently.)*
- Ensure a broken optional adapter cannot prevent unrelated Gateway domains
from starting unless explicitly configured as required. *(A channel whose
credentials are missing or whose native dependency fails to load should
not stop chat, ingestion, or the shell from starting — it should show up
as one degraded/unavailable channel in the Plan 03 readiness diagnostics,
not a startup crash.)*
- Populate `GET /v1/control/presence`'s `channels` field (in
`gateway/src/gateway/control/routes.py`) with one entry per registered
channel/voice adapter and its health (healthy / degraded / disabled), in
place of the hardcoded `"channels": []` Plan 03 left there. This is what
"Plan 03's readiness diagnostics" concretely means for this plan — it's an
existing stub to fill in, not a new endpoint to build, and it's the same
place decision 5's "dormant/enabled" state should be visible.

**How you'll know Work Package C is done:** the shutdown-during-active-
session test above passes for at least one poller-style and one webhook-
style channel; deliberately misconfiguring one channel's credentials still
lets Gateway start and serve every other domain normally.

### D. Voice

- Define shared STT and TTS contracts.
- Move providers one at a time with provider-local configuration and tests.
*(Today's* `glc_v5/glc/voice/stt/` *and* `.../tts/` *— whatever individual
provider modules live under each.)*
- Preserve `/v1/transcribe` and `/v1/speak` behavior.
- Preserve audio limits, timeouts, errors, and fallback order.

**How you'll know Work Package D is done:** the "transcription and speech"
fixtures Plan 01 captured produce identical results against the moved
routes; a request exceeding today's audio size/duration limit still gets
the same error it gets today, not a generic 500.

### E. UI and administration

- Decide which GLC static pages become React shell pages. *(Confirmed:*
`glc_v5/static/` *holds* `channels.html`*,* `dashboard.html`*,* `help.html`*, and*
`observability.html`*, mounted at* `/static` *by* `glc_v5/glc/main.py` *— GLC's
own admin pages, separate from the AI OS shell under* `shell/dist/`*. This
decides which of these four get reimplemented as shell pages versus
dropped.)*
- Preserve necessary channel setup and health information.
- Remove duplicated static pages only after equivalent UI/API capability
exists. *(Don't delete a GLC static admin page for a channel until the
shell can do the same setup/health job — otherwise there's a window with
no way to configure that channel at all.)*

**How you'll know Work Package E is done:** for every GLC static page
marked for removal, the shell has an equivalent page live and working
*before* the static page is deleted — check by using the shell's version to
actually perform the same setup task the static page did.

## Explicitly out of scope

- Ingestion movement.
- Agent-runtime redesign unless selected in decision 3.
- New channels or voice providers.
- Unimplemented real-time voice features unless explicitly approved.



## Exit gate

- Runtime channel and voice implementations do not import legacy `glc.*` code.
- Webhook signatures, WebSocket behavior, polling, send, STT, and TTS contracts
pass preserved tests.
- Secrets remain provider-local and redacted.
- Worker startup and shutdown behavior is supervised and observable.
- Optional integration failure does not take down unrelated Gateway domains.
- Every channel and voice adapter is registered but disabled by default
(decision 5), with no exceptions left undeclared.



## Aryaman's comments

All five decisions confirmed at the plan's proposed defaults (2026-09-22):

1. Capability-based process boundaries (per-channel, not all-in-process or
   all-worker).
2. First two channels: **Twilio SMS** (webhook) and **Telegram** (worker/
   poller). Not chosen because either is currently in active use — Aryaman
   isn't actively using any channel today — chosen because they're the
   best-documented, self-contained pair to prove both lifecycle patterns.
3. S16 agent bridge stays in Gateway channels as an injected downstream
   service, unchanged in shape.
4. Voice: preserve `/v1/transcribe` and `/v1/speak` unchanged; real-time/
   WebSocket voice is explicitly deferred, not part of this plan.
5. No exceptions to dormant-by-default — every channel and voice adapter is
   registered but off until explicitly enabled later, confirming
   `migration/baseline/activation-state.md` as-is.

## Plain-language explanation



### What is this plan trying to do?

Today, GLC contains the code that connects AI OS to services such as Telegram,
Discord, Gmail, WhatsApp, Twilio, and the speech-to-text and text-to-speech
providers. This plan moves that existing code into Gateway, so Gateway becomes
the single place that receives and sends messages and handles voice requests.

This is mainly a careful relocation, not a redesign. After a channel has moved,
it should accept the same messages, perform the same security checks, return the
same replies, and use the same credentials as it does today.

Moving a channel does **not** mean turning it on. All channels will remain off
by default. A channel will start only when Aryaman explicitly enables it and
provides its credentials. This prevents unused integrations such as WhatsApp or
Telegram from unexpectedly opening connections or listening for messages.

### The simplest way to think about the work

There are five parts:

1. Create one common set of message rules in Gateway. Every channel will use
  the same basic format for incoming messages, attachments, replies, and
   errors, while keeping its provider-specific code in its own folder.
2. Move each channel into Gateway one at a time. Its code, security checks,
  tests, setup tools, and documentation move together so nothing gets lost.
3. Decide how each channel runs. Simple webhooks can run inside Gateway.
  Channels that stay connected, continuously poll, or use fragile libraries
   can run as separate workers so a failure does not crash the rest of Gateway.
4. Move the existing voice endpoints into Gateway without changing their
  behavior. Real-time, call-like streaming voice is a separate future project
   unless it is deliberately added to this plan.
5. Replace GLC's old administration pages only after the main AI OS interface
  can perform the same setup and health-check tasks.



### Why start with two channels?

The plan proposes moving one simple webhook channel and one continuously
running channel first. This proves that both kinds of integration work before
the remaining channels are moved.

A sensible first pair is:

- Twilio SMS, to prove the simple webhook approach.
- Telegram, to prove the separate long-running worker approach.

Once both work correctly, the other channels can follow the same patterns
instead of inventing a new migration method for every channel.

### What decisions does Aryaman need to make?

Before implementation begins, Aryaman needs to confirm these points:

1. **How channels should run:** use the proposed mixed approach, where simple
  channels run inside Gateway and long-running or fragile channels use
   separate workers.
2. **Which two channels move first:** the suggested pair is Twilio SMS and
  Telegram, but another webhook-and-poller pair can be chosen.
3. **Where the S16 bridge belongs:** the simpler choice is to keep it with the
  Gateway channel code. Gateway will continue sending the standard message to
   S16 over HTTP, so S16 does not need to know anything about Telegram, Twilio,
   or other provider-specific systems.
4. **What happens with voice:** the simpler choice is to move the current
  `/v1/transcribe` and `/v1/speak` endpoints unchanged and leave real-time
   streaming voice for a later plan.
5. **Whether channels stay off after the move:** the proposed answer is yes.
  They are tested and available, but none starts until explicitly enabled.



### What will happen during the migration?

For each channel, the implementer will:

1. Record how it behaves today with tests.
2. Move its complete folder and supporting code under Gateway.
3. Connect it to Gateway's common message format.
4. Keep its own authentication or signature check in place.
5. Keep its credentials private and separate from other channels.
6. Run its existing tests from the new location.
7. Confirm that false or altered requests are still rejected.
8. Confirm that the channel is registered but does not start by default.

The voice providers will be moved in a similar way: one provider at a time,
with the existing routes, limits, timeouts, errors, and fallback behavior kept
the same.

### What does success look like?

This plan is complete when all existing channel and voice code lives under
Gateway and no longer depends on the old GLC package. Existing messages,
webhooks, polling, speech recognition, and speech generation still behave the
same. A broken optional channel cannot stop chat, ingestion, the shell, or
other Gateway features from starting. Credentials never appear in diagnostics
or admin pages. Finally, every migrated integration remains disabled until
Aryaman intentionally enables it.

In one sentence: **move the existing integrations safely, prove that they still
work, isolate the risky long-running ones, and do not switch anything on just
because it was moved.**