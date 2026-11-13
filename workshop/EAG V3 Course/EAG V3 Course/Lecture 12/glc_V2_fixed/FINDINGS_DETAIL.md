# FINDINGS.md — glc_v2 Part 1 Hardening

Reference deployments:
- **v1 monolith (before):** `https://aryamanchandak7--glc-v1-gateway-fastapi-app.modal.run`
  (left live on purpose as the "before" surface).
- **v2 separated (after):** `https://aryamanchandak7--glc-v2-gateway-fastapi-app.modal.run`
  (gateway) + `adapter_verify` / `adapter_relay` Functions in the pruned adapter image.

Keys confirmed dummy by the user. See `RECON.md` for Phase 0.

**How the evidence in this document was produced (stated up front, because the
assignment's step 2 asks for a specific method).** Step 2 says to reproduce every
Section 6/7 finding *against your own deployment*, by running the exploit
console's gateway curl in a terminal and the in-process snippets in the two-file
harness. That is how the "before" side was captured: the 18 curls and snippets in
`../6_7_2_findings.md` were run against a live Modal deployment of this gateway,
and the in-process leaks (policy monkey-patch, forged `log_call` row, reachable
`force_pair_owner`) were captured against the monolith in
`repro_inprocess_leaks_before.py`. Two honest caveats on the "after" side:

- The captured curl transcripts in `../6_7_2_findings.md` carry the
  `admin-14505--glc-v1-…` hostname rather than this workspace's
  `aryamanchandak7--glc-v1-…` URL. The findings were confirmed against the
  workspace's own deployment (see `RECON.md`'s Phase-0 live confirmations and
  Phase 4's post-deploy curls), but the transcripts as pasted are from the
  session's console, not this account.
- Phases 6 and 7 are **code-only**: the live v2 deployment predates them, so the
  "after" evidence for those phases is behavioural-but-local (FastAPI
  `TestClient` + the full pytest suite) rather than a live curl. This is a
  deliberate substitution, not an oversight — a redeploy is a production action
  awaiting go-ahead. The structural findings (8, 11, 13, 14, 15, 16, 18) are
  config-verified by design; the last section of `../6_7_2_findings.md` explains
  why that is the only possible proof for that class, not a weaker one.

## Status legend
- ✅ done + verified (real before/after captured)
- 🟡 partially closed / mechanism proven, migration of all adapters pending
- ⬜ not started (later phase)

---

## Master finding table — every Session 12 Section 6 (groups A, C) + Section 7 finding

Per `ASSIGNMENT.md`'s deliverable: *"a FINDINGS.md that lists each finding, the
invariant it broke, and your fix."* This table is that list, in one place, for
all 18 findings the assignment requires (curled/repro'd against the live
deployment and captured in `../6_7_2_findings.md`). Detailed narrative,
before/after evidence, and residual-risk discussion for each row lives in the
phase section linked from the "Detail" column — this table exists so a grader
doesn't have to read 900 lines to find the invariant citation for a given
finding.

**Invariant wording is quoted verbatim from Section 4** (see `RECON.md`'s
"Invariant 1" .. "Invariant 8" headers, the only place in this repo the 8 are
written out in full). Where a finding is genuinely a stretch against the 8 —
several of Section 6's findings are general access-control/hygiene issues
rather than agent-tool-safety issues the 8 invariants were written for — that
is stated plainly rather than force-fit, per the project's own standard of not
claiming a fix that isn't real.

**Attacker roles are quoted verbatim from Section 4** (`RECON.md:104-107`, the
only place in this repo the ladder is written out), weakest to strongest:

1. **Outsider on public internet, no credentials**
2. **Normal channel user, controls only the text they type**
3. **Attacker who has taken over a single adapter container**
4. **Attacker with code execution inside the gateway process itself**

The "Attacker role" column below is the role that reaches the finding **as it
stood in the unhardened build** — i.e. against the v1 monolith the recon curls
hit, where the data plane was unauthenticated and adapters shared the gateway's
process, Secret, and Volume. Where hardening has since raised the bar (a leak
that was role 3 in the monolith is now only reachable at role 4 inside the
gateway process), both are given as `3 → residual 4`. Three findings are
honestly **not** attacker-reachable on this ladder — #17 needs an upstream
supply-chain actor who sits outside roles 1–4 entirely, #18 is triggered by the
platform's own autoscaling with no attacker at all, and #7 never broke — and
are marked as such rather than assigned a role to make the column look complete.

| # | Finding (as curled/repro'd) | Section | Invariant broken | Attacker role | Fix (one line) | Status | Detail |
|---|---|---|---|---|---|---|---|
| 1 | `/openapi.json` + `/docs` publicly readable — hands an attacker the full route/schema map | 6·A | *No clean 1–8 match.* Closest in spirit: Inv 2 (every action must be checked against the actual user) — there is no "actual user" check possible before any auth layer exists at all. Mainly a recon/attack-surface-mapping enabler, not itself an invariant violation. | **1** — any outsider; the route map is served to unauthenticated callers | `GLC_ENV=production` sets `docs_url=None, openapi_url=None` | ✅ | Phase 4 |
| 2 | `/v1/status` unauthenticated — leaks provider order, rpm/rpd limits, models | 6·A | **Inv 2** — served to any caller with no check of who they are | **1** — no credential of any kind needed to read provider config | `require_bearer_token` at router `include_router()` | ✅ | Phase 4 |
| 3 | `/v1/chat` unauthenticated — a real (billable) LLM call executed for any caller | 6·A | **Inv 2** — clearest case: an action with real cost/side-effects, executed with zero identity check | **1** — an anonymous outsider executes a real, billable LLM call | `require_bearer_token` | ✅ | Phase 4 |
| 4 | SSRF via `image_url` — gateway fetches attacker-supplied URL server-side (loopback/private/link-local/metadata) | 6·C | **Inv 3** — the URL string is external content; fetching it is treating that content as an instruction to act (make a network call), not as inert data | **1** — pre-auth, any outsider chose the URL the gateway fetched; post-Phase-4, any data-plane token holder | v4+v6 private-range block, per-hop redirect recheck, opt-in `GLC_IMAGE_HOST_ALLOWLIST` | 🟡 | Phase 5 + Phase 7 addendum (DNS-rebind TOCTOU is a documented, evidence-backed residual — see recon addendum) |
| 5 | Verbose upstream error (`"gemini HTTP 400: ..."`) returned to the client | 6·C | *No clean 1–8 match.* This is OWASP-A09-style information-disclosure hygiene (server internals in a client-facing error), not one of the 8 agent-safety invariants. Fixed regardless of the mapping gap. | **1** — the error body is returned to whoever called, credential-free | Fixed generic client string; real detail to server logs + `db.log_call` only | ✅ | Phase 5 |
| 6 | `/v1/cost/by_agent` unauthenticated, and (per the recon fix text) not scoped to the requesting tenant | 6·A | **Inv 2** (auth half) + **Inv 5**, "each tenant must have separate memory" (scoping half) | **1** — anonymous read of cost/usage; the unclosed scoping half is reachable by any token holder | `require_bearer_token` closes the auth half. Tenant scoping is **not** closed — one shared install token = no per-caller identity to scope against; this needs new identity infrastructure, out of Part 1's scope, not patched with a fake filter | 🟡 half — auth ✅, scoping ⬜ | Phase 4 + Phase 7 addendum |
| 7 | `/v1/control/presence` already required the token | 6·A | Inv 2 (already held — nothing broke) | *n/a — nothing broke.* Correctly rejects roles 1 and 2 already; used as the baseline | n/a, used as the "what right looks like" baseline in the recon | ✅ (baseline, not a fix) | — |
| 8 | Adapter process reads every provider API key from shared env | 7·Leak 1 | **Inv 1** (exact — "Adapters must never see provider API keys") | **3** — adapter takeover; shared process env hands it every provider key. Closed for adapters; **role 4 holds these by design** (Inv 1 restricts *adapters*, and role 4 is not an adapter) — not a residual violation | Provider-key Secret mounted on the gateway Function only | ✅ | Phase 1, Leak-table row |
| 9 | `sqlite3... DELETE FROM audit_log` — audit table emptied with no trace | 7·Leak 2 | **Inv 7** (exact — "Components must not edit or delete their own audit logs") | **3** in the monolith (adapter shared the Volume) → **residual 4** only, post-separation | Hash chain + external checkpoint file; `verify_chain()` detects the truncation | ✅ | Phase 2 + Phase 6 item 3 |
| 10 | `force_pair_owner()` importable in-process — self-grants `owner_paired` | 7·Leak 3 | **Inv 2** (grants trust without checking the actual caller) + **Inv 4** ("a credential must work only for one specific tool call" — one shared token was doing the work of an owner-only bootstrap credential) | **3** in the monolith (adapter imports the module) → **residual 4**; no HTTP path at any role since Phase 7 | Process separation removes adapter import access (Phase 1); channel-scoped tokens removed HTTP reachability (Phase 6); `/v1/control/pair` now refuses `trust_level=owner_paired` outright, closing the last HTTP path even for a raw-token holder (Phase 7) | ✅ unreachable over HTTP or from an adapter; residual = still an importable function for code running **inside** the gateway process (process-boundary property, see Phase 7 addendum) | Phase 1/6/7 |
| 11 | Install token readable in-process (`~/.glc/install_token`) | 7·Leak 4 | **Inv 1** (same spirit, extended to the control-plane credential, not just provider keys) | **3** — adapter takeover reads the token off the shared Volume/env. Closed for adapters; **role 4 holds it by design** — not a residual violation | Token via gateway-only Secret; adapters hold a derived per-channel token instead (never the raw token) | ✅ | Phase 1 + Phase 6 item 1 |
| 12 | `glc.policy.engine.evaluate` monkeypatched — all policy decisions forced to `allow` | 7·Leak 5 | **Inv 6** ("dangerous/high-impact actions must be approved with their FINAL parameters" — a forged policy engine defeats approval entirely) | **3** in the monolith → **residual 4** only; unfixable in-process, hence capstone scope | Adapters cannot `import glc.policy` (not in the pruned image) — closes the *adapter-reachable* instance | ⬜ **not fixed for in-process gateway code, by design** — the recon file itself tags this "capstone scope"; no in-process guard can survive same-process code execution (any code that could rebind `evaluate` can also unwind a guard around it). Real fix is a separate policy process, explicitly out of Part 1 | Phase 7 addendum |
| 13 | `os.kill(os.getpid(), SIGTERM)` — adapter terminates the gateway | 7·Leak 8 | **Inv 8** ("every run has hard limits..." — availability is a precondition for any run limit to mean anything; an adjacent process ending the gateway ends every in-flight run unconditionally) | **3** — adapter takeover signals a PID it shares with the gateway. → residual **4** | Gateway and adapters are separate Modal Functions → separate PID namespaces | ✅ | Phase 1, Leak-table row |
| 14 | `glc.db.log_call(input_tokens=999999999, ...)` — forged ledger row | 7·Leak 10 | **Inv 8** (cost/limit ledger integrity is what the run-limit invariant is enforced against — a forgeable ledger defeats it) | **3** in the monolith (adapter imports `glc.db`) → **residual 4** | `db.py` excluded from the adapter image; only the gateway process can write the ledger | ✅ | Phase 1, Leak-table row |
| 15 | Single Function, no egress wall (A3) | 7·structural (Leak 6) | **Inv 3** (per existing Phase 3 tag — unrestricted egress lets adapter-reachable code exfiltrate to, or receive instructions from, arbitrary external hosts) | **3** — adapter takeover exfiltrates to any host on the internet | `modal.Sandbox(outbound_domain_allowlist=[gateway])` | ✅ | Phase 3 |
| 16 | One Secret for the whole Function (A4) | 7·structural | **Inv 1** (this is the architectural root cause of findings 8/11 — same invariant, at the config level) | **3** — structural root cause of #8/#11; same role reaches it. As with those, **role 4 holding the gateway's own secrets is by design** | Three secrets split along the trust boundary (provider keys / install token / per-channel token) | ✅ | Phase 1 + Phase 6, same fix as #8/#11 |
| 17 | Non-reproducible image (A5) | 7·structural | *No clean 1–8 match.* Supply-chain integrity (OWASP A06-style), not an agent-safety invariant. Fixed regardless. | *Outside roles 1–4* — needs an upstream supply-chain actor (a shifted or typosquatted dependency), not any of the four roles | Digest-pinned base image; `uv_sync()` against `uv.lock` (gateway), pinned exact versions (adapter) | ✅ | Phase 5 |
| 18 | Audit volume assumes one writer (A6) | 7·structural | **Inv 7** (concurrent writers corrupt/split the append-only hash chain — the same integrity property Leak 2/finding 9 protects) + **Inv 8** (identical concurrency risk on the cost ledger `db.py` shares) | *No attacker* — triggered by the platform's own autoscaling; a data-integrity risk, not an exploit path | `min_containers=1, max_containers=1` pins the gateway to one container | ✅ | Phase 5 |

**Two items found beyond this required list of 18** (not required for the Part-1
floor, documented here for completeness — see `../6_7_2_findings.md`'s "PART 1"
and "PART 2" resolution addenda for full writeups):

| # | Finding | Invariant broken | Attacker role | Fix | Where it counts |
|---|---|---|---|---|---|
| 19 | Non-http(s) image URL schemes (`file://`, `gopher://`) relayed to the provider verbatim, found while fixing #4 | **Inv 3** (same class as #4 — external content driving an unchecked action, here forwarded rather than fetched) | **1** — any data-plane caller (pre-Phase-4, an anonymous outsider) picks the scheme the provider then opens | Reject any image URL scheme that isn't `http(s)` or inline `data:` | Part 1 hardening bonus in this repo; not one of the required 18, and not filed as a PR — doesn't score Part 2 points as-is |
| 20 | Audit/cost/pairing SQLite paths never actually resolved onto the persistent Modal Volume — silently reset on every redeploy/recycle | **Inv 7** (audit durability) + **Inv 8** (cost-ledger durability) | *No attacker action required* — any redeploy, crash, or platform container-recycle wipes the history; a role-1 outsider benefits passively, since the evidence of anything they did is gone | Three modules now share `GLC_CONFIG_DIR` as a fallback instead of each hardcoding `~/.glc` | Genuine **Part 2 candidate** (found by the invariant sweep, not in Sections 6/7) — only scores its 100 points if filed as an actual pull request against `theschoolofai/glc_v2` with a from-fresh-checkout repro; not yet filed |

---

## Phase 1 — process separation (DONE, deployed)

The gateway and adapters now run as **separate Modal Functions with separate
images**. The gateway image has the full `glc` package + config/audit Volume +
`glc-control` (install token) + `glc-llm-keys` (provider keys). The adapter image
is a **pruned** copy that physically omits `glc/policy`, `glc/db.py`,
`glc/security/**`, and every provider module, mounts **no Volume**, and holds
**only** the install token. Real deployed proof, from inside the adapter
container (`modal run modal_app.py` → `adapter_verify`):

```json
{
  "leak1_provider_keys_visible": {"GEMINI_API_KEY": false, "NVIDIA_API_KEY": false,
    "GROQ_API_KEY": false, "CEREBRAS_API_KEY": false, "OPEN_ROUTER_API_KEY": false,
    "GITHUB_ACCESS_TOKEN": false, "CARTESIA_API_KEY": false, "ELEVENLABS_API_KEY": false},
  "leak5_policy_evaluate": "blocked: ModuleNotFoundError: No module named 'glc.policy'",
  "leak10_db_log_call":   "blocked: ModuleNotFoundError: No module named 'glc.db'",
  "leak3_force_pair_owner":"blocked: ModuleNotFoundError: No module named 'glc.security'",
  "leak2_4_volume_mounted": false,
  "install_token_in_env": true,
  "pid": 2
}
```

| Finding | Invariant broken | Attacker role | Fix summary | Repro before | Repro after |
|---|---|---|---|---|---|
| **Leak 1** — shared process env exposes every provider key | #1 | adapter takeover (role 3) | Provider keys live only in `glc-llm-keys`, mounted **only** on the gateway Function. Adapter image mounts `glc-control` only. | Monolith: `os.environ.get('GEMINI_API_KEY')` → `<present>` (repro_before.py) | Deployed adapter: all 8 provider keys → `false` (adapter_verify) |
| **Leak 2** — audit DB writable at OS layer | #7 | in-gateway code (role 4) / adapter takeover (role 3) | Volume mounted **only** on the gateway; adapters have no filesystem access to `~/.glc`. (Hash-chain of the audit rows = follow-up, see below.) | Monolith path `~/.glc/audit.sqlite` reachable in-process | Deployed adapter: `leak2_4_volume_mounted` → `false` |
| **Leak 3** — pairing escalation via `force_pair_owner()` | #2, #5 | adapter takeover (role 3) | Adapters cannot import `glc.security.pairing` (not in image). | Monolith: `from glc.security.pairing import get_pairing_store` → OK, `force_pair_owner` present (repro_before.py) | Deployed adapter: `ModuleNotFoundError: No module named 'glc.security'` |
| **Leak 4** — install token readable in-process from Volume | #4 (control-plane) | adapter takeover (role 3) | Token comes from the `glc-control` Secret (env), never a Volume file the adapter can read; adapter has no Volume. Loopback-only `/v1/control/kill` check kept. | Monolith: `open('~/.glc/install_token').read()` works | Deployed adapter: no Volume; token only reaches the adapter as the scoped control credential |
| **Leak 5** — policy engine monkey-patch | #2, #3 | adapter takeover (role 3) | Adapters cannot import `glc.policy`; policy is evaluated only inside the gateway. | Monolith: patched `glc.policy.engine.evaluate` → forged verdict `action='allow' reason='pirate'` (repro_before.py) | Deployed adapter: `ModuleNotFoundError: No module named 'glc.policy'` |
| **Leak 8** — adapter kills the gateway via shared PID | #8 (availability) | adapter takeover (role 3) | Separate Modal Functions ⇒ separate PID namespaces. | Monolith: `os.kill(os.getpid(), SIGTERM)` = gateway PID | Deployed adapter: `pid` = `2`, a distinct namespace; killing it cannot touch the gateway |
| **Leak 10** — cost-ledger poisoning via `db.log_call` | #5, #8 | adapter takeover (role 3) | Adapters cannot import `glc.db`; only the gateway writes the ledger. | Monolith: `db.log_call(input_tokens=999_999_999,…)` inserted an unvalidated row (repro_before.py) | Deployed adapter: `ModuleNotFoundError: No module named 'glc.db'` |
| **Webhook coupling** — gateway ran adapter code in-process via `registry.instantiate` | #2, #3 | normal channel user (role 2) → adapter takeover (role 3) | v2 gateway sets `GLC_INPROC_ADAPTERS=0`; the in-gateway webhook handlers refuse to run adapter code (HTTP 410). Ingress must come from a separated adapter Function over the authenticated WS. | v1 monolith: `POST /v1/channels/whatsapp/webhook` → **HTTP 200** (adapter instantiated & run in the gateway) | v2 gateway: same request → **HTTP 410** |

### Honest scope note (🟡)
The **separation mechanism is built, deployed, and proven** with a clean
reference adapter (`glc/channels/runner.py::EchoIngressAdapter`) running in the
pruned image and relaying over `WS /v1/channels/{name}`. The 15 existing
catalogue adapters still import `glc.security.pairing` / `allowlists` /
`trust_level` inside `on_message`/`send` (duplicating enforcement the gateway
already does — the whatsapp adapter's own comment confirms "the gateway's own
independent `allowed()` re-check … is the actual enforcement point"). They
therefore cannot yet load in the pruned image. Migrating each is **mechanical**:
delete those imports, set `trust_level="untrusted"` and let the gateway
re-classify, then give the adapter its own scoped channel-token Secret. Until
migrated they are simply not deployed as adapter Functions — and the v2 gateway
refuses to run them in-process (410), so the coupling is closed at the gateway
regardless.

### Brief inconsistency resolved
The brief says the gateway Secret should hold "only control-plane values …
no provider keys," but the gateway must hold the provider keys to make provider
calls (invariant #1 = *adapters* never see them). Resolution used: gateway
mounts **both** `glc-control` (token) and `glc-llm-keys` (provider keys);
adapters mount `glc-control` **only**.

---

## Phase 2 — the ten code leaks: patches beyond process separation

Leaks 1/3/4/5/8/10 are closed by Phase 1 (process separation) alone and were
verified above with real deployed evidence. Three leaks need code beyond
separation; each was reproduced against the pre-fix code first, then fixed,
then re-reproduced to confirm the repro now fails/behaves safely.

### Leak 9 — cross-channel envelope spoofing (✅ fixed)

**Invariant broken:** #2 (every action checked against the *actual* user/
channel, not a claimed one). **Attacker role:** normal channel user's
message content is opaque to this, but anything that can reach
`WS /v1/channels/{name}` — a compromised adapter, or literally anyone who
has the shared install token, since the socket doesn't otherwise bind a
connection to a channel — could send a `ChannelMessage` whose `channel`
field doesn't match the route it's connected to.

Before the fix, `glc/routes/channels.py::channel_ws` validated the envelope's
*shape* but never checked `env.channel == name`. That's not just a cosmetic
mismatch: `allowed()` (the allowlist check right after) is looked up **by
`env.channel`**, so a message sent over `WS /v1/channels/webui` claiming
`channel="discord"` gets evaluated against `discord`'s allowlist/trust
config instead of `webui`'s — an attacker who controls one channel's adapter
can borrow a *different* channel's policy for their traffic.

- **Repro before** (real pytest run against the pre-fix handler, envelope
  claims `channel="discord"` while connected to `/v1/channels/webui`):
  ```
  FAILED tests/test_channel_envelope_spoofing.py::test_mismatched_envelope_channel_is_rejected_and_closed
  assert 'does not match route' in "dropped: channel 'discord' is disabled in channels.yaml"
  ```
  i.e. the message was evaluated under `discord`'s config, not `webui`'s — it
  happened to be dropped only because `discord` is disabled by default, not
  because the gateway noticed the spoof. Swap in a channel with a permissive
  allowlist and the message goes through.
- **Fix:** immediately after envelope validation, if `env.channel != name`:
  audit-log an `envelope_channel_mismatch` event (route channel + claimed
  channel), send an error frame, and **close the socket** — treated as a hard
  protocol violation, not a droppable single message, since it means
  whatever's on the other end of the socket isn't the adapter it claims to
  be.
- **Repro after:**
  `tests/test_channel_envelope_spoofing.py` — both tests pass: a mismatched
  envelope gets the `does not match route` error, the socket closes
  (`WebSocketDisconnect` on the next read), and the audit log has exactly one
  `envelope_channel_mismatch` row; a matching envelope still processes
  normally with no such row.

### Leak 2 — audit DB hash-chain (✅ fixed, detection not prevention)

**Invariant broken:** #7 (components must not edit/delete their own audit
logs). Phase 1 already closes *adapter* access to the audit DB (no Volume
mount). What it doesn't close: a bug, or a compromise, **inside the gateway
process itself** running `sqlite3.connect(path).execute("DELETE/UPDATE ...")`
— ordinary Python, no exploit, same as the original Leak 2 repro. Nothing at
the SQL layer can make a file *physically* unwritable to a process that has
the Volume mounted and the OS-level permission to write it; the fix is
therefore **detection**, not prevention, and is described that way rather
than oversold.

- **Fix:** `glc/audit/schema.sql` bumped to schema v2, adding `prev_hash` and
  `row_hash` columns. `AuditStore.append()` (`glc/audit/store.py`) now reads
  the previous row's `row_hash` and the new row's own fields inside a
  `BEGIN IMMEDIATE` transaction (so concurrent appends can't race onto a
  stale `prev_hash`), computes `row_hash = sha256(prev_hash || fields)`, and
  inserts both. A new `verify_chain()` walks the log in `id` order and
  recomputes the chain from scratch, returning the first row where it
  breaks. A migration (`_migrate_v1_to_v2`) upgrades a pre-existing v1
  database in place (adds the columns, backfills a valid chain over
  whatever rows already exist) rather than requiring a fresh DB.
- **Repro before / after**, all real pytest runs in `tests/test_audit_log.py`:
  - `test_hash_chain_detects_raw_sqlite_tamper` — appends 3 rows (chain
    verifies OK), then runs the *original Leak 2 exploit shape*
    (`sqlite3.connect(path).execute("UPDATE audit_log SET event_type='FORGED' WHERE id=?")`)
    directly against the file, bypassing `append()` entirely. Before this
    fix there was no way to notice this at all (that's the "before" — no
    detection existed, not a specific failing repro). After:
    `verify_chain()` returns `{"ok": False, "broken_at_id": <tampered_id>}`.
  - `test_hash_chain_detects_raw_sqlite_delete` — same shape as the original
    repro's `DELETE FROM audit_log`, targeting one row (the realistic
    "quietly remove one incriminating entry" case): `verify_chain()["ok"]`
    flips to `False`.
  - `test_v1_database_migrates_and_backfills_chain` — builds a raw v1-schema
    sqlite file (no hash columns), runs `init_store()`, confirms
    `schema_version() == 2` and `verify_chain()["ok"] is True` over the
    backfilled rows.
  - `test_hash_chain_links_sequential_rows`, `test_hash_chain_first_row_has_empty_prev_hash` —
    basic chain-construction correctness.
