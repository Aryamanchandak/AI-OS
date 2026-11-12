# Plan 07 — Implementation Verification Report

**Update 2026-09-28 — CLOSED.** Everything in "Bottom line" below is
resolved: `gateway/openapi.json` was regenerated and the stale test fixed
(committed `3714e50`); `plan-07-openapi-audit.md` and
`plan-07-cutover-status.md` were refreshed to describe the current tree;
`migration/baseline/caller-inventory.md` got its Plan 07 resolution table;
all four decisions are now recorded with checkboxes and rationale directly
in `07-runtime-cutover-and-legacy-removal.md`'s "Aryaman's comments"
section. Decision #4 (archival) was executed: both submodules were pushed
to their own remotes first (glc_v5: 2 commits, ingestion-pipeline: 6
commits — neither was lost), tagged here as `plan-07-pre-legacy-removal`
(commit `3714e50`), then removed from this repo (`.gitmodules` and both
working directories, commit `e718668`). Re-verified *after* removal, not
just before: Gateway actually boots with neither sibling directory present
(`TestClient` hit `/health` and `/healthz` for real), the full suite still
passes (892 passed, 5 skipped, 0 failed), and mypy --strict is clean across
279 files. Both commits and the tag are pushed to `origin/main`. The rest
of this report is left as originally written, as the record of what was
found before the fix pass — see "Bottom line" for the point-by-point
before/after.

---

