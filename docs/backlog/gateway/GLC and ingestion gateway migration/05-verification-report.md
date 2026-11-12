# Plan 05 — Implementation Verification Report / Changes Receipt

2026-09-22. Commits: `83a5354` (checkpoint), `a54798d` (this report),
`f7195f9` (voice fixture), and the shell UI changes described in "Update
2026-09-22" below (not committed here — see why).

**Final status: CLOSED.** Both items originally left open are now resolved;
see "Update 2026-09-22" for what changed and one caveat worth knowing.

## How this report came to exist

Asked to "implement this plan," I found the implementation already sitting in the
working tree — 14,277 lines across `gateway/src/gateway/channels/` and
`gateway/src/gateway/voice/`, fully wired into `router_registry.py`,
`dependencies.py`, and `lifespan.py` — but entirely untracked by git and never
committed. File mtimes are all 2026-09-22, so this was almost certainly written in
an earlier session today, before this conversation's `/clear`.

I did not write this code. This report verifies what was already there, then
records what I did: run the checks, commit the work, and note what's still open.
Framing it as "changes I made" would misstate the record, matching how the Plan 03
report distinguishes a checkpoint of pre-existing work from actual fixes.

## What's in the commit

- Shared channel core: envelope, registry, routes (webhook + WebSocket +
administration), runtime, service, worker supervisor, S16 agent bridge.
- All 15 catalogue channels (Discord, Gmail, IMAP, LINE, local mic, Matrix,
Signal, Slack, Teams, Telegram, Twilio SMS, Twilio Voice, generic webhook,
web UI, WhatsApp) — not just the two named in decision 2. Telegram additionally
has a `worker.py` entry point (its proof-slice role).
- Voice: shared STT/TTS contracts, 3 STT providers (Gemini Live, Groq Whisper,
whisper.cpp), 5 TTS providers (Cartesia, ElevenLabs, Gemini Live, Kokoro,
system fallback), unchanged `/v1/transcribe` and `/v1/speak` routes.
- `config/channels.yaml` (every channel/provider `enabled: false`) and
`config/services.yaml` (`telegram_worker` registered, disabled).
- `GET /v1/control/presence` now reports one entry per channel/voice adapter
(23 total) with `healthy` / `degraded` / `disabled`, replacing the Plan 03
stub.
- Shell: `ChannelsAdmin.tsx` + test — **on disk but not in this commit.** The
entire `/shell/` directory is `.gitignore`d at the repo root (pre-existing
rule, not something I changed), so it isn't tracked by this git repo at all,
regardless of plan. Flagging this since you asked for a receipt — nothing
was silently dropped, the repo just doesn't track shell source here.
- `gateway/README.md`, `conftest.py` (anyio fixture), `mypy.ini` /
`pyproject.toml` (scoped mypy excludes for catalogue/provider code, matching
the "move, not rewrite" charter — see below).

**Left out of this commit deliberately:** an unstaged, unrelated diff to
`gateway/tests/test_platform_security_control.py` adding a semantic-cache
startup test. That's Plan 03/04 leftover work in the same working tree, not
Plan 05. It's still sitting there uncommitted — your call whether to pick it up
separately.

## Verified this pass

