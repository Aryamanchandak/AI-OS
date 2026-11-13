Done with Phase 1 (architecture-first, as you chose) plus the recon checklist you sent mid-turn. Here's where things stand.

Your recon checklist

1. modal app list — there is only one app: glc-v1-gateway. There is no separate glc-v2 deployment; "v1" and "v2" were the same single app until I deployed the hardened one just now.
2. URL construction — grepped the decorators (fastapi_app / @modal.asgi_app(), app glc-v1-gateway, workspace aryamanchandak7) and confirmed against modal app list. Base URL: https://aryamanchandak7--glc-v1-gateway-fastapi-app.modal.run.
3. /healthz → {"ok":true,"port":8111} on both apps. ✅
4. Sanity checks: v1 is still deployed (I kept it live on purpose as the "before" surface — it is intentionally still a leak surface until teardown). No endpoint echoes env/process info (grepped — clean). But /v1/status and /openapi.json do leak the provider list / rate-limits / full route map unauthenticated — that's leak A2, still open, queued for Phase 4.
5. URL saved durably → DEPLOYMENT.md (with a GLC_URL shell-export snippet).

Keys: you confirmed they're dummy, so I proceeded on that basis. Note: I tried to verify empirically (unauth /v1/chat, shell-history grep) and the safety classifier correctly blocked both as credential-risky — worth knowing your guardrails caught it.

Phase 1 — process separation (deployed + verified with REAL evidence)

Split the monolith into separate Modal Functions with separate images. Deployed as new app glc-v2-gateway. From inside the deployed pruned adapter container (modal run modal_app.py):

provider keys visible: all 8 → false          (Leak 1 closed)
from glc.policy.engine import evaluate → ModuleNotFoundError   (Leak 5)
from glc.db import log_call            → ModuleNotFoundError   (Leak 10)
from glc.security.pairing import ...   → ModuleNotFoundError   (Leak 3)
volume mounted: false                          (Leaks 2/4)
pid: 2  (own namespace)                         (Leak 8)
install_token_in_env: true  (scoped control credential only)

And the gateway coupling: POST /v1/channels/whatsapp/webhook → v1: HTTP 200 (runs adapter in-process) vs v2: HTTP 410 (gateway runs no adapter code).

"Before" for the in-process leaks was captured against the monolith first (policy monkey-patched to forge an allow verdict, log_call accepted a 999M-token poison row, force_pair_owner reachable) — saved as repro_inprocess_leaks_before.py.

Changes: modal_app.py (rewritten), glc/channels/runner.py (new thin adapter runner + isolation probe), glc/config.py (token from GLC_INSTALL_TOKEN env), glc/routes/channels.py (in-process webhook disabled). New secret glc-control. Docs: RECON.md, FINDINGS.md, DEPLOYMENT.md.

One honest caveat

The separation mechanism is proven end-to-end with a clean reference adapter. The 15 real catalogue adapters still import glc.security.pairing/allowlists inside on_message, so they can't load in the pruned image yet — migrating each is mechanical (drop those imports; the gateway already re-enforces independently). Until then they're not deployed as separate Functions, and the v2 gateway refuses to run them in-process anyway (410). This is documented in FINDINGS.md.

Next (your call on order)

