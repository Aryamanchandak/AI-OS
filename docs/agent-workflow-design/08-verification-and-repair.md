# 08 — Verification and Repair

[Back to macro](00-macro.md) · Status: exploration draft

## Verification authority

Configure project verification commands before dispatch where possible. The controller executes them and captures command, working directory, environment description, commit, timestamps, exit code, output, and test counts when available.

Revised Oct 9 (D-32): Codex reads the failures, diagnoses them, and fixes them, and it may run tests itself while it works. The controller's run is still the only record: an agent saying “all pass” is not evidence. **Revised Oct 10 (D-46):** after the agent says done, the controller runs the test command itself (a plain shell command, no AI usage) and records the result in the morning summary; if it fails, the output goes to round 1 Codex, then round 2 Claude. The suite always runs in the `check/` workspace, where the hidden independent tests and the code are combined (D-30, [06](06-workspaces-and-integration.md)).

An agent's successful execution status is distinct from a passing test suite. Also detect zero collected tests, unexpected skips, and setup failures. Preserve existing tests alongside new tests.

> **✅ DECISION C3 — Per-repository runner profile, proven during the day** (accepted Oct 9; details to work through)  
> **Problem:** fresh sandboxed workspaces lacked dependencies, `.env`, services, and network, so checks could fail at setup overnight.  
> **Fix:** Each repository declares one **runner profile**: setup command, an env file of **non-secret placeholder values** (never real secrets), services to start (for example Docker Compose), check commands, a feature-exercise command, and any network hosts the checks need. Refinement runs the profile once in a fresh workspace and records the baseline, so setup problems appear during the day. A plan cannot be queued until its profile has passed this dry run. Feature exercise means the controller runs the declared command and captures its output; agent claims of having tried something stay labelled agent-reported. The first trial uses a CLI, library, or API repository; UI exercise is deferred.

## Layered checks

Select checks appropriate to the repository: formatting or lint, type checks, focused tests, integration tests, regression suite, build, and product acceptance checks. UI or external-system behavior may need additional evidence or a declared manual check.

Map criteria to tests and other evidence. A mapping helps identify missing coverage; it does not prove that the tests correctly assert the requirement.

## Execution order and feature acceptance

Combine changes and run fast checks before independent review. Confirm new and existing tests are discovered in their normal project locations. During repair, use focused checks; before finalization run the required final set. Exercise actual user flows where feasible and supply runnable instructions and evidence. Automation may miss usability and product-fit problems. Track human acceptance separately, hold dependent work when its edge requires it, and keep main promotion manual.

Refactors need preserved-behavior evidence (keep tests); rewrites need keep, change, and remove tests plus caller-layer checks; see “Test types” in 15. Bug-fix mode is parked (D-26). See [15](15-work-modes.md).

## Top-to-bottom run (D-34)

Your comment: the agents should run the code top to bottom, not just its tests.