- **Known limitation** (noted, not fixed): `row_hash` canonicalizes fields
  with `"|".join(str(f))`; a crafted field value containing a literal `|`
  could in principle collide with an adjacent field boundary. Not exploitable
  today (no untrusted input reaches these fields un-jsonified), flagged for
  awareness rather than reworked.

### Leak 7 — subprocess/shell access (🟡 residual risk, confirmed by deployed evidence — not fully closed)

**Invariant broken:** #3 (external content / capability must not become
unchecked execution). The brief's suggested fix — minimal per-adapter image,
non-root execution, read-only filesystem "where possible" — was attempted
and partially reverted after real deployment testing showed the non-root
part doesn't work on this platform.

- **What was tried:** added `dockerfile_commands` to the adapter image:
  `useradd` a non-root user, `chown root:root` + `chmod -R a-w` on
  `/root/glc`, then `USER glcadapter`.
- **Deployed evidence it doesn't work:**
  ```
  => Step 3: USER glcadapter
  Skipping USER instruction, it is unsupported by Modal container images.
  ```
  and `adapter_verify` (real deployed run, both *before* adding the
  dockerfile_commands and *after*):
  ```
  "leak7_running_as_uid": 0,
  "leak7_running_as_root": true,
  "leak7_source_tree_writable": true
  ```
  identical in both cases — root ignores `chmod -R a-w`, so once `USER` is
  skipped the chmod is inert too. Checked for an alternative: neither
  `modal.App.function(...)` nor `modal.Sandbox.create(...)` (inspected both
  signatures against the installed `modal==1.5.1`) expose a user/uid
  parameter. Modal's isolation model runs container entrypoints as root and
  relies on its own gVisor/sandbox boundary instead of intra-container Linux
  users — this is a platform property, not a misconfiguration on our side.
  The dead `dockerfile_commands` block was **removed** rather than left in
  place, since a `chmod` that root ignores is worse than no chmod — it reads
  as a control that isn't actually there.
