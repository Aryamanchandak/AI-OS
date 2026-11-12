# 11 — Decisions and Exploration

[Back to macro](00-macro.md) · Status: exploration draft

## Confirmed intent

- Prepare multiple plans and hand them to a scheduled workflow.
- Use Codex and Claude for independent production and cross-review.
- Keep tests in normal project locations; Codex writes independent tests before code; agents work in an isolated workspace.
- Load plans, files, sandbox, and working folder through a local UI; backlog parked; no Jira.
- The user writes detailed plans in English; agents harden them against the repository by day and convert them to code by night.
- Support refactor, rewrite, and large-feature modes (bug fix parked); keep main promotion manual.
- Produce change receipts, collate findings, repair issues, integrate changes, and execute tests.
- Advance through plans and provide a final report for your review.
- Keep the design as separate section documents plus a macro document in a dedicated folder.

## Proposed defaults awaiting a decision

| ID | Topic | Starting proposal | Status |
| --- | --- | --- | --- |
| D-01 | Execution integration | Direct adapters (`run_claude()` / `run_codex()`, script mode); borrow from Omnigent, no dependency | Accepted Oct 10 (D-39, D-40, D-55) |
| D-02 | Workspace structure | One isolated candidate with checkpoints; separate worktrees for optional parallel production | Revised proposal |
| D-03 | Branch promotion | Checked candidate; human acceptance separate; manual main promotion | Revised proposal |
| D-04 | Repair limit | ~~Three rounds per plan~~ Two rounds, alternating Codex then Claude, only when the controller's test run fails | Revised Oct 10 (D-46) |
| D-05 | Blocked plans | Preserve work, hold dependents, continue independent plans | Proposed |
| D-06 | Artifacts | Controller records facts; agents supply judgments; Markdown generated from structured records | Revised proposal |
| D-07 | State store | Transactional state plus append-only event log | Superseded: one status file per run, no SQL (D-25, D-40); parked in [17](17-later.md) L8 |
| D-08 | First implementation | One manual refinement/implementation/check/review cycle; parallel production and scheduling later | Revised proposal |
| D-09 | Isolation | Vendor sandboxes for supervised trials; container before unattended overnight runs; controller-side diff check always | Revised Oct 10: v1 = per-run clone + vendor sandbox + permission reviewer + no push credentials (D-44, D-50); container and path check later ([17](17-later.md) L21) |
| D-10 (C1) | Test independence | Codex writes frozen acceptance tests during refinement, before code | Accepted; detail pending |
| D-11 (C2) | Test weakening | Protected tests, diff/skip/count checks; at night any flagged change is rejected and objections become test disputes for you (D-37) | Parked for v1 (D-47): prompt instruction instead; [17](17-later.md) L18 |
| D-12 (C3) | Check environment | Runner profile per repository; daytime dry run gates queueing | Accepted; detail pending |
| D-13 (C4) | Agent workspace | Per-run local clone; read-only Git for agents; controller commits | Accepted; detail pending |
| D-14 (C5) | Blocking findings | Criterion ID plus evidence; otherwise advisory | Accepted; detail pending |
| D-15 (C6) | Downstream changes | Invalidate all descendants; provisional stack ≤ 2; rejection creates plan revision | Accepted; detail pending |
| D-16 (C7) | Usage limits | `quota_exhausted` state; vendor terms checked | Superseded by D-25; vendor-terms check still required |
| D-17 (C8) | Light path | Defined minimal path for small bug fixes | Parked (D-26) |
| D-18 (C9) | Lower layers | Root-cause layer statement plus test at that layer | Accepted; detail pending |
| D-19 (C10) | State model | One plan status plus acceptance/provisional fields | Accepted; detail pending; backlog states parked with the backlog |
| D-20 | Intake | Local UI for plans, files, sandbox, working folder; backlog parked | Accepted Oct 9; design in [16](16-plan-ui.md) |
| D-21 | Plan authorship | Human writes detailed English plan; agents harden it until no structural question is open; ~~deviation at night on structural matters stops and asks~~ (replaced by D-29) | Accepted Oct 9; night rule revised by D-29 |
| D-22 | Workflow shape | Load-bearing work by day; short fixed night pipeline; heavy state and recovery replaced by wait-and-continue (D-25) | Accepted Oct 9 |
| D-23 | Test independence | Codex writes tests from the plan before code (C1) = the chosen form of parallel test writing; concurrent writing not needed | Accepted Oct 9 |
| D-24 | Isolation | Agents work in an isolated workspace (worktree or C4 clone), never the live checkout | Accepted Oct 9 |
| D-25 | Usage limits | On limit: commit WIP, wait for reset, resume same session with “continue”; usage-aware routing deferred | Accepted Oct 9 |
| D-26 | Scope | Refactors, rewrites, large features only; bug-fix mode and C8 parked | Accepted Oct 9 |
| D-27 | Test types | Each touched behavior labelled keep/change/remove; change tests fail on baseline, keep pass, remove see old behavior then its absence; existing tests for change are rewritten and for remove pre-approved for deletion during the day; v1 set and later types in [15](15-work-modes.md) | Accepted Oct 9 |
| D-28 | Plan mode / Execution mode | Day hardening is its own workflow (Plan mode) with restate-back, every edge-case dimension answered, item IDs, and end-to-end scenarios; night is Execution mode; separate from work mode | Accepted Oct 9 |
| D-29 | Night ambiguity | Interpret, don't stop: build the most reasonable reading and record it; interpretations lead the report; frozen tests win; sandbox unchanged; no test edits at night; `paused: question` removed from C10 | Accepted Oct 9; limits confirmed, list will grow |
| D-30 | Test independence | Independent tests hidden from the implementer (separate folder, never in its clone or history), not just read-only; combined only in the controller's check workspace | Accepted Oct 9; mechanism set Oct 10 (D-45) |
| D-31 | Swap after implementation | Codex completeness pass against the plan and implements missing items; then a new Claude session adds missing tests from the plan and a coverage list, changing no existing test (D-37) | Accepted Oct 9 |
| D-32 | Who fixes | The finder fixes; Codex fixes test-suite failures; the controller's rerun is the verification; no other-vendor approval path for test changes (D-37) | Revised Oct 10 (D-46): repairs alternate Codex then Claude, max 2 rounds |
| D-33 | Unimplemented items | Plan item IDs + controller coverage ledger decide completeness; a missing plan item is a defect fixed the same night; only out-of-scope suggestions go to the user | Revised Oct 10 (D-48): ledger parked, completeness pass stays, IDs optional |
| D-34 | Top-to-bottom run | Per-plan end-to-end scenarios declared by day; controller runs them and Codex drives the program at night; UI driving deferred | Accepted Oct 9 |
| D-35 | Explain-back and review | Random sample (v1: 5 functions, 2 features) drawn after the final commit; fresh session explains blind, then against the plan; explainer is a fresh Claude session; you review every plan and approve or suggest changes (C6) | Revised Oct 10 (D-49): you pick the sample; random draw parked |
| D-36 | Scope | One user; Claude and Codex only; one plan per v1 run; multiple layered plans after the first cycle | Revised Oct 10 (D-44): v1 runs all queued plans one after another |
| D-37 | Test changes at night | No agent edits, deletes, or skips an existing or frozen test at night; C2 rejects outright, no approval path; objections become test disputes for the user; missing tests come from a new Claude session told to read the plan and only add tests | Revised Oct 10 (D-47): enforced by prompt in v1 |
| D-38 | Controller scope | Simple Python loop: schedule, feed plans in sequence, run tests itself, wait for resets and continue, pause/resume. No stage state machine, gates, or allowed-action lists; “done” = agent says done, plus the controller's test result recorded; may grow into a simple agent loop | Accepted Oct 10 |
| D-39 | Agent invocation | Script mode (`claude -p`, `codex exec`, JSON output) in a visible Terminal window; not driving the interactive app; CLI only, SDK/app-server later (L16); vendor terms to check once | Accepted Oct 10 |
| D-40 | Adapter | `run_claude()` / `run_codex()`; predefined roles; given workspace; scope = plan; new session per node; session record = run date + plan + vendor session ID; reads status, session ID, limit hit; output = Claude's change receipt where the prompt says; vendor data kept for resume and limits only; usage info controller-only | Accepted Oct 10 |
| D-41 | Run window | Set per plan in the UI (IST); agents pause at window end; Pause/Resume buttons any time; Resume continues the same sessions | Accepted Oct 10 |
| D-42 | Keep awake | `caffeinate -i -w <controller PID>` for the run only; lid shut → sleeps; no power settings changed; delayed start; Mac mini/server later (L19) | Accepted Oct 10 |
| D-43 | Weekly limits | Check after each plan from your existing tracker; ≥95% → stop unless weekly reset is tomorrow (then burn through); next run continues from the cut-off; short-window limits never stop the run | Accepted Oct 10 |
| D-44 | Sequencing and workspace | All queued plans run one after another in one run clone; plan N+1 only after plan N confirmed done, on its commits; commit after every node; clone separate from your working folder; no push credentials; you merge and push | Accepted Oct 10 |
| D-45 | Hiding tests | Tests in a separate clone (not a worktree: shared `.git`); Claude deny-read rule on that path; controller copies tests into a check folder only | Accepted Oct 10 |
| D-46 | Tests and repair | Controller runs the test command itself after “done” (no AI usage); only on failure: round 1 Codex, round 2 Claude, then stop | Accepted Oct 10; outcome after round 2 open (L17) |
| D-47 | No test changes | Prompt instruction in every fix and missing-test prompt; disputes in the change receipt; mechanical C2 parked (L18) | Accepted Oct 10 |
| D-48 | Coverage ledger | Dropped for v1; Codex completeness pass stays; item IDs optional; ledger parked (L18) | Accepted Oct 10 |
| D-49 | Explain-back | You pick the functions and features in the morning after the final commit; fresh Claude session explains, blind then against the plan; not run by the controller; random draw parked (L20) | Accepted Oct 10 |
| D-50 | Permissions | Permission reviewer: Claude auto mode / `--permission-prompt-tool`; Codex equivalent hook or our own small reviewer; cheap model; unsure → deny and log; denied → plan pauses and waits for you with a notification | Accepted Oct 10; Codex hook to verify |
| D-51 | Ended vs done | Done → next node; usage limit → wait and continue; question → “interpret, proceed, record” up to N times | Accepted Oct 10 |
| D-52 | Processes and timeout | Own process group per node, killed at node end; 2-hour node timeout excluding waiting and paused time | Accepted Oct 10 |
| D-53 | Morning summary | Controller-written: per plan done / stopped / skipped, why, last commit, test result; change receipts under it | Accepted Oct 10 |
| D-54 | Dry run | One trivial plan end to end in the daytime before the first real run | Accepted Oct 10 |
| D-55 | Omnigent | Borrow code and ideas as and when required, license permitting, notices kept; session lifecycle first; not a dependency or fork | Accepted Oct 10 |
| D-56 | Point 3 | Stacking plans when verification is blocked or tests still fail, later plans fixing earlier code, rerunning earlier plans' tests: parked as its own later plan for you (L17) | Parked Oct 10 |

