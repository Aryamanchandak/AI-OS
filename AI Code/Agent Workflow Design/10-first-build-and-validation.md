# 10 — First Build and Validation

[Back to macro](00-macro.md) · Status: exploration draft

## First version

Prove one manually launched cycle before adding an overnight queue: load one detailed plan through a minimal UI, run Plan mode on it, have Codex write the tests before code in a folder Claude cannot see, implement, combine and execute checks, run the completeness pass and missing tests, repair within limits, run the plan top to bottom, do the explain-back, and generate a report with your review pending. Keep minimal durable records and checkpoints.

Use a small repository or contained feature with an established test command. Verify installed agent interfaces, permissions, authentication, and usage reporting before committing to exact adapter behavior.

## v1 build order (Oct 10, D-38 to D-56)

The goal is a usable v1 quickly. Build in this order; everything else below is the fuller target.

1. `run_claude()` / `run_codex()` in script mode with JSON output, in a visible Terminal window; read status, session ID, limit hit (D-39, D-40).
2. The controller loop: plans in sequence in one run clone, commit after every node, ended-vs-done handling, “continue” after a limit, Pause/Resume, run window, `caffeinate`, process-group kill, 2-hour timeout (D-38, D-41 to D-44, D-51, D-52).
3. The controller's own test run and the 2-round alternating repair (D-46).
4. Tests in a separate clone with a deny-read rule; check folder (D-45).
5. Permission reviewer (D-50) and weekly usage check (D-43).
6. Morning summary (D-53).
7. Daytime dry run on a trivial plan (D-54), then the first real run.

Borrow from Omnigent where it saves time, after a license check (D-55).

## Implementation sequence

1. Build a minimal local UI to load a plan, attach files, and set sandbox and working folder ([16](16-plan-ui.md)). Run one hardening session on a plan you wrote.
2. Define minimal plan, checkpoint, finding, and command-result records; generate the readable report from them (coverage ledger parked, D-48).
3. Prepare an isolated candidate and controller-owned verification runner.
4. Connect the two agent roles for one manual implement → combine and check → completeness pass → missing tests → repair cycle, with tests hidden from Claude (D-30, D-31, D-32).
5. Add the top-to-bottom run (D-34) and the explain-back audit on the functions you pick (D-49).
6. Evaluate whether refinement caught useful issues and whether independent review improved the result.
7. Add only the persistence, locks, limits, and interruption handling required for safe unattended execution; exercise them with fake adapters where useful.
8. Add wait-and-continue for usage limits ([09](09-scheduling-and-recovery.md)) and test it with a forced limit.
9. Add scheduled launches, dependency gates, and multiple plans after the core cycle is reliable.

Safety and recovery gates still apply before unattended use. The thinner sequence delays general orchestration machinery, not exact-commit checks or preserved work.

## Evidence needed before overnight use

| Scenario | Expected behavior |
| --- | --- |
| Plan hardening | Agents map your plan to real files, return every open structural decision as a question, and flag untestable criteria |
| Human correction to an upstream plan | Affected descendants and evidence reassessed; original chain preserved |
| Human-gated dependency | Does not dispatch before acceptance |
| Small successful feature | Integrated candidate passes required checks; report links exact commit |
| Deliberately faulty implementation | Independent test catches defect; repair restores expected behavior |
| Frozen tests (C1) | Written by Codex before code; change tests fail, keep tests pass, and remove tests see the old behavior on baseline; unchanged by the implementer; they catch the faulty implementation |
| Pre-approved test deletion (D-27) | Deleting a test listed for a “remove” behavior is accepted; deleting any other test is rejected |
| Test weakened (C2) | *Parked for v1 (D-47).* Later: edited assertion, new skip, or dropped test count is rejected outright at night; the agent's objection appears as a test dispute in the report (D-37) |
| Missing-tests session touches an existing test (D-37) | v1: the prompt forbids it and you see it in the diff and receipt (D-47); later: rejected mechanically |
| Runner profile dry run (C3) | Fresh run clone executes setup and baseline checks during the day; plan not queued until it passes |
| Agent tries a Git write (C4) | Denied; real repository branches unchanged |
| Advisory vs blocking finding (C5) | Finding without criterion and evidence does not consume a repair round |
| Tests hidden from the implementer (D-30) | Claude's clone has no independent test files or commits containing them, before and after the run |
| Plan item left unimplemented by Claude (D-33) | Codex's completeness pass finds and implements it; its receipt shows it as fixed, not as a question (ledger parked, D-48) |
| Unclear plan item at night (D-29) | Nothing pauses; the agent builds a reading and the interpretation leads the report; a frozen test overrides it |
| Agent asks a question at night (D-29) | Controller answers “interpret and record”; stage continues |
| Restate-back difference (D-28) | Two readings that differ appear as one question in Plan mode before queueing |
| End-to-end scenario fails (D-34) | Recorded with output; goes into repair; not reported as passed |
| Explain-back sample (D-49) | Picked by you after the final commit; absent from every earlier prompt, file, and workspace |
| Usage limit hit (D-25) | Work committed, plan enters `paused: usage reset`, same session resumed with “continue” after reset; repair count unchanged |
| Weekly usage at 95% after a plan (D-43) | Run stops, unless the weekly reset is tomorrow; next run continues from the cut-off |
| Run window ends / Pause pressed (D-41) | Agents pause with work committed; Resume continues the same sessions |
| Laptop during a run (D-42) | Stays awake only while the controller runs; sleeps with the lid shut; no power settings changed afterwards |
| Agent run ends without “done” (D-51) | Limit → wait and continue; question → “interpret, proceed, record”; never counted as done |
| Plan 1 not done (D-44) | Plan 2 does not start |
| Agent says done but tests fail (D-46) | Controller's own run records the failure; round 1 Codex, round 2 Claude |
| Permission reviewer denies an action (D-50) | Logged; plan pauses and notifies you |
| Agent leaves a dev server running (D-52) | Process group killed at node end |
| Node runs past 2 hours (D-52) | Stopped; work committed; time paused or waiting for a reset not counted |
| Claude looks for the hidden tests (D-45) | Separate clone; deny-read rule blocks it; nothing in its own clone's history |
| Defective generated test | Review identifies the error against the contract |
| Zero discovered tests | Workflow does not claim successful verification |
| Interrupted agent stage | Recovery inspects partial edits and resumes safely |
| Interrupted integration | Recovery detects actual Git state and avoids duplicate application |
| Repeated unresolved defect | Repair limit produces a preserved blocked result |
| Failed prerequisite plan | Dependent plan stays held; independent plan may run |
| Invalid receipt | Controller rejects it and follows bounded retry policy |
| Concurrent scheduled launch | Lock prevents duplicate work |

## Useful measurements

Track time to usable result, useful issues discovered during refinement, later missed assumptions, human corrections, downstream rework, criteria coverage, repair rounds, unresolved findings, usage, and defects found during human review. Compare against a simpler single-agent workflow on similar tasks before expanding orchestration complexity.

## Deferred features

External issue-tracker integrations, extended agent-to-agent diagnosis exchanges, a visual workflow editor, arbitrary workflow graphs, many vendors, shared-user access, remote monitoring, automatic deployment, and automatic main-branch promotion can follow once the core cycle is reliable.

## Exploration

- Which real project should be the first trial?
- What is the smallest useful feature to implement?
- What result would justify adding overnight scheduling?
- Which failure scenarios matter most for your projects?