- **What Leak 7 fix *is* real:** the adapter image was already minimal (no
  `apt_install`, three pip deps: `pydantic`, `httpx`, `websockets` — no shell
  utilities added beyond what `debian_slim` ships). `verify_isolation()` now
  reports `leak7_running_as_uid` / `leak7_running_as_root` /
  `leak7_source_tree_writable` plainly, rather than silently claiming a fix
  that doesn't hold.
- **Why this is a bounded residual, not an open door:** an attacker who gets
  a shell inside an adapter container still gets *only* that: Phase 1 already
  proved (Leak 1/3/5/10 above) they land with no provider keys, no Volume, no
  `glc.policy`/`glc.db`/`glc.security` import path, and their own PID
  namespace. A root shell in an empty box is a much smaller prize than a root
  shell in the old monolith, which is what process separation was for — it
  just isn't *no* prize, and that gap is documented here rather than
  papered over.

---

## Phase 3 — egress allowlist (Leak 6, ✅ fixed, deployed + verified)

**Invariant broken:** #3 (external content / capability must not become
unchecked reach). **Attacker role:** adapter takeover — a plain Modal
`@app.function` has **no outbound network control at all**; any code running
in an adapter container can `httpx.post` to any host on the public internet
(e.g. exfiltrating provider replies, pairing state, or anything else it can
read, to an attacker-controlled server), and nothing in Modal's Function
primitive stops it.