## Revised design direction

Sections 01 and 03–10 now incorporate the workflow revision. See [14](14-plan-refinement-and-local-backlog.md) for detailed plan refinement and [15](15-work-modes.md) for mode-specific evidence. Precise runtime limits, adapter behavior, and schema details remain implementation choices. Dependency gates and human correction recovery are explicit design requirements. Jira has been removed from current scope; intake is local.

## Questions to resolve first

1. Which repository and first plan should be used for a trial?
2. ~~Is this a local workflow initially, or must it run remotely?~~ Settled Oct 10: your laptop for v1; Mac mini or server later (D-42, L19).
3. ~~Who drafts the refined plan?~~ Settled: the user (D-21); Codex writes tests before code (D-23).
4. What repository checks and acceptance evidence are mandatory?
5. ~~Which actions and assumptions can be authorized before the run?~~ Mostly settled (D-29): any interpretation is authorized at night, within the sandbox and frozen tests.
6. ~~Should Omnigent be a dependency, an optional adapter, or only a design reference?~~ Settled Oct 10 (D-55): a source to borrow from, license permitting.
7. Which files must never be visible to agents, and is sparse checkout enough or is snapshot export required? See [12](12-sandboxing-and-access.md).
8. ~~Who writes the explain-back?~~ Settled: a fresh Claude session, blind first (D-35).
9. ~~Keep other-vendor approval for frozen-test changes?~~ Settled: no; no test changes at night at all (D-37).
10. ~~Confirm the bounds on night interpretation?~~ Settled: confirmed; the list will grow (D-29).
11. ~~Planning documents for the plan workflow~~ Drafted Oct 10 as [20](20-planning-workflow-macro.md)–[24](24-handoff-to-execution.md), awaiting your comments.
12. Point 3: what happens when a plan's verification is blocked or its tests still fail after 2 rounds ([17](17-later.md) L17).
13. Where does your existing usage tracker read weekly usage from (D-43)?
14. Which run time in IST is best for usage (D-41)?
15. Does Codex have a permission-approval hook usable from `codex exec` (D-50)?

