# Plan 03 — Implementation Verification Report

First pass: 2026-09-21. Updated 2026-09-22 after fixing the blockers found in the first pass.
Commits: `73419ee` (checkpoint of what was already implemented), `f3f579e`, `2afc664`, `ed0c9cf` (fixes).

## Current verdict

**5 of 5 blockers from the first pass are fixed and verified.** 88 gateway tests pass (up from 54 — 34 new,
including ported GLC characterization tests), `mypy --strict` is clean (69 files), and the legacy `glc_v5`
tree is untouched, so rollback is intact.

**Two items remain and need a decision from you, not more automated fixing** — see "Needs your decision" below.
Everything else is either fixed, or a documented, intentional out-of-scope call.

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

## Needs your decision (not fixed, because they're genuine choices, not bugs)

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
line the plan explicitly confirmed. **I have not run `git filter-repo` — it rewrites history and I won't do
that without you choosing (a).**

### B. Two rows in decision #2's fail-fast table don't match what's actually in scope or in the code

- **Semantic cache "fail-hard" row is unimplementable under Plan 03 as scoped.** The Goal section's confirmed
  import-path list (`glc/config.py`, `glc/db.py`, `glc/audit/`, `glc/security/`, `glc/policy/`,
  `glc/routes/control.py`) does not include `glc/cache/`. Decision #2's table commits to converting the
  semantic cache to fail-hard anyway — that's a self-contradiction in the plan, not something Plan 03's code
  can satisfy without importing code the Goal section said not to import yet. Given the cache sits on the chat
  request path, it more naturally belongs to whichever plan imports chat (Plan 04, which I can see is already
  under way in this repo — `src/gateway/llm/` exists). **Recommend:** strike or reassign that table row to
  Plan 04 rather than leaving it as an unmet Plan 03 commitment. I did not implement a cache module to satisfy
  it — building one to pass a test would be exactly the "verification theater" the first pass flagged.
- **`budgets.yaml` table row says "fail-hard already" — that's not what the GLC source does.** In
  `glc_v5/glc/main.py`, `_boot_economics` catches a broken `budgets.yaml`, sets `config_errors["budgets.yaml"]`,
  disables the budget controller, and boots anyway ("budget enforcement is OFF"). That's fail-soft today, not
  fail-hard, so the table's premise is factually wrong about current behavior. This doesn't block anything in
  Plan 03 (budgets isn't imported either, same reasoning as cache), but the table should be corrected so it
  doesn't misstate GLC's current behavior for whoever picks this up in Plan 04.

I'd suggest a short edit to `03-glc-platform-security-audit-control.md`'s decision #2 table (drop or
reassign the cache row, fix the budgets row's "today" column) rather than me editing the plan document
myself — that's a plan-content call, not an implementation one.

## Still-open items from the first pass, unchanged (not blockers, listed for completeness)

- **WP D "define kill/presence/pairing within the unified Gateway lifecycle"**: done functionally
  (`suspend_glc` flips a flag, doesn't terminate the process) but there's no test asserting ingestion/shell
  routes stay reachable after a kill — only that `/health` does.
- **Decision #1**: budget and cache SQLite files were not relocated (they don't exist in this tree — same
  scope question as item B above). No dead-table audit artifact exists for the ledger's ~15
  `_migrate_columns` columns that `append()` never writes.
- **WP E**: the four baseline control routes exist in `gateway/openapi.json`, but no test replays
  `migration/baseline/contracts/glc-openapi.json`'s fixtures against them directly.
- **Dependency-direction test** is a substring grep for `from glc`/`import glc`, not a check for retired
  module paths (the plan's stronger form). Low priority — the retired `glc.*` modules still exist untouched
  in `glc_v5/` under WP A's own recommended reading (standalone copy stays, only the *merged* copy retires).

## Confirmed working (re-verified this pass)

- Fresh boot with empty `HOME`, no `GLC_*` env vars: no `~/.glc/*` created; databases land in `Database/sqlite/`.
- Fail-fast on malformed `policy.yaml`, unreachable OTel endpoint, and (new) malformed `channels.yaml`
  rate-limit config — all raise structured `gateway.startup.dependency_failed` events.
- Policy reload is atomic on an invalid replacement; live SIGHUP with a valid file still reloads and audits
  correctly; live SIGHUP with an invalid file no longer crashes and leaves the old policy in place.
- `/v1/control/*` 401/403/404/400 shapes preserved; loopback-only kill guard verified rejecting directly (not
  just via a passing config).
- No `glc.*` imports anywhere in `src/gateway`.
- 88/89 gateway tests pass; the one failure (`test_committed_typescript_schema_is_current`) predates this
  work, is unrelated to Plan 03 (a stale generated TypeScript file under `shell/`), and reproduces identically
  on the pre-fix commit.
