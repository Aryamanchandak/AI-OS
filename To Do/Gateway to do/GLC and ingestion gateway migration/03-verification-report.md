# Plan 03 — Implementation Verification Report

Verified 2026-09-21 against `gateway/src/gateway/**` (uncommitted) and `glc_v5/` (unchanged, clean).

## Verdict: substantial and clean, but NOT verified against Plan 03

54 gateway tests pass, `mypy --strict` is clean (35 files), and the legacy `glc_v5` tree is untouched, so rollback is intact.
Five items block a "verified" verdict: 1–4 below and the missing cache fail-hard (#5).

## Blocking findings

1. **Policy engine: list-valued conditions no longer match (fail-open).**
   Original `_matches_condition` has `elif isinstance(expected, list): params.get(key) not in expected`. `policy/engine.py:_matches` has no such branch, so `{mode: [rm, del]}` compares `"rm" != [...]` and the deny rule is skipped.
   Probe: original → `deny`, gateway → `allow`. No shipped rule in `config/policy.yaml` uses this form, so impact is latent, but a user-authored deny rule would silently not fire.
2. **Policy engine: backslash normalization dropped.**
   Original `_normalize_path_for_glob` did `expanduser` and `.replace("\\", "/")`, with a comment explaining the bypass it closes. The new code keeps only `expanduser`.
   Probe: `\home\u\Documents\x` vs rule `/home/u/Documents/**` → original `deny`, gateway `allow`.
3. **Audit "fail-closed" holds at the store, not at the route.** Every control route applies its effect and then audits. With audit down (probe):
   - `/pair` → 500, but the pending code is persisted.
   - `/reload-policy` → 500, but the policy is already swapped.
   - `/kill` → 500, but `glc_enabled` is already `False`.

   That is effect applied, caller sees an error, no audit record. WP D required a deliberate policy and a test of it. `test_audit_is_append_only_and_fail_closed` only asserts `AuditStore.append` raises.
4. **SIGHUP reload failure escapes the signal handler.** Live uvicorn run: a malformed `policy.yaml` on `kill -HUP` raises `ValueError` from `_ceval_process_signals`. The server survives and keeps the old policy (atomic reload works), but the original caught and logged this. A failed reload is also not audited, and a successful SIGHUP reload is (`trigger: sighup`), so decision #3's API-vs-signal audit question is only half-settled.
5. **Cache fail-hard row is unimplemented behind a test that fakes it.**
   `test_broken_runtime_dependency_refuses_startup_and_names_it` parametrizes `["semantic cache", "telemetry export"]` but injects `StartupCheck(name, broken)` itself, so it only proves the harness re-raises a caller-supplied lambda. No cache exists anywhere in `src/gateway/`. The telemetry case is genuinely covered by `test_configured_unreachable_telemetry_target_fails_real_startup`.
   `budgets.yaml` is also never loaded, so decision #2's "stays fail-hard" row has no implementation. These two may be intentionally deferred to Plan 04, but the plan does not say so.

## Plan items not done or not evidenced

- **WP A: no history-preserving import.** `git log --follow -- gateway/src/gateway/audit/store.py` returns nothing; `src/`, `tests/`, `config/` are untracked; no `git filter-repo` pass happened. The confirmed checkbox is unimplemented and `git blame` on moved code will have no GLC history.
- **WP C: "existing security tests pass unchanged" cannot hold.** GLC has about 1,070 lines across 10 security/audit/policy/telemetry test files. The gateway has 13 new tests in one file. The APIs were re-shaped (singletons → instances, `allowed()` → `Allowlist`, `PolicyEngine(config)` → `(path, config)`), so the originals cannot run. The characterization tests were rewritten rather than carried over, which is why #1 and #2 escaped. Not covered: allowlist, trust classification, pairing TTL/expiry, policy matcher hardening, and rate-limit config.
- **WP D: the loopback-only kill guard is not tested.** The only kill test sets `GLC_KILL_ALLOW_REMOTE=1`. The guard itself works (a probe with the default client host `testclient` gave 403).
- **Decision #3 verify:** the reload test asserts 200 and an audit row, not that policy decisions changed. There is no SIGHUP test.
- **Decision #2 methodology:** no artifact for the grep inventory of fail-soft sites or the per-conversion 563-test re-run.
- **Decision #1:** the budget and cache SQLite files were not relocated or audited. No dead-table audit artifact exists, and `CallLedger._migrate_columns` carries about 15 columns `append()` never writes.
- **WP E:** the four baseline paths in `glc-openapi.json` exist in `gateway/openapi.json` (plus `reload-policy`), but no test replays the baseline contract fixtures against the routes.
- **Dependency-direction test** is a substring grep for `from glc` / `import glc` over gateway source. It does not check retired module paths (the plan's stronger form).

## Lower-severity drift

- Deny reason for a rule with no reason: original `"denied by policy"`, new `"matched rule #N"`.
- Install token moved from `~/.glc/install_token` to `Database/sqlite/glc_install_token`. Beyond what the plan asked, and clients reading the old path will not see it. It is under root-gitignored `/Database/` but does not match `Database/.gitignore` patterns.
- `PairingStore.owners()` and `revoke()` were dropped. Fine as dead-code pruning if nothing calls them, but not documented.
- `Allowlist`, `trust.classify`, and `ssrf` are ported but constructed by nothing in `build_container`, so "Gateway owns security" is currently code hosting rather than enforcement.
- `rate_limiter.configure(channels)` in `build_container` is not wrapped in `_construct`, so a malformed `rate_limits` value gives a raw `ValueError`, not a structured startup error.
- `load_gateway_settings` and `load_service_registry` run after the startup checks and are not covered by the telemetry-close cleanup.
- `DependencyContainer.close()` docstring is stale ("Plan 02 has no non-legacy closeable resource").

## Confirmed working

- DB relocation: a fresh boot with an empty `HOME` and no `GLC_*` vars did not create `~/.glc`; files land in `Database/sqlite/`.
- Domain-owned separate SQLite files with shared connection/migration primitives.
- Fail-fast on malformed `policy.yaml`, with a structured JSON `StartupDependencyError` naming the dependency.
- Real unreachable OTLP endpoint refuses startup.
- Policy reload is atomic on an invalid replacement. Live SIGHUP with a valid file reloaded and audited.
- `/v1/control/*` 401/403/404/400 shapes preserved. The loopback kill guard works.
- Allowlist defaults match the original (unlisted channel → `enabled: True`).
- No `glc.*` imports in gateway source.