## Further exploration

- Reusable fixed workflows versus user-defined workflow graphs.
- Model and role selection based on task type.
- Fresh review sessions versus continued sessions.
- How to arbitrate disagreements without endless discussion.
- Whether dependencies should connect plans within one repository or across repositories.
- Usage and cost reporting under the chosen account setup.
- How much context to preserve and how to retrieve previous findings.
- Report quality and whether the workflow saves time in practice.

## Decision log template

Copy this block when a question is settled:

```text
Decision ID:
Date:
Topic:
Decision:
Reason:
Alternatives considered:
Affected sections:
Evidence or assumptions:
Conditions for revisiting:
```

## Iteration notes

Add your notes below, or place them directly in the relevant section. Nothing in the proposed-default table becomes accepted configuration merely by being written here.

### Notes

October 9, initial discussion: [13 — Workflow revision](13-workflow-revision.md) captured test integration, human feature acceptance, dependent checkpoint chains, work modes, and a thinner first build.

October 9, requested revision: updated the core plans to incorporate that discussion, added [14 — Plan refinement and local backlog](14-plan-refinement-and-local-backlog.md) and [15 — Work modes](15-work-modes.md), and revised D-02, D-03, D-06, and D-08. The user does not use Jira, so intake is local. Only Markdown plans were changed; no workflow implementation or external integration was created.

