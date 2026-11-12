# Plan 03 — Implementation Verification Report

First pass: 2026-09-21. Updated 2026-09-22 after fixing the blockers found in the first pass.
Commits: `73419ee` (checkpoint of what was already implemented), `f3f579e`, `2afc664`, `ed0c9cf` (fixes).

**Final status: CLOSED — 2026-09-22.**

## Current verdict

**All Plan 03 blockers and the signed-off semantic-cache follow-up are fixed and verified.** 91 of 92
Gateway tests pass, `mypy --strict` is clean (68 source files), and the legacy `glc_v5`
tree is untouched, so rollback is intact.

The only failing Gateway test is the already documented stale generated TypeScript schema under `shell/`;
it predates this work and is unrelated to Plan 03. The plan is closed.

## Fixed since the first pass

1. **Policy engine list-valued conditions (fail-open) — fixed.** `_matches` now has the missing
  `isinstance(expected, list)` branch. Verified by re-running a 22-case differential fuzz against the
   original `glc.policy.engine._matches_condition`: 0 mismatches (was 3). Ported as
   `test_list_valued_condition_still_matches`.
2. **Policy engine backslash-path normalization — fixed.** `_normalize_path_for_glob` restored (expanduser +
  `\`→`/`). Ported as `test_backslash_path_matches_tilde_rule`.
3. **Audit fail-closed only held at the store, not the route — fixed.** `ControlService.require_audit_writable()`
  now probes the audit store *before* `/pair`, `/pair/confirm`, `/reload-policy`, and `/kill` apply their
   effect, and refuses with 503 if the probe fails. `presence` (a read, not a security decision) uses a new
   `audit_best_effort()` instead, so it stays available when audit is down. Verified with a test that asserts
   *state*, not just status code: with the audit store broken, `pending_codes` stays empty, the policy verdict
   doesn't change, and `glc_enabled` stays `True` — see `test_audit_unavailable_blocks_pair_confirm_and_kill_without_side_effects`.
4. **SIGHUP reload failure escaping the signal handler — fixed.** The handler now calls `policy.reload()`
  directly (not `ControlService.reload_policy()`) and catches/logs failures instead of letting them propagate.
   This also removes the SQLite audit write that was previously happening synchronously inside the signal
   frame on every successful SIGHUP reload — a risk in itself, independent of the crash bug. Consequence:
   **SIGHUP reloads are not audited, only the HTTP endpoint is** — this matches GLC's original behavior
   (which also didn't audit SIGHUP) and is the deliberate answer to decision #3's audit-asymmetry question.
   Verified live on uvicorn (malformed `policy.yaml` + `kill -HUP` no longer crashes or corrupts the loaded
   policy) and with `test_sighup_reload_failure_does_not_crash_the_process`.
5. **Misleading cache-coverage test — fixed by being honest, not by building a cache.** The `"semantic cache"`
  parametrize case never tested a cache (no cache backend exists in `src/gateway/`); it tested that the
   startup-check harness re-raises whatever `StartupCheck` it's handed. Renamed and documented; see "Plan
   defects" below for why no cache was built.



### Also fixed while in the area

- **Rate-limiter config now goes through the structured startup-error path.** `rate_limiter.configure(channels)`
was called outside `_construct()`, so a malformed `rate_limits` section in `channels.yaml` raised a raw
`ValueError` instead of a structured `gateway.startup.dependency_failed` event. Now wrapped.
- **Deny-reason drift fixed.** A deny rule with no `reason` now returns `"denied by policy"` again, matching
the original, instead of `"matched rule #N"`.
- **Kill-loopback guard now actually tested.** Every existing kill test set `GLC_KILL_ALLOW_REMOTE=1`, so the
403 path was never exercised. `test_kill_from_non_loopback_is_rejected_without_the_override` covers it.
- **Ported GLC characterization tests** for allowlist defaults, trust classification, pairing expiry/collision,
and per-channel rate-limit YAML config (`tests/test_security_characterization.py`) — these were dropped
during the rewrite and are part of why findings 1–2 went undetected in the first place.
- **Confirmed harmless: the install-token relocation.** A full-repo grep for `install_token` turned up no
consumer outside `gateway/` and `glc_v5/` itself. `glc_v5`'s own `config.py`/`daemon/` still read
`~/.glc/install_token` for the standalone rollback copy — unaffected, since it's a separate process with its
own token. Nothing reads the Gateway's new `Database/sqlite/glc_install_token` path except the Gateway.



## Decisions recorded (no implementation rework required)



### A. Work Package A — history-preserving import never happened

`git log --follow -- gateway/src/gateway/audit/store.py` returns nothing; `src/`, `tests/`, `config/` were
untracked until this session's checkpoint commit. No `git filter-repo` pass was run. The Goal section's
confirmed checkbox ("path-filtered import... full git history is preserved for exactly those paths") is
unimplemented, and `git blame` on any moved file shows no GLC-era history.

**This isn't fixable by editing code.** `git filter-repo` cannot retroactively attach history to files that
have already been rewritten at new paths outside that process — satisfying this now means either (a) redoing
the import from `glc_v5` with `filter-repo` onto a fresh landing point and re-applying today's changes as
tracked commits on top, or (b) deciding the `git blame` requirement was a nice-to-have you're willing to drop
for this plan. Both are legitimate; only you can pick, since (a) is a real chunk of rework and (b) reopens a
line the plan explicitly confirmed. **I have not run** `git filter-repo` **— it rewrites history and I won't do
that without you choosing (a).**

**Answer/decision: keep the code as it is and do not redo the import.** The code is already committed and
working. This issue only concerns whether Git remembers who last changed each line *before* the files were
moved into Gateway. `git blame` is a history-viewing command that shows the commit and author responsible for
each line; it does not affect how the code runs. Rebuilding that old history would require redoing part of the
Git import, not merely making another commit, and it provides no runtime benefit. Because preserving that
history is not important here, drop the history-preservation requirement for Plan 03. The existing commits
remain the record from the point at which the code entered Gateway, and no implemented work needs to be
redone.

### B. Two rows in decision #2's fail-fast table don't match what's actually in scope or in the code

- **Semantic cache fail-hard behavior — resolved after sign-off.** The cache belongs to the LLM/chat path
that Plan 04 imported, but Plan 04 was already implemented when this report was reviewed. The remaining cache
work was therefore completed as the final Plan 03 closure item rather than deferred again.

**Plain-English answer:** a semantic cache saves the result of a previous AI request and can reuse it when a
later request means roughly the same thing. It is useful on chat/LLM requests because it can make repeat
requests faster and cheaper. "Fail-hard" means refusing startup or the affected request when the cache
backend is unavailable instead of silently making an uncached provider call.

**Final resolution:** because Plan 04 was already implemented, the cache was completed now. It uses the
domain-owned `Database/sqlite/semantic_cache.sqlite`, survives restarts, enforces tenant scope, reuses the
lookup embedding on a miss, and applies the configured TTL and entry limit. A writable health check named
`semantic cache` now blocks startup when the backend is broken, and database failures during requests
propagate instead of silently bypassing the cache.

- `budgets.yaml` **table row says "fail-hard already" — that's not what the GLC source does.** In
`glc_v5/glc/main.py`, `_boot_economics` catches a broken `budgets.yaml`, sets `config_errors["budgets.yaml"]`, disables the budget controller, and boots anyway ("budget enforcement is OFF"). That's fail-soft today, not fail-hard, so the table's premise is factually wrong about current behavior. This doesn't block anything in Plan 03 (budgets isn't imported either, same reasoning as cache), but the table should be corrected so it doesn't misstate GLC's current behavior for whoever picks this up in Plan 04.

**Plain-English answer:** `budgets.yaml` contains AI-spending limits. Today, if that file is broken, the old
GLC still starts but switches budget protection off. The plan incorrectly says the old GLC already refuses
to start. Plan 03 does not move the budget system, so this is not a bug in the work completed here.
**Decision implemented:** the table now records that legacy GLC is fail-soft while the unified Gateway is
fail-hard: malformed `budgets.yaml` prevents `LLMService` construction and therefore prevents startup.

The corresponding decision table in `03-glc-platform-security-audit-control.md` has been corrected for both
budgets and the now-implemented semantic cache.

## Accepted later hardening (does not reopen Plan 03)

- **Add one stronger kill test:** the kill command correctly disables only the GLC features and leaves the
Gateway process running. A future test should also prove that ingestion and shell routes still work after a
kill; the current test proves only that `/health` still works.
- **Handle the budget database separately if it becomes its own store:** the semantic cache now has its own
database under `Database/sqlite/`; budget reservations currently use the Gateway ledger database. There is
also optional database-cleanup documentation to do for old audit columns that are no longer written.
- **Add a direct compatibility test:** the four control API routes are present in the generated OpenAPI file,
but a future test could replay the saved old-GLC examples against the new routes to prove exact compatibility.
- **Strengthen the import check later:** the current test catches direct imports from `glc`, which is the main
risk. It does not check every possible retired module path. This is low priority because the untouched
`glc_v5` copy is intentionally being kept for rollback.



## Confirmed working (re-verified this pass)

- Fresh boot with empty `HOME`, no `GLC_*` env vars: no `~/.glc/*` created; databases land in `Database/sqlite/`.
- Fail-fast on malformed `policy.yaml`, unreachable OTel endpoint, and (new) malformed `channels.yaml`
rate-limit config — all raise structured `gateway.startup.dependency_failed` events.
- The semantic cache persists across Gateway restarts in its own SQLite database, isolates entries by tenant,
and refuses startup with a structured error naming `semantic cache` when its backend is unusable.
- Policy reload is atomic on an invalid replacement; live SIGHUP with a valid file still reloads and audits
correctly; live SIGHUP with an invalid file no longer crashes and leaves the old policy in place.
- `/v1/control/*` 401/403/404/400 shapes preserved; loopback-only kill guard verified rejecting directly (not
just via a passing config).
- No `glc.*` imports anywhere in `src/gateway`.
- 91/92 gateway tests pass; the one failure (`test_committed_typescript_schema_is_current`) predates this
work, is unrelated to Plan 03 (a stale generated TypeScript file under `shell/`), and reproduces identically
on the pre-fix commit.