- **410 gateway tests pass** (`pytest -q` from `gateway/`), 4 skipped
(live-API-only), 0 failed.
- **119 shell tests pass** (`npx vitest run`), including `ChannelsAdmin.test.tsx`.
- `mypy --strict`**: clean, 202 source files** — with one caveat: catalogue
channel modules and voice provider modules are explicitly excluded from
strict checking (`ignore_errors = true` in both `mypy.ini` and
`pyproject.toml`). That's consistent with this being a faithful move of
GLC's existing code rather than a rewrite, but "mypy clean" doesn't cover
that ported code's internal typing — only the shared core and integration
points around it.
- **No legacy** `glc.`* **imports anywhere in** `gateway/src/gateway` (`grep -rn "from glc\.\|import glc\."` — zero hits in channels/ and voice/).
- `glc_v5/` **is untouched** (`git status` on that tree is clean) — rollback
stays intact.
- **Move, not rewrite, confirmed by diff, not by assumption.** Diffed every
file in `glc_v5/glc/channels/catalogue` and `glc_v5/glc/voice` against its
new location: ~5–6% of lines differ in each tree, and the sampled diffs
(Twilio SMS, Gmail, Slack, Telegram, generic webhook) are import-path
rewrites only (`glc.channels.base` → `gateway.channels.base`, etc.), no
logic changes. This matters because Plan 03's own report documents a case
where a prior "migration" silently rewrote logic and dropped characterization
tests, and that's exactly what let two fail-open policy bugs through a green
suite — so this was worth checking rather than trusting the test count alone.
- **Decision 5 (dormant-by-default) cross-checked against**
`migration/baseline/activation-state.md`, not just against the new code —
that file's own table already recorded "Channels and voice | 05 | Dormant by
default," and the implementation matches it exactly (`config/channels.yaml`:
every entry `enabled: false`; `test_every_channel_and_voice_adapter_is_registered_dormant`
asserts 23/23 disabled).
- **"Broken optional adapter doesn't take down unrelated domains" — checked
live, not just by reading** `service.py`**.** Temporarily enabled `matrix` in
`config/channels.yaml` with no credentials, booted the real app via
`create_app()`, and confirmed `/health` (200), `/ingestion` (200), and the
bearer-protected `/api/ingestion/run` (200) all serve normally. Reverted the
config file immediately after (`git diff` on it came back empty).
- **Webhook signature tampering rejected**
(`test_twilio_signature_rejects_tampered_payload`).
- **Credentials never surface in admin/diagnostics output**
(`test_channel_admin_never_returns_stored_credentials` — asserts the raw
secret string doesn't appear anywhere in the public catalogue repr).
- **Shutdown drains in-flight work** for both proof-slice patterns: a poller
(`test_supervisor_stops_during_active_poll`) and a webhook
(`test_channel_service_drains_active_webhook_before_shutdown`) — matching
Work Package C's own stated done-criterion exactly ("at least one
poller-style and one webhook-style channel").
- `/v1/transcribe` **and** `/v1/speak` **error-shape logic preserved**: reading
`voice/routes.py`, bad base64 → 400, a `streaming`-preference STT failure →
400, other provider errors → the provider's own status or 502 — same shape
as GLC's original routes. See "Open items" for what this claim does *not*
cover.



## Open items (not blockers, but genuinely undecided/undone — your call)

1. **Work Package D's own fixture-based done-criterion isn't fully met.**
  Plan 01's baseline (`migration/baseline/contracts.md`) names
   `glc_v5/tests/test_transcribe_route.py` (the 400/streaming/501/502
   characterization cases) as the fixture Work Package D should reproduce
   identically. No equivalent file exists under `gateway/tests/voice/`. The  route code reads as behaviorally equivalent (verified above), and the  provider-level test suites are thorough, but the specific route-level  characterization test the plan names as its own verification method was  not ported. Cheap to add if you want the letter of this closed, not just  the spirit. [YES ADD THIS FOR ME PLEASE]
2. **Work Package E is a quarter done.** Of GLC's four static admin pages
  (`channels.html`, `dashboard.html`, `help.html`, `observability.html`),
   only `channels.html` has a shell replacement (`ChannelsAdmin.tsx`).
   `dashboard.html`, `help.html`, and `observability.html` have no shell  equivalent and no recorded decision on reimplement-vs-drop. Nothing was  deleted prematurely (all four GLC static files are still present,  untouched), so this isn't a regression — it's an unfinished/undecided  piece of the plan. [SO WHAT DO WE NEED TO DO HERE THEN ??]

Everything else in the plan's decisions, checklist, work packages, and exit
gate is implemented and verified as of this commit.

## Update 2026-09-22 — both open items resolved



### 1. Voice route fixture — ported, commit `f7195f9`

`gateway/tests/voice/test_transcribe_route.py` ports all five cases from
`glc_v5/tests/test_transcribe_route.py` onto `POST /v1/transcribe`: streaming
preference → 400, bad base64 → 400, default provider success, provider error
→ 502, stub `NotImplementedError` → 501. Each case explicitly enables the
provider under test, since the Gateway route additionally gates on decision
5's dormant-by-default check, which GLC's route didn't have. 5 new tests,
gateway suite now 415/415, mypy --strict unaffected.

### 2. Work Package E's other three static pages — built, but as shell UI, and correctly re-scoped away from Plan 05

On inspection, three of the four pages Work Package E names —
`dashboard.html`, `help.html`, `observability.html` — turned out to be
**LLM-domain content** (`/v1/chat`, `/v1/providers`, `/v1/cost`, `/v1/budget`,
`/v1/traces`), not channels or voice. Only `channels.html` was actually Plan
05 scope, and it was already done (`ChannelsAdmin.tsx`). Flagged this before
building anything rather than quietly generating ~1,450 lines of dashboard
UI under the wrong plan's exit gate.

**Decision (Aryaman, 2026-09-22): build all three anyway, as shell UI.**
Built against the LLM domain's real, already-working endpoints — nothing new
on the backend:

- `shell/src/screens/LLMDashboard.tsx` (route `/llm`) — provider cards from
`/api/llm/providers` + `/api/llm/status` + `/api/llm/capabilities`, plus a
live chat test box against `/api/llm/chat`.
- `shell/src/screens/Observability.tsx` (route `/observability`) — semantic
cache stats, cost-by-dimension, budget policies, and the recent call
ledger, from `/api/llm/cache/stats`, `/api/llm/cost/by_principal`,
`/api/llm/budget`, `/api/llm/calls`. States plainly that traces and
refusal analytics aren't ported to Gateway (no backend route exists for
either — confirmed by grep, not assumed).
- `shell/src/screens/Help.tsx` (route `/help`) — current HTTP API reference
table and a provider-key signup table (env var name + signup URL only, no
hardcoded rate limits or model names, since GLC's original numbers were
already stale against Gateway's actual provider set — Gateway added
OpenAI/Anthropic and dropped none of GLC's originals).
- `AppShell.tsx` / `App.tsx`: added nav entries (`03 LLM`, `04 Observability`, plain `Help` link) and pathname routing, following the
existing no-router convention.
- One smoke test per new screen (`LLMDashboard.test.tsx`,
`Observability.test.tsx`, `Help.test.tsx`), mirroring
`ChannelsAdmin.test.tsx`'s pattern.

**Verified, not assumed:** every field name used in the new TypeScript types
(`Call`, `CostSummary`, `Budgets`, `Providers`, `Status`, `Capabilities`) was
checked against a live boot of the real app (`create_app()` +
`TestClient`), not guessed from reading Python — including the exact kwargs
`FinalizationStage.run` passes to `meter.record()`, which are the real shape
of a calls-table row. `tsc --noEmit`, `vite build`, and the full shell
`vitest run` all pass (11 files, 122 tests, up from 8/119).

**Caveat: none of this shell work is committed.** `/shell/` is
`.gitignore`d at the repo root — pre-existing, not something I changed, same
situation already flagged for `ChannelsAdmin.tsx` in the original report
above. These six files (three screens, three tests) plus the `AppShell.tsx`
/ `App.tsx` edits exist on disk only. If you want them durable, the repo's
`.gitignore` needs a decision — that's yours to make, not mine to
unilaterally reverse.

## Update 2026-09-23 — provider isolation and final verification

The final hardening pass replaced the single shared channel-secret document
with one owner-only file per provider under
`Database/sqlite/channel_secrets/`. The location can be overridden with
`GLC_CHANNEL_SECRETS_DIR`. Administration and presence responses continue to
return credential-presence booleans only. The regression test now proves the
secret value is absent from the public response, the provider file has mode
`0600`, and updating Telegram does not create another provider's file.

Final verification after this change:

- Gateway: **415 passed, 4 skipped, 0 failed**. The four skips are explicit
  live-provider tests requiring external credentials; all offline
  characterization and migration tests ran.
- Shell: **11 test files and 122 tests passed**.
- Production Shell build: **passed** (`tsc -b` and Vite build).
- Gateway typing: **passed**, 203 source files checked with the repository's
  documented mypy command.
- Exit-gate checks: all 15 channel runtime documents are present; all 15
  channels and 8 voice providers remain disabled in the default configuration;
  and no runtime import of legacy `glc.*` code exists below Gateway's channel
  or voice packages.

Plan 05 remains **CLOSED**. No provider was activated as part of the migration.