Verified 2026-09-27. Nothing in this report has been committed by me; the
current commit is still `3e19fc2` ("Plan 05: close out the verification
report"). All Plan 07 work — code and docs alike — exists only in the
working tree (`git status`: dozens of modified files, plus untracked
`gateway/src/gateway/compatibility/`, `gateway/src/gateway/ingestion/`,
`gateway/ingestion_tests/`, `gateway/scripts/`, `migration/plan-07-*.md`,
and more).

**Status: OPEN, not CLOSED.** Substantial real work exists and most of it
holds up under independent re-testing, but the plan's own decisions were
never recorded as decisions, two tests fail on a clean re-run, one entire
decision (archival) was never acted on, and the exit gate's own final check
("a fresh clone... builds, tests, and runs with no reference anywhere to
`glc_v5`, `ingestion-pipeline`, `glc.main`, or port 8111") cannot pass —
nothing is pushed, and both submodules and `glc.main`'s entry point still
exist untouched.

## Important framing note before the rest of this report

A file already exists at `migration/plan-07-cutover-status.md`, written by
whoever implemented this plan, that **renegotiates the plan's own scope**:
it withdraws the observation-window requirement ("an assistant-added
assumption... has been withdrawn"), declares external-caller migration "not
a blocker," and calls the still-present submodules "a publication/versioning
issue, not a failure." It opens with "Scope agreed on 2026-09-25."

I can't confirm that agreement from the repo. The plan file itself
(`07-runtime-cutover-and-legacy-removal.md`) still has all four decisions'
checkboxes unchecked (`- [ ]` throughout), and its "Aryaman's comments"
section — the place decisions like this belong — is empty. So this report
grades against the plan as written, not against the status doc's
self-issued rescoping, and calls out every place the two disagree. That's a
decision for you to make explicitly, not one to accept by default because
an implementation note asserts it.

## What I independently re-ran (not just re-read)

| Check | Result |
| --- | --- |
| `gateway/.venv/bin/python -m pytest -q` (full suite) | **878 passed, 5 skipped, 2 FAILED** — not the "880 passed, 5 skipped" the status doc claims |
| `gateway/.venv/bin/python -m mypy --config-file mypy.ini main.py src/gateway` | Success, 279 source files |
| `gateway/.venv/bin/python -m mypy --strict src/gateway/ingestion/server.py` | Success |
| Shell `npx tsc -b` | Passed, no errors |
| Shell `npx vite build` | Passed |
| Shell `npx vitest run` | **122/122 passed**, 11 files — matches the status doc |
| `grep -rn "8111"` outside `glc_v5/`, `ingestion-pipeline/`, `build/` | Only config values (`gateway/config/services.yaml`) and tests that assert against those config values — no hard-coded literal in Gateway's own runtime code |
| `grep` for `glc.client`/`glc_v5` imports outside `glc_v5/` | Zero *runtime* imports; the one hit, `gateway/ingestion_tests/test_glc_policy.py:155`, is a string literal inside an AST-based architecture guard (it scans *other* files for the string, doesn't import it itself); `test_glc_contract.py` came up clean on grep and, read directly, imports `gateway.ingestion.http_client` — Gateway's own client, not `glc.client` |
| `git submodule status` | Both `glc_v5` and `ingestion-pipeline` still listed |
| `glc_v5/glc/main.py` | `if __name__ == "__main__": uvicorn.run("glc.main:app", ...)` entry point and `PORT = os.getenv("GLC_PORT", "8111")` are untouched |
| `gateway/src/gateway/platform/configuration/glc.py` | Still reads `GLC_GATEWAY_DB`, `GLC_AUDIT_DB`, `GLC_POLICY_YAML`, etc. as live env-var overrides |

### The single root cause behind both failures — and behind the stale audit doc

878 passed + 2 failed = 880 — the exact count `plan-07-cutover-status.md`
reports as "880 passed" on 2026-09-25. Same suite, nothing added or removed;
two tests that passed then fail now. Combined with the committed
`openapi.json` being stale against the live app, and with
`migration/plan-07-openapi-audit.md`'s "genuine missing capability" list
being *wrong*, not just unapproved (see below), this isn't three unrelated
defects — it's one timeline gap: **real implementation work landed in this
working tree after the 2026-09-25 verification snapshot, and none of the
verification artifacts (the committed `openapi.json`, the audit doc, the
cutover-status test count) were regenerated against it.** Every number in
`plan-07-cutover-status.md` should be treated as "true as of 2026-09-25,"
not "true now."

**1. `test_contract_staleness.py::test_committed_openapi_schema_is_current`**
— the committed `gateway/openapi.json` no longer matches `app.openapi()`.
Trivial fix (`python export_openapi.py`), but the "Required final
verification" bullet "OpenAPI comparison with intentional differences
approved" is not satisfied right now — the artifact this repo would ship is
stale.

**2. `tests/test_foundation.py::test_missing_api_routes_do_not_fall_through_to_shell`**
— expects `GET /v1/refusals` and `GET /v1/traces/recent` to return **404**
for an unauthenticated request; they return **401**. I initially read this
as an ambiguous middleware-vs-test disagreement. It isn't: I dumped the live
app's actual OpenAPI schema (`app.openapi()`, not a naive `app.routes` walk —
FastAPI's newer route-group wrapping hides included routers from a shallow
walk) and confirmed **both paths are real, registered, working routes** —
`gateway/src/gateway/platform/observability/routes.py` implements
`GET /v1/refusals`, `GET /v1/traces/recent`, `GET /v1/traces/{trace_id}`, and
`GET /v1/observability/agent_trace/{run_id}` (plus `/api/observability/*`
equivalents), all wired into `router_registry.py`. `src/gateway/app/middleware.py`'s
`requires_bearer_token()` correctly gates them — a 401 for a missing bearer
token on a real protected route is the *right* answer. **The test is
outdated, not the middleware.** It was written when these were genuinely
missing routes (matching what the audit doc still claims); someone
implemented them afterward and never updated this test or the audit doc to
match. Fix: update the test to exercise two paths that are *actually*
missing (or drop these two from it), not the middleware.

**This also means `migration/plan-07-openapi-audit.md` is comprehensively
stale, not just on `/dashboard` (below).** I checked its full "genuine
missing capability" list against the live `app.openapi()` schema directly:

| Audit doc says | Live schema actually has |
| --- | --- |
| `POST /v1/preflight` — "no route invokes chat and embedding readiness probes" | `POST /v1/preflight` **and** `POST /api/llm/preflight`, both registered (`gateway/src/gateway/llm/api/routes.py:43`) |
| `GET /v1/traces/recent` — "no equivalent... ring or read route" | Implemented, `platform/observability/routes.py:18` |
| `GET /v1/traces/{trace_id}` — same | Implemented, same file |
| `GET /v1/refusals` — "no 402-refusal recorder or read route" | Implemented, same file |
| `GET /v1/observability/agent_trace/{run_id}` — "no agent-trace proxy route" | Implemented, same file, proxies to `agent_runtime` via the service registry |
| `POST /v1/channels/{name}/send` — "genuine missing proactive channel-send capability" | Implemented, `gateway/src/gateway/channels/routes.py:26` |
| `GET /dashboard` — "wrong screen... needs redirect or deliberate retirement" | Already a `307` redirect to `/observability` (`src/gateway/app/main.py:73-75`) |

Every item the audit doc lists as an open decision or a genuine gap is
closed in code. This is good news about how much of the plan is actually
done — but it means neither the audit doc nor the cutover-status doc can be
read as a current statement of what's missing. Both need regenerating
before either is trusted again.

## Decision-by-decision (plan text vs. current repo state)

**1. Final process model — matches the plan's proposed default, but was
never checked off.** `gateway/config/services.yaml` registers one
`gateway` service (port 8000, required) plus `glc_legacy` (8111, optional),
`agent_runtime` (8113), and a disabled `telegram_worker` (8121) — one
process plus explicitly configured workers, exactly the plan's first
option. Port 8000 is kept as a documented deliberate exception (comment in
`services.yaml`), consistent with the plan's port note. **Not recorded**:
the plan's own checkbox for this decision.

**2. Port 8111 transition — implemented as a fourth option the plan didn't
offer, without being recorded as a decision.** The plan's three checkboxes
are "observed-usage cutover," "fixed-date removal," or "keep permanently."
What exists is a fourth model: an optional, off-by-default-unless-configured
proxy (`gateway/src/gateway/compatibility/legacy_listener.py`) that forwards
HTTP/SSE/WebSocket to Gateway and logs only connection metadata (never
path, headers, or body) — verified by reading the code, not just the test.
`migration/plan-07-cutover-status.md` explicitly withdraws the observation
window this decision's "how you'll verify this landed" section depends on
("the observation window's logs... show zero connections... before it's
removed"). No observation window has run; no connection-count report
exists. If "keep 8111 as an optional, always-available compatibility
listener with no sunset" is the actual intended decision, it should be
written into the plan file's decision #2, not left implicit in a separate
status note.

**3. Legacy Python imports — the plan's own stated verification passes,**
but the decision itself is still unchecked. `grep -rn "^import glc\|^from
glc" gateway/src` — zero hits. Repo-wide `glc\.client\|glc_v5` outside
`glc_v5/` — zero *runtime* hits (the two test-file hits are an import-path
string in a docstring and an AST scan target, not an import statement).
`glc_v5/glc/client.py` itself has **not** been removed — it's still fully
present and working, which is one of the two valid choices this decision
offers ("retain... for external callers"), just, again, not recorded as the
chosen one.

**4. Archival policy — not implemented at all, in any of its three forms.**
`.gitmodules` still lists both submodules; `git submodule status` still
shows both at their existing commits; there is no `archive/` directory
anywhere in the repo. None of the three options this decision offers has
been chosen or executed. This is the one decision where "not decided yet"
is the accurate description, not "decided but not recorded."

## Work packages

**A. Service registry authoritative — done.** `gateway/main.py` resolves
its port via `gateway_address()` from the registry, not a literal; the
`8111` grep above turns up nothing hard-coded in Gateway's own runtime code.
Not verified: `glc_v5/daemon/install.sh` and the channel dev scripts under
`glc_v5/glc/channels/catalogue/*` still hard-code `8111` — the plan
explicitly names these as in scope for this work package's "Update
launchd... demo, and local scripts" bullet, and they remain untouched. That
may be an intentional consequence of decision #4 not having removed
`glc_v5` yet (no reason to edit code you're about to delete), but it isn't
stated that way anywhere.

**B. Migrate callers — partially done, and the plan's own record-keeping
step was skipped.** `migration/baseline/caller-inventory.md` (Plan 01's
artifact) is dated 2026-09-14 and still describes ingestion's dependency on
`glc.client` in the present tense as "Active" — it was never updated with
the "migrated" mark and evidence this work package's own done-criterion
requires ("every row... gets a 'migrated' mark and evidence... before this
plan's exit gate"). The migration itself is real (verified: no runtime
`glc.client` import in `gateway/src/gateway/ingestion/`), but the paper
trail the plan asks for doesn't exist.

**C. Compatibility observation — instrumentation and deprecation messaging
both exist; the observation window itself was explicitly skipped, not run.**
The listener logs connection metadata only (verified by reading the code).
`gateway/README.md` documents the cutover story reasonably well: how to
start the legacy listener, that "Gateway itself does not require it," how to
disable `glc_legacy` in the registry, and a real script
(`gateway/scripts/legacy_usage_report.py`) to turn its logs into daily
connection counts — that's genuine progress on this work package's
"publish deprecation messages and final cutover instructions" bullet. What's
still missing is the measurement itself: no no-usage window was defined or
run, and `plan-07-cutover-status.md` states this directly ("The previous
14-day observation requirement... has been withdrawn"). Whether that
rescoping is acceptable is your call, not something the repo state can
settle.

**D. Operational readiness — plausible but not independently re-run by
me.** `gateway/scripts/runtime_cutover_smoke.py` (112 lines) and
`gateway/tests/test_standalone_bootstrap.py` exist and read as genuine cold
start/restart/backup/restore/no-submodule-bootstrap exercises, matching the
specific claims in `plan-07-cutover-status.md`. I did not re-run the smoke
script myself (it kills processes and restores SQLite files in place — real
side effects I didn't want to trigger without asking first). The concurrent
budget/audit/cache/ingestion load test the plan asks for is not evidenced
anywhere I could find beyond the general suite passing.

**E. Remove legacy boundaries — mostly not done, by design (nothing's been
cut over yet), but that means this work package is genuinely incomplete
against the plan text.** Specifically: the 8111 listener is optional
infrastructure, not removed (no exit condition has been reached to remove
it against); `glc.client` compatibility is not removed; `glc.main`'s
`__main__` entry point is not removed; the `GLC_*` env aliases are not
removed — `gateway/src/gateway/platform/configuration/glc.py` still reads
`GLC_GATEWAY_DB`/`GLC_AUDIT_DB`/etc. directly, meaning readers have *not*
all moved to the registry/config system yet, so this work package's own
stated precondition for removing the aliases isn't met either; the
submodules are not removed or archived; legacy documentation has not been
replaced.

## Required final verification — checked against the plan's list

- Gateway/ingestion suite: **878 passed, 5 skipped, 2 failed** (see above) —
  not clean.
- Frontend type/build/test suites: clean (`tsc`, `vite build`, 122 vitest
  tests).
- OpenAPI comparison: the committed `gateway/openapi.json` is currently
  stale against the running app (test failure above), and the audit doc's
  gap list is stale too — I checked all six of its "genuine missing
  capability" items against the live schema directly and every one is now
  implemented (`/v1/preflight`, `/v1/traces/recent`, `/v1/traces/{trace_id}`,
  `/v1/refusals`, `/v1/observability/agent_trace/{run_id}`,
  `/v1/channels/{name}/send`), plus the `/dashboard` redirect. Feature
  coverage is in much better shape than the audit doc suggests; the
  paperwork just hasn't caught up. What's still genuinely unresolved: the
  audit's own caveat that OpenAPI schema matching doesn't prove response-body
  or side-effect equivalence for the 33 originally-shared routes — that
  needs the route-level characterization tests the audit doc calls for,
  independent of this staleness.
- End-to-end chat/SSE/WebSocket/webhook/STT/TTS/budget/cache/audit/ingestion
  tests: covered by the general suite; no live-provider end-to-end run was
  possible or attempted (no external credentials/services on this machine,
  same limitation the status doc already names).
- Search proving no production dependency on `glc_v5`/old ingestion
  package/`glc.main`/copied port 8111: the search comes back clean for
  Gateway's own runtime code, but `glc_v5` and `ingestion-pipeline`
  themselves are still present, still runnable, and still the thing
  `.gitmodules` points at — "no dependency" and "no longer present" are
  different claims, and only the first one is currently true.
- Fresh-machine/bootstrap test: `test_standalone_bootstrap.py` exists and
  exercises this at the file-copy level, but there is nothing to actually
  clone — no commit contains this work.

## Exit gate — checked against the plan's list

- "Unified Gateway is the sole documented application entry point" — not
  fully true: `glc_v5/glc/main.py` is still a working, startable entry
  point; nothing stops someone from running it.
- "Every active caller uses a supported Gateway contract" — true for the
  in-repo callers I could find (ingestion, shell); the caller-inventory
  bookkeeping this claim rests on wasn't updated (Work Package B).
- "Compatibility traffic is zero for the approved observation window" —
  no window was run; this gate item is unmet by the plan's own text,
  explicitly waived by the status doc.
- "Old submodules are unnecessary for build, test, runtime, and operation"
  — plausible (the standalone-bootstrap test suggests Gateway doesn't need
  them present), but not proven by removing them, and they haven't been
  removed.
- "Replacement commits are pushed, tagged, and recoverable before deletion"
  — **false as of this report.** Nothing is committed, nothing is pushed,
  nothing is tagged. This is the most concrete unmet item: even if every
  other gate were satisfied, this one alone means the plan cannot be called
  closed yet.
- "Rollback and backup procedures have been exercised" — the smoke script
  suggests yes for SQLite backup/restore; not independently re-verified by
  me this pass.

## Bottom line

Real, substantial implementation work exists in the working tree, and it's
further along than its own paper trail claims — the process model, the
registry-driven ports, the legacy listener with real deprecation
documentation, and (found only by checking the live schema directly, not by
trusting the audit doc) every route the openapi audit called "genuinely
missing" is actually implemented. But by the plan's own written definition
of done, this is not finished:

1. Everything traces to one cause: real work landed after the 2026-09-25
   verification snapshot and nothing was re-run against it. Regenerate
   `gateway/openapi.json`, update or retire the two stale tests, and refresh
   `plan-07-openapi-audit.md` and `plan-07-cutover-status.md` so they
   describe the current tree instead of last Friday's.
2. None of the four decisions is recorded as decided in the plan file
   itself — only in a separate status note whose authority I can't confirm.
3. Decision #4 (archival) has no implementation at all — both submodules
   remain, unarchived, unremoved.
4. Nothing is committed. The exit gate's explicit final check — a fresh
   clone building and running with no legacy references — is currently
   impossible to satisfy because there is nothing to clone.

I'd treat this as ready for a decision-recording, re-verification, and
cleanup pass, not as closed.