**Fix:** the adapter image (unchanged) is now also run inside a
`modal.Sandbox.create(..., outbound_domain_allowlist=[GATEWAY_HOSTNAME])` —
confirmed via `inspect.signature(modal.Sandbox.create)` against the installed
`modal==1.5.1`, not assumed from training data (the brief's warning that this
API surface changes across versions was correct to heed: the parameter is
`outbound_domain_allowlist`, a Sequence[str], with a separate
`outbound_cidr_allowlist` and a `block_network` bool also available).
`GATEWAY_HOSTNAME` is the gateway's own Modal hostname — the only thing an
adapter legitimately needs to reach. New functions in `modal_app.py`:
`adapter_verify_sandboxed` (re-runs the full Phase 1 `verify_isolation()`
probe from inside the Sandbox) and `adapter_relay_sandboxed` (runs the real
adapter→gateway relay from inside the Sandbox, to prove the allowlist doesn't
break the legitimate path).

`verify_isolation()` (`glc/channels/runner.py`) gained a
`leak6_egress_to_attacker_domain` probe: `httpx.post` to `https://example.com/
exfil`. Deliberately **not** a made-up hostname like `attacker.example.com` —
that fails plain DNS resolution regardless of any Modal network policy
(confirmed: first attempt using that hostname gave `ConnectError: [Errno -5]
No address associated with hostname` in *both* the restricted and
unrestricted case, which is not evidence of anything). `example.com` is a
real, always-resolvable IANA test domain that is not the gateway and not on
any allowlist, so a block there is attributable specifically to the sandbox's
egress policy.

**Two real build/deploy issues hit and fixed along the way** (kept here
rather than silently smoothed over, since they're genuine Modal-platform
gotchas, not app bugs):
1. `Sandbox.create(workdir=...)` and `Sandbox.exec(workdir=...)` are two
   independent parameters — setting only the former left `python -c` running
   from the container's default cwd (not `/root`), so `import glc` failed
   with `ModuleNotFoundError` even though the source tree was present.
   Fixed by passing `workdir="/root"` to *both*.
2. `Image.add_local_dir(..., copy=False)` (the default) mounts the local
   directory into a container **at Modal's Function-entrypoint startup**,
   which a raw `Sandbox` never goes through — so with `copy=False` the
   adapter image built fine and the plain `adapter_verify` Function saw
   `/root/glc`, but any Sandbox built from the *same* image had no
   `/root/glc` at all. Fixed by switching the adapter image to
   `copy=True` (bake the tree into the image layer at build time), which
   is present in a container regardless of how it's started.

**Repro before (real deployed run, `modal run modal_app.py`, plain
`adapter_verify` Function):**
```json
"leak6_egress_to_attacker_domain": "REACHED (LEAK OPEN): status=405"
```
(a real TCP connection to `example.com` succeeded; 405 is just that host's
own "POST not allowed" response — the point is the connection was not
blocked at the network layer at all.)

