# FINDINGS.md — glc_v2 Part 1 Hardening

Per the assignment: *"a short note that, for each finding, names the invariant
from Section 4 that it broke and shows the fix"* — and, per step 2, one
sentence per finding naming the invariant broken and the attacker role that
reaches it. This is that note. Full evidence (before/after repros, test names,
residual-risk reasoning) lives in `FINDINGS_DETAIL.md`; this file is the
graded deliverable, kept to what was asked.

**Attacker roles** (verbatim from Section 4), weakest to
strongest: **1** outsider on the public internet, no credentials · **2** normal
channel user, controls only the text they type · **3** attacker who has taken
over a single adapter container · **4** attacker with code execution inside
the gateway process itself.

**Deployment note:** the fixes below are all committed and locally verified
(full pytest suite green). The live Modal deployment reflects the earlier
phases; the last two rounds of fixes are code-only pending a `modal deploy`
(a production action, awaiting go-ahead) — flagged so a live curl against the
deployed URL isn't read as contradicting this note.

| # | Finding | Invariant broken & attacker role | Fix | Status |
|---|---|---|---|---|
| 1 | `/openapi.json` + `/docs` publicly readable | No clean Inv 1–8 match (closest: Inv 2 — no caller check exists at all yet); reachable by **role 1**, any outsider. | `GLC_ENV=production` disables `docs_url`/`openapi_url`. | ✅ |
| 2 | `/v1/status` unauthenticated, leaks provider config | **Inv 2** — served with no check of who's asking; **role 1**. | `require_bearer_token` on the router. | ✅ |
| 3 | `/v1/chat` unauthenticated, real billable call | **Inv 2** — a costed action with zero identity check; **role 1**. | `require_bearer_token`. | ✅ |
| 4 | SSRF via `image_url` (loopback/private/link-local/metadata) | **Inv 3** — external URL treated as an instruction to fetch; **role 1** pre-auth, any token holder post-auth. | Private-range block (v4+v6), per-hop redirect recheck, opt-in host allowlist. | 🟡 DNS-rebind TOCTOU documented as residual |
| 5 | Verbose upstream error returned to client | No clean Inv 1–8 match (info-disclosure hygiene); **role 1**. | Generic client error; real detail server-side only. | ✅ |
| 6 | `/v1/cost/by_agent` unauthenticated & unscoped | **Inv 2** (auth) + **Inv 5** (tenant scoping); **role 1**. | `require_bearer_token` closes auth; scoping needs per-caller identity that doesn't exist yet — out of Part 1 scope, not faked. | 🟡 half |
| 7 | `/v1/control/presence` | Already gated — nothing broke; used as the baseline for what right looks like. | n/a. | ✅ baseline |
| 8 | Adapter reads every provider API key | **Inv 1**, exact; **role 3** (adapter takeover). | Provider-key Secret mounted on the gateway Function only. | ✅ |
| 9 | `DELETE FROM audit_log` leaves no trace | **Inv 7**, exact; **role 3** in the monolith → residual **role 4** only, post-separation. | Hash chain + external checkpoint; `verify_chain()` detects truncation. | ✅ |
| 10 | `force_pair_owner()` self-escalates to owner | **Inv 2** (unchecked caller) + **Inv 4** (credential scope); **role 3** in the monolith → residual **role 4**. | Process separation + channel-scoped tokens; `/v1/control/pair` refuses `owner_paired` over HTTP outright. | ✅ unreachable over HTTP/adapter |
| 11 | Install token readable in-process | **Inv 1**, extended to the control-plane credential; **role 3**. | Token via gateway-only Secret; adapters get a derived per-channel token instead. | ✅ |
| 12 | Policy engine monkey-patched to always allow | **Inv 6** — forges approval entirely; **role 3** in the monolith → residual **role 4**, capstone scope. | Adapters cannot import `glc.policy`. In-process gateway code is unfixable by construction (any code that can rebind `evaluate` can also defeat a guard around it) — real fix is a separate policy process, explicitly out of Part 1. | ⬜ by design |
| 13 | `os.kill` terminates the gateway | **Inv 8** — availability precondition; **role 3**. | Separate Modal Functions → separate PID namespaces. | ✅ |
| 14 | Forge a cost-ledger row | **Inv 8** — ledger integrity; **role 3** in the monolith → residual **role 4**. | `db.py` excluded from the adapter image. | ✅ |
| 15 | No egress wall (A3) | **Inv 3** — unrestricted egress; **role 3**. | `modal.Sandbox(outbound_domain_allowlist=[gateway])`. | ✅ |
| 16 | One Secret for the whole Function (A4) | **Inv 1** — architectural root cause of #8/#11; **role 3** (role 4 holding the gateway's own secrets is by design, not a violation). | Three secrets split along the trust boundary. | ✅ |
| 17 | Non-reproducible image (A5) | No clean Inv 1–8 match (supply-chain, OWASP A06); reachable only by an upstream supply-chain actor, outside roles 1–4. | Digest-pinned base image; `uv.lock`-locked dependencies. | ✅ |
| 18 | Audit volume assumes one writer (A6) | **Inv 7** + **Inv 8** — concurrent writers corrupt the chain/ledger; no attacker — triggered by platform autoscaling. | `min_containers=1, max_containers=1`. | ✅ |
| 19 (bonus) | Non-http(s) image schemes relayed to the provider verbatim | **Inv 3**, same class as #4; **role 1**, any data-plane caller. | Reject any image URL scheme that isn't `http(s)` or inline `data:`. | ✅ |
| 20 (bonus) | Audit/cost/pairing DBs never wired to the persistent Volume | **Inv 7** + **Inv 8** — durability; no attacker action required, any redeploy/crash/container-recycle wipes state. | Three modules share `GLC_CONFIG_DIR` as a fallback instead of each hardcoding `~/.glc`. | ✅ |

Detailed before/after evidence, test names, and residual-risk reasoning for
every row above lives in `FINDINGS_DETAIL.md`.