- **By day (Plan mode):** each plan declares **end-to-end scenarios**: a command, real inputs (including the plan's important edge cases), and the expected output, covering every feature from entry point to final output. The C3 dry run proves they start on the baseline; change scenarios are expected to fail there.
- **At night, after the checks pass:** the controller runs each scenario in `check/` and captures command, input, output, and exit code. Then Codex drives the program through the same scenarios and anything else the plan implies, and its transcript is kept labelled *agent-run*.
- **On failure:** it is a finding with evidence and returns to the repair loop if rounds are left; otherwise it is reported as failed.
- **Browser-driven checks (Oct 10):** Codex driving Chrome may be blocked by its sandbox. The permission reviewer (D-50) lets truly safe actions through, and a daytime run window lets you watch (D-41). What to do with verification that stays blocked is parked for you ([17](17-later.md) L17).
- **Scope:** CLI, library, and API projects. Driving a UI is deferred ([17](17-later.md) L14).

This builds on the C3 feature-exercise command; the change is that scenarios are per plan, cover every feature, and are required before a plan can be queued.

## Failure classification

| Failure | Response |
| --- | --- |
| Environment or dependency failure | Repair setup within scope or block with evidence |
| Implementation defect | Fix code and add or strengthen regression evidence |
| Test defect | Correct test against the contract and obtain review |
| Contract ambiguity | Interpret, proceed, and record the interpretation for the report (D-29); a frozen test overrides any interpretation |
| Baseline defect | Report separately; apply the configured regression policy |
| Flaky behavior | Investigate and report instability; retries do not erase evidence |
| Integration conflict | Resolve, review the resolution, and rerun checks |

## Repair loop

**Revised Oct 10 (D-46):** at most **2 rounds**, only when the controller's test run fails: round 1 Codex, round 2 Claude, alternating so each vendor gets a look without overspending usage. This replaces the finder-fixes routing below and the 3-round default. What happens if tests still fail after round 2 is open ([17](17-later.md) L17).

Revised Oct 9 (D-32), **the finder fixes**: a failure in the test suite goes to Codex; a finding goes to the agent that raised and verified it (Codex's completeness findings to Codex). Failures of the new missing tests go to the implementing Claude session, since the missing-tests session only adds tests (D-37). Those tests are not yet approved by you, so if Claude believes one is wrong it files a test dispute: the test is marked `disputed` in the coverage ledger, stops gating the plan, and is listed for you. Your approved frozen tests can never be disputed out of the gate. No hand-over to the other vendor for review. Capture failure evidence, diagnose, apply the fix, produce a new receipt; the controller reruns focused checks, then the required final verification set, and that rerun is the verification. Missing plan items are defects here, not questions (D-33).

Prevent completion through removing meaningful assertions, skipping failing tests, or changing expected behavior without contract justification. Such changes require explicit rationale and review.

> **✅ DECISION C2 — Detect test weakening mechanically** (accepted Oct 9; details to work through)  
> **Problem:** weakening a test was forbidden but nothing detected it.  
> **Fix:** Existing tests and frozen acceptance tests are protected paths. The controller's diff check flags (a) any edit to or deletion of a protected test file, (b) newly added skip/xfail/only markers, and (c) a fall in the collected-test count, or any test that ran before and no longer runs, compared with the baseline. Edits and deletions settled during hardening (rewrites for “change” behavior, pre-approved deletions for “remove” behavior, D-27) are not flagged. Revised Oct 9 (D-37): **any other flagged change is rejected outright at night; there is no approval path.** An agent that believes a test is wrong files a **test dispute**: the criterion ID and why the test is wrong against the plan. The dispute goes in the report for you; the test is left untouched and keeps counting. You approve the change in the morning, and it enters as a plan revision. The C2 check applies to every agent, including Codex, which wrote the tests. Test-change requests appear in the report.

> **Parked for v1 (Oct 10, D-47):** the mechanical check is not built in v1. Instead every fix and missing-test prompt says: do not edit, delete, or skip existing tests; put any dispute in your change receipt. Bring the check back if agents ignore the instruction ([17](17-later.md) L18).

Default (D-46): two repair rounds per plan, alternating Codex then Claude. Define one round as a diagnosis-and-patch cycle followed by verification. Give infrastructure retries a separate small limit so intermittent process failures do not obscure the repair count.

## No-progress repairs and upstream corrections

Record failure signatures, attempted hypotheses, and whether evidence changed. Repeated failure without progress requires a different diagnosis, optionally a bounded other-vendor critique, or a preserved blocker. Infrastructure retries remain separately limited. Unresolved product semantics never become indefinite agent debate or a pause: a test settles them if one exists; otherwise the implementer's interpretation stands and leads the report (D-29).

A foundational fix requires inspection of affected lower layers and consumers, not only the top-level symptom. Invalidate affected evidence on plan or checkpoint changes even when Git finds no conflict; rerun relevant checks and required final verification.

## Final gate

The exact final commit must satisfy all required checks and finding dispositions. If checks cannot run, report the plan as unverified or blocked according to policy. Preserve logs explaining why.

## Exploration

- What checks must every repository supply?
- How are known baseline failures handled?
- Which skipped tests are acceptable?
- What evidence should close a review finding?