October 9, user review of the macro: direction set as D-20 to D-26 (UI intake, human-authored plans hardened by agents, simple night pipeline, tests-first by Codex, isolation kept, wait-and-continue on usage limits, scope limited to refactors/rewrites/large features). D-27 accepted with keep/change/remove labels and the v1 test set. Sections 16 and 17 (Later: parked items preserved verbatim) added; 13's discovery section marked superseded; backlog, bug-fix mode, and C8 parked. Correction: plan dependencies (C6), the findings lifecycle, end-of-window policy, the launch lock, and the full C10 fields were briefly parked by Claude without a user instruction and have been restored.

October 9, second user review (comments on 01): direction set as D-28 to D-36 — Plan mode / Execution mode, interpret instead of stopping, tests hidden from the implementer, the swap after implementation, finder fixes, coverage ledger for unimplemented items, top-to-bottom run, randomised explain-back with human review of every plan, scope confirmed. Knock-on edits in 00, 03–10, 12, 14–17; replaced wording preserved in 17 under “Second review round”. New to-do item: L15 (explain-back sizing).

October 9, answers to the three open questions: explain-back by a fresh Claude session (writing quality, load balance with Codex); no other-vendor approval for test changes, replaced by no test changes at night plus a new add-only Claude session for missing tests (D-37); interpretation limits confirmed and expected to grow.

October 10, review of 02 (architecture and Omnigent): v1 cut to the minimum, logged as D-38 to D-56. Controller is a simple Python loop; script mode in a visible window; minimal adapter; run window per plan with Pause/Resume; `caffeinate` for the run only; weekly-limit rule; plans in sequence in one run clone; hidden tests via separate clone; controller runs tests with 2 alternating repair rounds; D-37 by prompt; coverage ledger and random explain-back parked; permission reviewer; Omnigent as a source to borrow from. Point 3 parked as its own later plan. Knock-on edits in 00, 01, 03–10, 12, 14–17; replaced wording preserved in 17 under “Fourth review round”. Then 01 and 02 were rewritten as clean documents with your comments built in (comments removed at your request), to make conversion into implementation plans easier.

October 9, review: ten gaps (C1–C10) found and fixes accepted in direction; logged as D-10 to D-19 and marked in place with `DECISION Cn`. Next step: work through each in detail, one at a time. Note that D-13 (local clone) supersedes the worktree wording in D-02 for agent workspaces.