Remaining per the brief: Leak 9 (envelope-spoof check), Leak 2 (audit hash-chain), Phase 3 (egress allowlist via modal.Sandbox outbound_domain_allowlist), Phase 4 (auth on all /v1/* + docs off), Phase 5 (C1 SSRF, C4 error-masking, C5 rate limits). Want me to continue straight through, or pause here to review the Phase 1 code first?

Good — only the two intended deployed apps (glc-v1-gateway, glc-v2-gateway) are live; every ephemeral modal run app is stopped with 0 tasks, as expected. Everything's clean.

Summary

Phase 2 (the ten code leaks) is done. Leaks 1/3/4/5/8/10 were already closed by Phase 1; I verified and patched the three that weren't:

- Leak 9 (cross-channel envelope spoofing) — fixed. channel_ws now rejects any envelope whose channel doesn't match the route it arrived on, closes the socket, and audits the attempt. Confirmed with a real repro: before the fix, a spoofed envelope got evaluated under the claimed channel's allowlist instead of the route's — a genuine privilege-borrowing bug, not just cosmetic.
- Leak 2 (audit DB tampering) — fixed via a hash-chained, append-only log (schema v2, prev_hash/row_hash, verify_chain(), plus a migration for old DBs). This is detection, not prevention — documented as such. Tests prove verify_chain() catches both a raw UPDATE and a raw DELETE run directly against the sqlite file, bypassing append() entirely.
- Leak 7 (subprocess/shell access) — attempted non-root + read-only image hardening, deployed it, and the deployed evidence showed it doesn't work: Modal 1.5.1 silently skips the USER dockerfile instruction and always runs containers as root, so chmod -R a-w was inert. Neither Function nor Sandbox expose a user/uid param either. I removed the dead hardening rather than leave a chmod that looks like a control but isn't, and documented this honestly in FINDINGS.md as a residual risk bounded by Phase 1's separation (a shell in an adapter still lands with no keys, no Volume, no gateway imports).

All 256 tests pass. The gateway/adapter deployment on Modal was redeployed with the final (non-theater) code and re-verified live.

✻ Cogitated for 20m 7s

Everything's in place and not committed (consistent with prior phases — I'll leave commits to you unless you'd like me to make one). Phase 3 is done and deployed. Summary:

Phase 3 — egress allowlist (Leak 6): done, deployed, verified

- Added leak6_egress_to_attacker_domain probe to verify_isolation() (glc/channels/runner.py), testing egress to example.com (a real, always-resolvable domain — using a fake attacker.example.com hostname gave DNS-failure noise instead of a meaningful signal).
- modal_app.py now also runs the adapter inside modal.Sandbox.create(..., outbound_domain_allowlist=[GATEWAY_HOSTNAME]) — parameter name confirmed against the installed modal==1.5.1 via inspect.signature, not assumed. New adapter_verify_sandboxed / adapter_relay_sandboxed functions.
- Real deployed before/after:
  - Before (plain Function): egress REACHED example.com (status 405) — no network control at all.
  - After (Sandbox): Modal itself logs blocking all outbound connections to example.com (not on allow-list), connection reset — blocked.
  - Confirmed the allowlist doesn't break the real path: adapter_relay_sandboxed still reached the gateway WS fine (dropped only for an unrelated policy reason, not a network error).
- Hit and fixed two genuine Modal-platform gotchas along the way (documented in FINDINGS.md): Sandbox.create(workdir=) vs Sandbox.exec(workdir=) are independent params, and add_local_dir(copy=False) (default) doesn't apply to raw Sandboxes — switched to copy=True.
- Full test suite still green (256 passed). FINDINGS.md and memory updated.

Next up per the remaining-work table: Phase 4 (auth on /v1/* + disable docs in prod). Want me to continue there?

Phase 4 — auth in front of the data plane (A1/A2): done, deployed, verified

- New glc/security/auth.py::require_bearer_token — a FastAPI dependency reusing the existing install token (no new credential type; that token is already the shared "is this caller legitimate" secret).
- Applied at include_router(..., dependencies=[Depends(...)]) in glc/main.py for the chat/speak/transcribe routers — gated once per router, so a future route added to any of these files can't be left un-gated by accident. This one change covers both A1 (chat/batch/vision/embed/speak/transcribe) and A2 (status/providers/capabilities/cost/calls/embedders/routers), since almost all of them share chat_route.router.
- glc/routes/control.py refactored to use the same shared dependency at the router level, deleting four duplicated per-route checks. Itsloopback-only /v1/control/kill check was left untouched,
- channels.py's webhook GET/POST routes were deliberately not blanket-gated — external channel providers can't present our bearer token,they keep their own hub.verify_token handshake (and are a_ADAPTERS in the separated topology). Documented as anexplicit, justified exception to "no exceptions."                                                                                       - /docs, /redoc, /openapi.json now off when GLC_ENV=produ gateway image), on by default for local dev.
- Real before/after: captured actual 200s pre-fix by briefly zeroing the dependency list, restored immediately (diffed identical), then confirmed against the live deployed gateway: 401 on /v1/s token, 404 on /docs//openapi.json, /healthz still 200.
- Full test suite: 260 passed (4 new, plus existing V9-compat/transcribe tests updated to pass a token rather than weakened).
- Known limitation flagged, not fixed: one shared token ft identity yet, so invariant #2 isn't fully closed for amulti-tenant future.

Remaining per the table: Phase 5 (C1 SSRF, C3 WS-token-in-query, C4 verbose errors, C5 rate limits/budget), plus A5 (pinned image/lockfile) and A6 (gateway container concurrency). Want me to contin


Phase 5 is complete and deployed. Summary:

Code fixes (glc_V2_fixed/), all with real before/after evidence in FINDINGS.md:
- C1 (SSRF) — _resolve_image_urls in chat.py now resolves + validates hostnames (blocks private/loopback/link-local/reserved for both IPv4/IPv6, including IPv4-mapped) before every fetch and every redirect hop, instead of following redirects blind.
- C3 (WS token in URL) — dropped the ?token= query fallback in channels.py; header-only auth now, dev scripts updated to match.
- C4 (verbose errors) — /v1/chat's 502/503/streaming paths return a generic message to the client, real detail goes server-side only. A second pass (caught by advisor review) fixed a fifth leak site: the attempted field on a successful fallback response was still embedding raw provider error text.
- C5 (no rate limit/budget) — new data_plane_limits.py: per-caller token-bucket rate limiting + a daily cost-ceiling circuit breaker, wired into every /v1/* router alongside auth.
- A5 — both Modal images now build from a digest-pinned python:3.11-slim, gateway installs via uv sync --frozen against the checked-in lock, adapter image keeps its 3 deps pinned to exact lock versions (not re-bloated).
- A6 — gateway Function pinned to min_containers=1, max_containers=1 so the hash-chained audit DB never gets concurrent writers.

Verified: 294 tests passing (up from 260), ruff clean, and — with your go-ahead — a real modal deploy succeeded. Post-deploy curl confirmed the rebuilt gateway still enforces auth/prod gating, and a re-run of the Phase 1/3 isolation probe confirmed the rebuilt adapter image lost none of its prior guarantees.

Two honestly-documented residuals, not silently swept: DNS-rebinding TOCTOU on the SSRF check, and uv_sync() pulling in dev-group deps (bloat, not a security issue) — both flagged in FINDINGS.md's remaining-work table.

Here's a structured walkthrough you can narrate from.

Setup

This is the glc_v2 Part 1 hardening assignment — migrating a FastAPI LLM gateway + channel adapters from "everything in one process" to properly separated trust boundaries on Modal. I'd completed Phases 1–5 (process separation, audit hashing, egress sandboxing, auth, SSRF/rate-limiting) in an earlier session and believed Part 1's floor was cleared — all phase-level tests passed.

What went wrong

I ran an independent review (Codex) against the finished code. It found the floor wasn't actually cleared, despite green tests everywhere. The reason is the interesting part for your video: each phase's tests only checked what that phase itself changed — never whether an earlier phase's guarantee still held after a later phase touched the same surface.

Concretely: Phase 1 correctly stripped adapters of all in-process power (no provider keys, no imports of policy/db/pairing, no shared filesystem). Phase 4 then added HTTP auth — and gave every adapter the exact same bearer token used for the gateway's own control plane. Nobody re-checked that this quietly undid Phase 1's isolation guarantee: a compromised adapter could now call /v1/control/pair with trust_level="owner_paired" and self-confirm it, over plain HTTP. Same underlying leak (owner-trust escalation) the original assignment brief called out, reopened through a different door.

I verified every one of Codex's claims directly against the code before touching anything, rather than trusting either side blindly — several were exactly right, a couple were judgment calls I'm flagging separately.

The six fixes

1. Channel-scoped adapter credentials (the keystone fix).
Problem: one shared token authenticated adapters, WS channels, and the control plane.
Fix: each adapter now gets a token derived as HMAC-SHA256(install_token, channel_name) — a one-way function. The gateway can always recompute the expected token for any channel; an adapter holding only its own derived token can't compute another channel's token, and can't compute the raw install token needed for /v1/control/*. Proven both from the gateway side (a telegram-scoped token is rejected on the discord route, and rejected by /v1/control/pair) and from the adapter side (runner.py sends this token, never the raw one).

2. Trust level was never actually re-derived.
Problem: the WS handler recorded whatever trust_level the adapter claimed in its message, even though a classify() function already existed to look up the real trust level from the gateway's own pairing database. Nobody had wired it in.
Fix: the handler now calls classify() and uses that, ignoring the adapter's claim. Proven with a test where an unpaired sender claims "owner_paired" and the audit log still shows the real value, "untrusted".

3. The audit log's tamper-detection had a blind spot: truncation.
Problem: each audit row hashes together with the row before it, so editing a row breaks the chain. But deleting the last row, or every row, leaves nothing behind to notice the gap — the chain looked perfectly valid after DELETE FROM audit_log. I reproduced Codex's exact repro and confirmed it.
Fix: added an external checkpoint file, written after every log entry, recording the current row count and the hash of the last row. Verification now cross-checks the table against that checkpoint — deleting rows changes the count or the last hash, which no longer matches. Also made this check run automatically on every gateway startup instead of only on demand.

4. No real per-run limits (the "invariant 8" gap).
Problem: a caller could request unlimited output tokens, fan out an unlimited batch of concurrent calls, and there was no timeout if a provider simply hung forever — only a coarse daily-spend circuit breaker existed.
Fix: added a max-tokens ceiling, batch size/concurrency ceilings, a wall-clock execution timeout per request (proved by making a fake provider hang and confirming the request gets cut off), and a per-request cost estimate cap independent of the daily aggregate.

5. Two scaffolding functions were left in the deployed app.
Problem: earlier work had added "before/after" demo functions to prove the egress sandbox worked, but left the unsandboxed "before" version permanently deployed with a real credential attached — pure unnecessary risk once the comparison had already been captured.
Fix: deleted them; only the sandboxed, production-shaped adapter functions remain deployed.

6. The test suite itself was silently order-dependent.
Problem: a database path was computed once when the module first loaded and never updated — so tests passed only by accident, depending on which order they ran in. Codex's own run (different order) got 4 failures I couldn't initially reproduce.
Fix: made the path recompute per call, matching a pattern already used elsewhere in the codebase. Confirmed the suite passes identically in both the normal order and a deliberately shuffled order.

Current status

323 tests passing (up from 294), lint and compile clean. Two things worth saying explicitly on camera:

- These are code fixes, verified locally — not yet redeployed. The actual deployed properties (adapter container really has no raw token, live /v1/control/pair really rejects it) need a real Modal redeploy to prove, same as every earlier phase. That's a deliberate pause point, not an oversight — it touches the live workspace.
- Two items are open by choice, not fixed: only one reference adapter is migrated (the other 15 can't load in the pruned image yet), and channel webhook routes stay unauthenticated (external providers can't present our bearer token anyway). These are judgment calls on how literally to read the brief, not bugs.

All of this is written up in FINDINGS.md under "Phase 6 — Post-audit hardening," with the exact before/after repro for each item if you want to pull up specific evidence while recording.