**Repro after (real deployed run, same probe, from inside
`adapter_verify_sandboxed`'s Sandbox with `outbound_domain_allowlist=
[GATEWAY_HOSTNAME]`):**
```json
"leak6_egress_to_attacker_domain": "blocked: ConnectError: [Errno 104] Connection reset by peer"
```
with Modal's own sandbox logs showing the enforcement explicitly:
```
blocking all outbound connections to example.com (not on allow-list)
```
All of Leaks 1/2/3/4/5/8/10 (`verify_isolation()`'s other fields) read
identically closed inside the Sandbox as inside the plain Function — the
egress restriction doesn't loosen or interact with the Phase 1 isolation.

**Confirmed the allowlist doesn't break the legitimate path:** calling
`adapter_relay_sandboxed.remote()` (the real adapter→gateway relay, run
inside the same egress-restricted Sandbox) returned
```json
{"status": "dropped", "detail": {"error": "dropped: sender 'demo-user' not in allowed_senders for 'relay_echo'"}}
```
— i.e. the WS connection to the gateway host succeeded (the message reached
the gateway and was evaluated by its allowlist logic), and was rejected for
an unrelated, expected reason (the demo sender isn't paired), not a network
error. Had the allowlist also blocked the gateway host, this would have
raised a connection error instead of a policy-level "dropped".

**Known limitation (explicitly not fixed here, flagged per the brief):** an
allowlist restricts *destinations*, not *content*. It cannot stop
exfiltration through an already-allowed channel — e.g. an adapter smuggling
secrets inside the reply text it sends back to its own channel, or inside
metadata fields the gateway doesn't inspect. That's a data-flow / DLP concern
or Part 2; Part 1's egress allowlist closes the "adapter reaches an arbitrary
attacker-controlled host directly" leak, not "adapter cleverly encodes data
into a path it's allowed to use."

---

## Phase 4 — auth in front of the data plane (A1/A2, ✅ fixed, real before/after)

**Invariant broken:** #2 (every action must be checked against the actual
user/tenant — here, checked against *no one*: there was no caller identity
check at all). **Attacker role:** the weakest one in the brief — an outsider
on the public internet with no credentials whatsoever could call the entire
data plane and read every info-disclosure route.

**A1 — public data plane, no auth.** `POST /v1/chat`, `/chat/batch`,
`/embed`, `/vision`, `/speak`, `/transcribe` ran for anyone with the URL.
**A2 — unauthenticated info disclosure.** `/v1/status`, `/v1/providers`,
`/v1/capabilities`, `/v1/cost/by_agent`, `/v1/calls`, plus `/docs` and
`/openapi.json`, leaked provider order, models, rate limits, usage, and the
full route map to anyone. Both share one fix, since (convenient accident of
the existing code layout) every one of these routes except `/v1/speak` and
`/v1/transcribe` already lives on the single `chat_route.router` in
`glc/routes/chat.py`.

**Fix:**
- New `glc/security/auth.py::require_bearer_token` — a FastAPI dependency
  checking `Authorization: Bearer <install_token>` against the same
  `get_or_create_install_token()` already used by the control plane and the
  adapter WS (no new credential type introduced; this gateway has no
  per-caller roles/scopes for a second token type to usefully distinguish).
- Applied via `dependencies=[Depends(require_bearer_token)]` at
  `app.include_router(...)` time in `glc/main.py` for `chat_route.router`,
  `speak_route.router`, `transcribe_route.router` — enforced once per
  *router*, not per endpoint, so a route added to any of these files later
  can't be left un-gated by accident.
- `glc/routes/control.py` already had its own hand-rolled version of this
  same check (`_require_token`, duplicated per route). Refactored to use the
  shared dependency at the router level instead (`APIRouter(dependencies=
  [Depends(require_bearer_token)])`), deleting four duplicate call sites. The
  route-specific loopback check on `/v1/control/kill` is unrelated (network
  layer, not auth) and was left exactly as-is, per the brief's explicit
  instruction to keep it.
- `glc/routes/channels.py` (`channels_route.router`) is **deliberately not**
  given the same blanket router-level dependency: its `WS /v1/channels/{name}`
  already authenticates itself the same way (Bearer token in the connect
  headers, checked in Phase 1/2). Its `GET`/`POST /v1/channels/{name}/webhook`
  routes are called by the external channel provider (e.g. Meta), which
  cannot present our bearer token — they use their own `hub.verify_token`
  handshake instead, and in the separated v2 topology are further gated by
  `GLC_INPROC_ADAPTERS=0` → `410` regardless (Phase 1). This is a deliberate,
  documented exception to "every /v1/* route, no exceptions" for the one
  category of route that structurally can't use caller-supplied bearer auth.
- `glc/main.py`: `FastAPI(...)` now takes `docs_url=None if _PRODUCTION else
  "/docs"` (same for `redoc_url` / `openapi_url`), gated on
  `GLC_ENV=production`. `modal_app.py`'s `gateway_image` sets
  `GLC_ENV=production` via `.env(...)`; local dev (plain `uvicorn`/pytest,
  no `GLC_ENV` set) keeps the explorer on.

**Repro before** (real run against the pre-fix router wiring — captured by
temporarily zeroing `dependencies=` back to `[]` in a working copy, running,
then restoring immediately and re-confirming the full suite green again):
```
GET  /v1/providers          -> 200
GET  /v1/status             -> 200
GET  /v1/capabilities       -> 200
GET  /v1/cost/by_agent      -> 200
GET  /v1/calls              -> 200
POST /v1/chat               -> 503   (no providers wired in test env — but NOT 401/403)
POST /v1/embed              -> 422   (validation reached — but NOT 401/403)
POST /v1/vision             -> 422   (validation reached — but NOT 401/403)
```
i.e. every route was reachable with zero credentials; the non-2xx codes on
`chat`/`embed`/`vision` are downstream validation/availability responses, not
auth rejections — proof the request was processed, not blocked. (The same
fact is independently visible in the git diff of `tests/test_v9_compat.py`:
the pre-fix tests called these routes with no `Authorization` header at all
and asserted on response *bodies*, e.g. `assert k in body`.)

**Repro after** (real pytest run, current code):
- `tests/test_v9_compat.py::test_v1_data_plane_requires_bearer_token` —
  all 11 data-plane/info routes now return exactly `401` with no token.
- `tests/test_transcribe_route.py::test_transcribe_requires_bearer_token` —
  same for `/v1/transcribe`.
- `tests/test_control_plane.py` (pre-existing) — unaffected; still passes
  against the refactored shared dependency.
- `tests/test_docs_disabled_in_prod.py` (new) — reloads `glc.main` with
  `GLC_ENV=production` set and confirms `/docs`, `/redoc`, `/openapi.json`
  all return `404`; a second test confirms they're `200` with `GLC_ENV`
  unset (local-dev default unaffected).
- Full suite: `260 passed` (was `256` before Phase 4 — 4 new tests, plus the
  pre-existing V9-compat/transcribe tests updated to pass a token, per the
  diff above, rather than skipped or weakened).

**Also confirmed against the real deployed gateway** (`modal deploy`, then
`curl`, no local mocking):
```
GET  /v1/status    (no token) -> 401
POST /v1/chat      (no token) -> 401
GET  /docs         (GLC_ENV=production) -> 404
GET  /openapi.json (GLC_ENV=production) -> 404
GET  /healthz      (unauthenticated by design — health check) -> 200
```

**Known limitation (not fixed here, flagged rather than hidden):** every
caller shares one credential — there's no per-tenant or per-caller identity
behind the bearer token, so this closes "anonymous internet access" but not
"a legitimate holder of the token acting as any tenant it likes." Invariant
#2's *full* form (checked against the *actual* user/tenant) needs per-caller
identity, which this single shared-secret model doesn't provide; that's a
larger change than Part 1's floor requires and is noted as a gap, not solved
here.

---

## Phase 5 — SSRF, WS token, verbose errors, rate limits/budget, image pinning (✅ code fixed, real before/after; A5/A6 pending a live `modal deploy` — see note at end of section)

### C1 — SSRF via `/v1/vision` / `/v1/chat` image resolution (invariant #3)

`_resolve_image_urls` (`glc/routes/chat.py`, used by both `/v1/chat` and
`/v1/vision` since `vision` is a thin wrapper around `chat`) fetched any
`http(s)://` URL in an `image_url` block with `follow_redirects=True` and no
allowlist — a caller could point it at `http://169.254.169.254/...` (cloud
metadata) or any RFC1918 address and the gateway would fetch it server-side
and hand the bytes back as a data URL.

**Fix:** `_assert_host_is_public(hostname)` resolves the host via
`socket.getaddrinfo` and rejects if *any* returned address is
private/loopback/link-local/reserved/multicast/unspecified (via
`ipaddress`'s flags, which cover IPv4 and IPv6 uniformly, including
IPv4-mapped IPv6 like `::ffff:127.0.0.1`). The fetch loop now sets
`follow_redirects=False` and walks redirects manually (`_MAX_IMAGE_REDIRECTS
= 5`), calling `_assert_host_is_public` again before *every* hop — so a
public-looking first hop that 302s to an internal address is caught on the
second check, not just the first.

**Known residual gap (documented, not solved — same posture as Leak 7):**
this is resolve-then-connect, not a pinned-connection fetch, so DNS
rebinding between the check and httpx's own connect-time resolution isn't
closed. The brief's ask (resolve first, recheck every hop) is satisfied;
full rebinding protection needs a custom transport that connects to the
exact validated IP, which is a larger change.

**Repro before:** `_fetch_to_data_url` used
`AsyncClient(follow_redirects=True)` with no host check at all — a request
to `http://127.0.0.1:<gateway-port>/healthz` or
`http://169.254.169.254/latest/meta-data/` would be fetched successfully.

**Repro after** (`tests/test_ssrf_vision.py`, 22 tests, real pytest run):
- `_is_blocked_ip` unit-tested against `127.0.0.1`, `10.x`, `172.16.x`,
  `192.168.x`, `169.254.169.254`, `0.0.0.0`, `::1`, `fe80::1`, `fc00::1`,
  `::ffff:127.0.0.1`, `::ffff:169.254.169.254` — all blocked; `8.8.8.8`,
  `1.1.1.1`, a public IPv6 — all allowed.
- `test_direct_internal_url_is_blocked_before_any_fetch` — a message whose
  `image_url` is `http://127.0.0.1:8080/secret` raises `HTTPException(400)`
  and the mock transport's handler (which would assert-fail if called) is
  never invoked — proof no network request was attempted.
- `test_redirect_from_public_host_to_internal_host_is_blocked` — the core
  case: DNS resolves `public.example` to a real public IP, the mocked
  transport 302s to `http://127.0.0.1/internal-secret` on the first
  request, and the resolver is proven to reject the *redirect target*
  before following it (the handler asserts if the internal host is ever
  actually requested).
- `test_public_host_no_redirect_succeeds` — the legitimate path (public
  host, no redirect, 200) still returns a `data:image/png;base64,...` URL,
  proving the fix doesn't break normal image fetches.

### C3 — WS install token in the query string (invariant #4)

`channel_ws` accepted the install token via `?token=...` as a fallback
whenever no `Authorization` header was presented. Query strings land in
access logs, reverse-proxy logs, and browser history — exactly where a
bearer credential shouldn't be, and the fallback wasn't even needed: the
production relay path (`glc/channels/runner.py::relay`) already sends the
token in the header.

**Fix:** dropped the `Query` param and the `elif token:` fallback entirely
— `channel_ws` now accepts only `Authorization: Bearer <token>`. Updated
the two dev scripts that still built `?token=` URLs
(`glc/channels/catalogue/telegram/dev/live_poll.py`,
`glc/channels/catalogue/discord/tests/run_discord_bridge.py`) to send the
header via `websockets.connect(..., additional_headers=...)` instead.

**Repro before:** `ws_url = f".../v1/channels/telegram?token={token}"` was
a valid, accepted connection.

**Repro after** (`tests/test_ws_auth.py`, real pytest run):
- `test_query_string_token_is_no_longer_accepted` — connecting with a
  *correct* token only in `?token=` now raises `WebSocketDisconnect` (same
  as no credential at all).
- `test_no_credential_at_all_is_rejected` — unchanged baseline behavior.
- `test_header_token_still_works` — the legitimate path (header-only auth)
  still round-trips a message and gets the echo reply, so the fix doesn't
  regress the one path adapters are supposed to use.

### C4 — verbose upstream errors reach the client (invariant #1)

`/v1/chat`'s explicit-override failure path raised
`HTTPException(502, f"{name} failed: {e}")` and the final "no candidates
left" path raised `HTTPException(503, f"all providers unavailable.
attempts: {all_attempts}. last_error: {last_err}")` — both put the raw
provider SDK exception text straight into the response body. The streaming
path (`gen()`) did the same via `yield f"data: {json.dumps({'error':
str(e)[:300]})}\n\n"`. Provider error bodies can carry things an SDK
happens to echo back (account/org identifiers, request fragments, infra
hints) that shouldn't cross the trust boundary to whoever is calling the
gateway.

**Fix:** the three raise/yield sites now return a fixed generic string
(`_GENERIC_UPSTREAM_ERROR` / `_GENERIC_ALL_UNAVAILABLE`, defined once at
module level in `glc/routes/chat.py`) to the client, and log the real
exception server-side via `log.warning(...)` (new `logging.getLogger(__name__)`
in chat.py, matching the pattern already used elsewhere in `glc/`) — in
addition to the detail `db.log_call()` was already persisting to the
auth-gated `/v1/calls` audit trail. Client-input validation errors (bad
provider name, HUGE-tier 503, structured-output-schema-mismatch) were left
untouched — those describe the caller's own request, not upstream
internals, and are useful diagnostics, not leaks (confirmed by reading
`test_v9_compat.py` first: none of its assertions depend on the old raw
error text).

**A fifth leak site, found by advisor review after the first pass:** the
per-attempt `reason` tags appended to `all_attempts` (`tag = f"failed:
{str(e)[:100]}"` / `f"exception: {str(e)[:120]}"`) also embedded raw
`str(e)` — truncated, not sanitized. Those tags ride into
`ChatResponse.attempted`, which is returned on a **200** whenever a request
fails against one provider and then succeeds against the next (no explicit
override needed) — a real path, not an edge case, and the first pass's
"all four sites now return generic text" claim was wrong until this was
caught. Fixed by dropping `str(e)` from both tags entirely, keeping only
controlled vocabulary: provider name, the numeric HTTP `status` if the
exception carries one, and `_backoff_for`'s fixed reason categories
("rate limited", "timeout", "auth error", `f"upstream {status}"`, etc.) —
the routing diagnostic (which provider, what kind of failure) survives,
the raw upstream text doesn't.

**Repro before/after** (`tests/test_verbose_errors.py`, real pytest run):
- `test_explicit_provider_failure_returns_generic_502` — a fake provider
  raises `ProviderError("auth rejected for org_secret_internal_id=..., key=sk-should-not-leak")`;
  the response is `502` with `detail == "upstream provider request failed"`,
  and neither secret-looking substring appears anywhere in the response
  body.
- `test_all_providers_unavailable_returns_generic_503` — every provider
  raises an error embedding `quota_pool=prod-shard-7`; the final response is
  `503` with the fixed generic message, and that string is absent from the
  body.
- `test_fallback_then_success_does_not_leak_the_failed_providers_error_in_the_200`
  — the fifth-site case: no explicit override, provider `gemini` raises a
  retryable `ProviderError("...sk-should-not-leak-either...account=acct_9999...",
  status=500)`, provider `groq` then succeeds. Before the tag fix this test
  fails (`sk-should-not-leak-either` is present in the 200 body's
  `attempted` list); after the fix it passes — 200, the secret-looking
  substrings are absent, and `attempted` still correctly shows a `gemini`
  entry so the routing diagnostic isn't lost, just the raw text.

### C5 — no rate limits or cost budget on the data plane (invariant #8)

`/v1/chat`, `/v1/vision`, `/v1/embed`, `/v1/speak`, `/v1/transcribe` had
auth (Phase 4) but nothing bounding request volume or spend per caller —
invariant 8's "hard limits on time, tokens, tool calls, and cost" was
unenforced above the per-provider RPM/RPD bookkeeping in `routing.py`
(which protects the gateway's own provider quotas, not the caller).

**Fix:** new `glc/security/data_plane_limits.py`:
- `TokenBucket` — per-key (caller) token bucket, `GLC_DATA_PLANE_RPM`
  (default 60) capacity with continuous refill.
- `enforce_rate_limit` — FastAPI dependency; 429 with a clear message once
  a caller's bucket is empty.
- `enforce_cost_budget` — circuit breaker; sums today's actual spend from
  `db.aggregate(call_role="worker")` (real logged token counts) priced via
  the existing `glc/pricing.py`, and returns 503 once
  `GLC_DAILY_COST_CEILING_USD` (default $5) is reached. A ceiling of 0
  is an explicit opt-out, not the default.

Both are added to `_v1_auth` in `glc/main.py` alongside
`require_bearer_token`, at `include_router()` time — the same "no route can
be added un-gated by accident" reasoning as Phase 4.

**Scoping decision (documented, not invented):** this gateway has no
"run" concept yet — invariant 8 talks about agent runs, but the S11 agent
runtime (`glc/routes/channels.py`) is still an echo stub. Invariant 8 is
therefore enforced at the coarsest defensible scope available today:
per-caller-per-minute rate limiting and a gateway-wide daily cost ceiling.
The rate limiter keys on source IP, not a per-tenant identity, because
(per Phase 4's already-documented gap) there is only one shared bearer
token — behind a shared NAT/proxy, distinct callers collapse into one
bucket. Both gaps need the same fix (per-caller credentials) and are noted
together, not separately, so they don't get "solved twice, differently."

In-memory bucket/budget-check state is process-local; this is only sound
because of **A6** (below) pinning the gateway to exactly one container —
otherwise autoscaling would silently multiply the effective rate limit,
one bucket per container.

**Repro before/after** (`tests/test_data_plane_limits.py`, real pytest run):
- `TokenBucket` unit tests: exhausts at capacity and blocks the next call;
  independent keys don't share budget.
- `test_rate_limit_trips_429_over_http` — with `GLC_DATA_PLANE_RPM=2`, the
  3rd `/v1/status` call in a row from the same client returns `429`.
- `test_cost_breaker_disabled_at_zero_ceiling` — ceiling `0` is a no-op, by
  design.
- `test_cost_breaker_trips_when_todays_spend_meets_ceiling` /
  `test_cost_breaker_end_to_end_over_http` — logging a real (`groq`,
  1,000,000 input tokens) call against a `$0.01` ceiling trips the breaker;
  the next `/v1/status` call returns `503` with `"circuit breaker"` in the
  detail.

### A5 — non-reproducible base image / loose dependency ranges

`gateway_image` and `adapter_image` both built on
`modal.Image.debian_slim(python_version="3.11")` (floats to whatever
`python:3.11-slim` resolves to on build day) with `pip_install(">=x")`
ranges — a rebuild could silently pick up a newer, unreviewed dependency
release, and the base OS layer wasn't pinned at all.

**Fix:**
- Both images now build from `modal.Image.from_registry(f"python:3.11-slim@{digest}")`
  — the immutable manifest-list digest for `library/python:3.11-slim`
  (resolved 2026-07-16 via the Docker Hub registry API), not the mutable
  tag. A base-image bump now requires deliberately changing the digest
  constant, not just re-running `modal deploy` on a day the tag moved.
- `gateway_image` installs dependencies via `.uv_sync()` (`uv sync
  --frozen` under the hood, uv_sync's default) against the repo's checked-in
  `pyproject.toml` + `uv.lock` — the build now reproduces the exact locked,
  hashed dependency set or fails; it can't drift.
  **Correction caught on review, before this was called "nothing extra":**
  `uv_sync()` syncs the project's *default* dependency groups, which
  includes `[dependency-groups] dev` (`pytest`, `ruff`, `mypy`, `pytest-cov`,
  ...) alongside `[project.dependencies]` — confirmed by the real deploy
  log below, which shows `mypy==2.1.0`, `ruff==0.15.17`, `pytest==9.1.0` etc.
  installed into the gateway image. That's image-size bloat (dev tooling
  ships to a runtime container), not a security regression — the gateway
  image is already the trusted, full-`glc` image with every provider key,
  so a few extra dev packages don't change its trust boundary — but the
  original claim was wrong and is corrected here rather than left standing.
  Tightening this later means passing `groups=[]` (or the equivalent
  no-dev flag) to `uv_sync()`.
- `adapter_image` deliberately does **not** use `uv_sync()` — that would
  install every package in `pyproject.toml`'s dependency group (fastapi,
  jsonschema, twilio, ...) and silently re-bloat the pruned adapter image,
  defeating the point of pruning it in Phase 1. Instead its three actual
  deps are pinned to the exact versions `uv.lock` resolved for the gateway
  build (`pydantic==2.13.4`, `httpx==0.28.1`, `websockets==16.0`), so both
  images agree on versions without the adapter gaining anything unused.

Verified by inspection against the installed `modal==1.5.1` API (per
ASSIGNMENT.md's warning not to assume the surface from training data):
`inspect.signature(modal.App.function)` and `dir(modal.Image)` confirmed
`from_registry`, `uv_sync`, and `pip_install` all exist with the parameters
used here; `modal.Image.uv_sync.__doc__`'s own example is literally
`modal.Image.debian_slim().uv_sync()`, confirming the chaining pattern.

**Repro after — real `modal deploy modal_app.py`** (user-approved, run
2026-07-16): both images built successfully from the pinned
`python:3.11-slim@sha256:db3ff2e1...53a93` base. Build log excerpt for the
adapter image confirms the exact pinned versions actually landed (not just
requested):
```
Installing collected packages: websockets, ... pydantic-core, httpcore, anyio, pydantic, httpx
Successfully installed ... httpx-0.28.1 ... pydantic-2.13.4 ... websockets-16.0 ...
```
Gateway image build log confirms `uv sync --frozen` ran against the
checked-in lock and installed the full pinned set (`fastapi==0.137.1`,
`pydantic==2.13.4`, `httpx==0.28.1`, `websockets==16.0`, `modal==1.5.1`,
...) — matching `uv.lock` exactly, plus the dev-group bloat noted above.
Deploy succeeded end-to-end: `✓ App deployed in 28.844s!` →
`https://aryamanchandak7--glc-v2-gateway-fastapi-app.modal.run`.

Post-deploy `curl` against the live URL (real, not mocked):
```
GET /healthz    -> 200   (unauthenticated by design)
GET /v1/status  -> 401   (Phase 4 auth still enforced on the rebuilt image)
GET /docs       -> 404   (GLC_ENV=production still enforced)
```

Re-ran `modal run modal_app.py` (the same `adapter_verify` /
`adapter_verify_sandboxed` probe from Phase 1/3) against the *rebuilt,
digest-pinned* adapter image to confirm the base-image/dependency-pinning
change didn't regress any prior isolation property — all held: provider
keys absent, `glc.policy`/`glc.db`/`glc.security` unimportable, no Volume,
Sandbox egress to `example.com` blocked (`Connection reset by peer`),
unrestricted Function egress still open (the expected, documented Phase 3
contrast). Full JSON output matches the Phase 1/3 "after" shape recorded
earlier in this document.

### A6 — audit DB concurrency risk from autoscaling

`fastapi_app` ran with `min_containers=0` and no `max_containers` cap, so
under load Modal could spin up more than one gateway container, each
opening its own SQLite connection to the same `/data/glc/audit.sqlite` on
the shared Volume — concurrent writers with no serialization, which is
exactly how an audit trail gets split/corrupted, and it would silently
break Phase 2's hash-chain invariant (each row must chain from the
previous one in a single, ordered sequence of writes).

**Fix:** `fastapi_app` now pins `min_containers=1, max_containers=1`,
confirmed to exist on the installed `modal==1.5.1` API via
`inspect.signature(modal.App.function)` before using them. This makes the
gateway itself the single serialized writer Phase 2 already assumed.

**Repro after:** `modal deploy` accepted the decorator with both params set
(a `TypeError`/validation error at deploy time would have surfaced
immediately if either param name or value were wrong — it didn't) and
`modal app list` shows the deployed `glc-v2-gateway` app running with `1`
container, consistent with the pin. Not independently pytest-verifiable
beyond that — this is a Modal scheduling guarantee enforced platform-side,
not application code.

C1/C3/C4/C5 are additionally proven by the real pytest runs above; the
full suite is `294 passed` (was `260` before Phase 5 — 34 new tests: 22 in
`test_ssrf_vision.py`, 3 in `test_ws_auth.py`, 3 in
`test_verbose_errors.py`, 6 in `test_data_plane_limits.py`; run `pytest -q`
from repo root to reproduce).

---

## Phase 6 — Post-audit hardening (independent review, 2026-07-16)

An independent review (Codex) of everything through Phase 5 found the
Part 1 floor was not actually cleared, despite every phase's own tests
passing. Verified directly against the checked-out code before starting
any fix (not taken on faith either way): every blocking finding below was
confirmed first, then fixed, then re-verified with a real repro.

**The meta-lesson.** Each phase's own test suite checked what THAT phase
changed in isolation (Phase 4's test: "no token → 401" — true) but never
re-checked an invariant an EARLIER phase had already established. Phase 1
correctly stripped adapters of in-process power (no provider keys, no
`glc.policy`/`glc.db`/`glc.security` imports, no Volume); Phase 4 then
quietly handed equivalent power back over HTTP by giving every adapter the
exact same bearer token used for the control plane. Green tests at every
step were not proof the brief's invariant list still held end-to-end.

### Keystone — every adapter held the control-plane's own token (Leaks 3/9 reopened)

**Repro before:** `glc/channels/runner.py` read `GLC_INSTALL_TOKEN` — the
identical token `glc/security/auth.py::require_bearer_token` checked for
`/v1/control/*`. `POST /v1/control/pair` (`glc/routes/control.py`) accepted
`trust_level="owner_paired"` and handed the pairing code straight back in
the response; `POST /v1/control/pair/confirm` took just that code with no
independent owner-side check. A compromised adapter — holding only what
Phase 1/3 gave it — could self-request and self-confirm owner trust over
plain HTTP, and could open `WS /v1/channels/<any other channel>` and
impersonate it, all with the one credential it already had.

**Fix:** new `glc/security/adapter_auth.py` — `derive_channel_token(install_token,
channel)` = `HMAC-SHA256(install_token, channel)`. Each adapter Function
now mounts a per-channel Secret (`glc-channel-<name>`, e.g.
`glc-channel-relay-echo`) holding only `GLC_CHANNEL_TOKEN`, never the raw
install token (`modal_app.py`: `relay_echo_channel_secret`, replacing
`control_secret` on every adapter Function). `channel_ws` in
`glc/routes/channels.py` accepts either the raw install token (the
admin/dev credential, kept only by the gateway operator/WebUI, never
distributed to an adapter) or exactly that route's own derived token —
binding happens at the WS handshake itself, not just via the existing
Leak-9 envelope-channel check. `/v1/control/*` still only accepts the raw
token, so a channel-scoped token can never authenticate it. Provisioning:
`GLC_INSTALL_TOKEN=<raw> uv run modal run modal_app.py::derive_channel_token_cli
--channel relay_echo`.

**Repro after:** `tests/test_channel_scoped_credentials.py` (10 tests) —
a token derived for one channel authenticates only that channel's WS route
and is rejected on another channel's route before any envelope is even
sent; the same token gets `403` from `/v1/control/pair` and
`/v1/control/presence`; the raw install token still works for WS (the
admin path stays intact). `runner.py::verify_isolation()` gained a live
network probe (`leak1_9_channel_token_cannot_reach_control_plane`) that
POSTs to `/v1/control/pair` using only `GLC_CHANNEL_TOKEN` and asserts a
401/403 — reachable from inside the Sandbox since the gateway host is on
its egress allowlist, so this is real deployed evidence, not just a unit
test, once redeployed.

### Trust level was never re-derived (Invariant 2)

**Repro before:** `channels.py`'s WS handler recorded `env.trust_level` —
the adapter's own unverified claim — into every audit event, even though
`glc/security/trust_level.py::classify()` already existed and the adapter
module's docstring claimed "gateway re-classifies trust." Nothing called it.

**Fix:** both the WS handler and the legacy in-process webhook handler now
call `classify(channel, channel_user_id)` against the gateway's own
pairing store and use that (`real_trust`) everywhere instead of
`env.trust_level` / `msg.trust_level`.

**Repro after:** `test_ws_handler_reclassifies_trust_and_ignores_adapter_claim`
— a sender who is allowlisted but never paired claims
`trust_level="owner_paired"` in the envelope; the audit record still shows
the gateway-derived `"untrusted"`.

### Audit hash chain didn't catch truncation (Invariant 7)

**Repro before (exact shape from the review):** `DELETE FROM audit_log`
(whole table) and deleting just the last row both returned `verify_chain()
== {"ok": True, ...}` — the in-table chain has nothing left to disagree
with rows that no longer exist.

**Fix:** `glc/audit/store.py` now writes an external checkpoint file
(`audit_chain_checkpoint.json`, next to but NOT inside `audit_log`) on
every successful `append()`, recording row count + tip hash.
`verify_chain()` cross-checks the table's actual tip/count against it
after the in-table walk passes. `init_store()` now also runs
`verify_chain()` automatically at every gateway startup (it previously ran
only on demand) and, on a detected break, logs an error and records a
permanent `audit_chain_verification_failed` event in the log itself. New
`GET /v1/control/audit/verify` lets an operator check on demand without
gateway-process code execution.

**Repro after:** `test_hash_chain_detects_delete_all_rows`,
`test_hash_chain_detects_delete_last_row` (both fail pre-fix, pass
post-fix — reproduced the review's exact two DELETE shapes),
`test_new_append_after_truncation_still_gets_recorded_and_resyncs_checkpoint`,
`test_init_store_auto_verifies_and_records_detected_tampering_on_restart`.
An attacker with filesystem access can still edit both files, but now has
to keep two independent files consistent instead of one — same
"detectable, not unconditionally preventable" posture as the original
row-level chain, extended to cover the tail.

### Invariant 8 — no real per-run hard limits

**Repro before:** `ChatRequest.max_tokens` was an unbounded `int`;
`BatchChatRequest.calls`/`max_concurrency` were unbounded; no wall-clock
timeout wrapped a provider call (a hung provider blocked the request
forever); only a gateway-wide daily cost ceiling existed, which only ever
catches overspend in aggregate, after many runs.

**Fix:** `glc/llm_schemas.py` — `field_validator`s cap `ChatRequest`/
`VisionRequest.max_tokens` (`GLC_MAX_TOKENS_CEILING`, default 8192) and
`BatchChatRequest.calls`/`max_concurrency` (`GLC_MAX_BATCH_CALLS`/
`GLC_MAX_BATCH_CONCURRENCY`). `glc/security/data_plane_limits.py` gained
`run_timeout_seconds()` (`GLC_RUN_TIMEOUT_SECONDS`, default 60) and
`enforce_per_run_cost_ceiling()` (`GLC_PER_RUN_COST_CEILING_USD`, default
$2, priced conservatively against the most expensive configured
provider/direction since the provider isn't chosen yet at that point in
the request). `glc/routes/chat.py`'s `chat` and `embed` routes are now
thin wrappers around `_chat_impl`/`_embed_impl`, wrapped in
`asyncio.wait_for(..., timeout=run_timeout_seconds())`; `chat_batch` and
`vision` both call `chat(...)` directly so each call in a batch gets its
own independent cap, not one shared budget.

**Repro after:** `tests/test_run_limits.py` (8 tests) — an over-ceiling
`max_tokens` is rejected with `422`; an over-limit batch/concurrency is
rejected with `422`; a provider that `await asyncio.sleep(999)`s trips a
`504` at a shortened timeout while a normal instant provider still
completes `200` inside a normal timeout; a request whose worst-case cost
exceeds a (deliberately tiny, for the test) per-run ceiling is rejected
`413`, and the ceiling is a genuine opt-out at `0`.

### Two scaffolding/test-infra issues also confirmed and fixed

- **Unsandboxed adapter Functions stayed deployed** (`adapter_verify`/
  `adapter_relay` in `modal_app.py`, unrestricted egress, originally
  holding the control secret) — kept alive only for a one-time Leak 6
  before/after comparison already captured in this document. Deleted;
  only the Sandboxed variants (which are also the production-shaped path)
  remain deployed.
- **`294 passed` wasn't reproducible out of order** — confirmed via
  `glc.db.DB_PATH` being a module-level constant computed once at import
  time, frozen against whatever `GLC_GATEWAY_DB` happened to be at first
  import, silently ignoring every later per-test change. Fixed the same
  way `glc.audit.store`/`glc.security.pairing` already did it: resolve the
  path at call time (`glc.db._resolve_path()`), not import time. One test
  (`test_cost_breaker_trips_when_todays_spend_meets_ceiling`) also never
  triggered `db.init()` (no `app_client` fixture) and was silently riding
  on another test's already-initialized `calls` table; fixed by calling
  `db.init()` directly. Full suite now passes in both declared order and
  a deliberately reordered run: `318 passed` both times.

Full suite after Phase 6: **318 passed** (was 294 — 24 net new tests:
10 in `test_channel_scoped_credentials.py`, 5 in `test_audit_log.py`,
2 in `test_control_plane.py`, 8 in `test_run_limits.py`, minus edits to
existing files; `ruff check` and `python -m compileall` both still pass).

---

## Phase 7 — re-verification against `6_7_2_findings.md` (2026-07-18)

A fresh recon list (18 items, curled against the **v1** deployment at
`admin-14505--glc-v1-gateway-fastapi-app.modal.run`) was cross-checked item by
item against `glc_V2_fixed`. All 18 map onto work already done in Phases 1–6;
nothing in the list was a new class of problem. Re-verification was
*behavioural*, not grep-only: the full suite plus a direct `TestClient` probe of
every endpoint named in the recon.

### Item-by-item verdict

"How proven" matters as much as the verdict. **Behavioural** = observed a real
response/return value this pass. **Config** = read from `modal_app.py` /
deployment shape; the local suite *cannot* prove these, because locally the full
`glc` tree is importable and the split secrets don't exist — live proof needs the
Modal isolation run after a redeploy.

| # | Recon item | Verdict | How proven |
|---|---|---|---|
| 1 | `/openapi.json` + `/docs` public | ✅ | Behavioural — 404 under `GLC_ENV=production` (Phase 4) |
| 2 | `/v1/status` leaks provider config | ✅ | Behavioural — 401 with no token |
| 3 | `/v1/chat` unauthenticated | ✅ | Behavioural — 401 with no token |
| 4 | SSRF via image URL | 🟡 mostly | Behavioural — private/loopback/link-local/v6 all 400, per-hop recheck tested. Allowlist clause added but **opt-in** (see below) |
| 5 | Upstream error detail echoed to client | ✅ | Behavioural — generic strings on 502/503/stream; Phase 5 also fixed the `attempted` tags that rode into a **200** |
| 6 | `/v1/cost/by_agent` public | 🟡 half | Behavioural — 401 now. But "scope results to the requesting tenant" is **not** done (no tenant identity) |
| 7 | `/v1/control/presence` already gated | ✅ n/a | Recon says "nothing to fix"; still 401 |
| 8 | Adapter reads provider keys | ✅ | **Config** — `llm_secret` mounted on the gateway Function only |
| 9 | `DELETE FROM audit_log` undetected | ✅ | Behavioural — `verify_chain()` returns `ok=False, reason="chain truncated…"` via the external checkpoint |
| 10 | `force_pair_owner()` self-escalation | 🟡 narrowed further | Behavioural — `/v1/control/pair` now rejects `trust_level="owner_paired"` outright (400); owner trust is installer-only, so **no** HTTP path mints owner even for a raw-token holder. Residual: the function is still importable by in-process gateway code (process-boundary answer, not an in-process lock) |
| 11 | Adapter reads the install token | ✅ | **Config** — `control_secret` is gateway-only since Phase 6; adapters mount `glc-channel-<name>` |
| 12 | Monkeypatch the policy engine | ⬜ out of scope | The recon file itself marks this "capstone scope." `glc/policy/**` is excluded from the adapter image, so it's unreachable from adapter code, but same-process gateway code can still patch it |
| 13 | `os.kill` the gateway | ✅ | **Config** — separate Modal Functions ⇒ separate PID namespaces |
| 14 | Forge a row via `glc.db.log_call` | ✅ | **Config** — `db.py` in `_ADAPTER_IGNORE`; import fails in the adapter image |
| 15 | No egress wall (A3) | ✅ | **Config** — adapters run in `modal.Sandbox(outbound_domain_allowlist=[gateway])`; the unrestricted demo Functions were deleted in Phase 6 |
| 16 | One Secret for the whole Function (A4) | ✅ | **Config** — three separate secrets, split by trust boundary |
| 17 | Non-reproducible image (A5) | ✅ | **Config** — both images from a digest-pinned `python:3.11-slim`; gateway `uv_sync()` against `uv.lock`, adapter pins exact versions |
| 18 | Audit volume assumes one writer (A6) | ✅ | **Config** — `min_containers=1, max_containers=1` on the gateway Function |

Evidence captured this pass:

- `/docs`, `/redoc`, `/openapi.json` → **404** with `GLC_ENV=production` (recon #1).
- Every `/v1/*` route named in the recon → **401** with no token: `status`,
  `cost/by_agent`, `providers`, `capabilities`, `routers`, `calls`, `embedders`,
  `chat`, `chat/batch`, `vision`, `embed`, `transcribe`, `speak`,
  `control/pair`, `control/kill` (recon #1/#2/#3/#6). `/healthz` stays **200**
  by design.
- SSRF probes → **400** for `127.0.0.1`, `169.254.169.254` (metadata),
  `[::1]`, `10.0.0.5` (recon #4).
- `max_tokens=1e9` and a 5000-call batch → **422** (invariant 8 ceilings).
- `verify_chain()` after `DELETE FROM audit_log` → `ok=False`, reason
  `chain truncated: checkpoint expected 5 row(s) ending at id=5, found 0` (recon #9).

Two genuine gaps found and fixed in this pass:

1. **C1's destination-allowlist clause was never implemented.** The recon's fix
   text for #4 is three-part — "allowlist destinations, block loopback/private/
   link-local ranges for IPv4 and IPv6, and re-check after every redirect."
   Phase 5 delivered parts 2 and 3; there was no allowlist at all. Added
   `_image_host_allowlist()` / `_assert_host_is_allowed()` in
   `glc/routes/chat.py`, driven by `GLC_IMAGE_HOST_ALLOWLIST`, enforced on the
   initial fetch **and every redirect hop** (a test proves the per-hop check —
   an allowlisted first hop cannot redirect off-allowlist). Matching is
   case-insensitive, trailing-dot-tolerant, and anchored on a label boundary so
   `notexample.com` does not satisfy an entry of `example.com`.
   **Deliberately opt-in**: image URLs legitimately arrive from arbitrary chat
   users, so a non-empty default would break normal traffic. Unset (the
   default) means the private-range block alone still applies — so this is
   "mechanism now exists and is enforced when configured," not
   "deny-by-default everywhere." Stated plainly rather than counted as a
   full close.
2. **Non-http(s) image schemes were relayed to the provider verbatim.**
   *Not one of the 18 recon items* — found while probing #4, and arguably not a
   gateway-side SSRF at all (the gateway never opens these; the provider's
   fetcher would). Kept as defence-in-depth, but it **changes behaviour**: The
   old resolver only fetched `http(s)://` URLs and passed everything else
   through untouched — including `file://` / `gopher://`, which the gateway
   never opened itself but did forward upstream (the old test
   `test_non_http_scheme_is_left_unfetched` asserted exactly this pass-through
   as correct). Now anything that is neither `http(s)` nor an inline `data:`
   URL is rejected with **400 unsupported image url scheme**. The old test was
   replaced, not deleted silently — behaviour intentionally inverted.

A third fix (defence-in-depth) went in for #10: `/v1/control/pair` now rejects
`trust_level="owner_paired"` (400) — owner trust is bootstrapped only by the
out-of-band installer (`force_pair_owner`), so no HTTP caller mints owner even
with the raw install token. Framed as surface-reduction, not closing a hole an
untrusted party could reach (the only remaining caller is the trusted
token holder); the importable-function residual is the process-boundary answer.

Suite: **335 passed** (was 323; +12 across scheme-rejection, host-allowlist, and
the owner-paired restriction cases). `ruff check glc tests` clean.

The submission-ready per-item writeup — new finding #19, the #4/#6/#10/#12
revisits, and the "why config-verified" explanation — lives in the recon file
the assignment is submitted from (`../6_7_2_findings.md`, "PART 1 — RESOLUTION
ADDENDUM").

Three recon items are **not** clean closes and are recorded as such:

- **#6** asks to authenticate *and* "scope results to the requesting tenant."
  Auth is done; per-tenant scoping is not — see the per-caller-identity row
  below. Half-satisfied.
- **#10** (`force_pair_owner`) — reachable paths closed, function still
  importable in-process. See its row below.
- **#12** (policy-engine monkeypatch) — the recon file itself marks this
  "capstone scope." Out of Part 1 by the brief's own scoping, not fixed here.

**Deployment status:** Phase 6 and Phase 7 are **code-only**. The live v2
deployment predates both, so re-running the recon's curls against the live URL
today will not show the Phase 6/7 behaviour. Live proof still requires
`modal secret create glc-channel-relay-echo …` followed by
`modal deploy modal_app.py` — both production-affecting, both awaiting explicit
go-ahead.

---

## Remaining work (genuinely open — not proxy for "not yet gotten to")

| Item | Invariant | Status | Plan |
|---|---|---|---|
| **Leak 7** — non-root / read-only FS | #3 | 🟡 (residual, see Phase 2 writeup above) | Not achievable on Modal 1.5.1 (no user/uid knob on Function or Sandbox); revisit if the platform adds one. Blast radius already bounded by Phase 1. |
| **A5 dev-dependency bloat** | — (size, not security) | 🟡 (noted on review, see A5 writeup) | `uv_sync()` pulls in `[dependency-groups] dev` (pytest/ruff/mypy/...) alongside the runtime deps — confirmed in the real deploy log. Not a trust-boundary issue (gateway is already the full-access image), just avoidable image bloat; fix by passing `groups=[]` or the uv_sync no-dev equivalent. |
| **Per-caller identity for the HTTP data plane** | #2, #8 | ⬜ (narrowed by Phase 6, not closed) | The adapter side of "one shared credential" is fixed (channel-scoped tokens). The `/v1/*` data-plane bearer token itself is still one shared credential across all HTTP callers — needed for true per-tenant checks and to key C5's rate limiter on identity instead of source IP. |
| **DNS rebinding on C1's SSRF check** | #3 | 🟡 (documented residual, see C1 writeup) | Resolve-then-connect leaves a TOCTOU window; closing it needs a custom transport that connects to the exact validated IP rather than re-resolving at connect time. |
| **`force_pair_owner()` has no dedicated capability restriction** | #6 | 🟡 (exposure narrowed by Phase 6, not eliminated) | Its only reachable HTTP path (`/v1/control/pair` + `/pair/confirm` self-confirm) now requires the raw install token, which adapters never hold — but the method itself is still an ordinary importable function reachable by any gateway-process code execution (the strongest attacker role in the brief). Restricting it to a dedicated startup/install-only call path is still open. |
| **15 catalogue adapters unmigrated** | #1–#5 (by construction, once migrated) | ⬜ (unchanged, judgment call) | Only `EchoIngressAdapter` is deployed; the pruned adapter image still excludes `channels/catalogue/*/**`. Real adapters can't load in the pruned image yet, so this is mechanical migration work, not a live vulnerability — but it does mean only one reference adapter, not real functionality, is currently live. |
| **Image-host allowlist is opt-in, not default-deny** | #3 | 🟡 (mechanism added Phase 7, unset by default) | `GLC_IMAGE_HOST_ALLOWLIST` is enforced on every hop when set, but empty by default because image URLs come from arbitrary chat users. Deployments with known image sources (one CDN, one bucket) should set it to get real deny-by-default; until then the private-range block is the only image-destination control. |
| **Channel webhook GET/POST routes stay ungated** | #2 (literal reading of A1) | ⬜ (unchanged, judgment call) | External providers can't present our bearer token; `GLC_INPROC_ADAPTERS=0` returns `410` in production regardless. Documented exception to "every /v1/* route, no exceptions," not a fix. |
