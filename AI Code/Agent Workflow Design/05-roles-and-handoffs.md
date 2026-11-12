# 05 — Roles and Handoffs

[Back to macro](00-macro.md) · Status: exploration draft

## Initial role assignment

| Responsibility | Proposed owner |
| --- | --- |
| Plan authoring (detailed, in English) | **You** (D-21) |
| Plan hardening: map to repo, find gaps, ask questions | Claude and Codex, independently; merged by controller |
| Independent tests (change, keep, remove, migration) and rewrites of affected existing tests, before code | Codex (C1, D-23, D-27) |
| Implementation and implementation-specific tests | Claude, without seeing the independent tests (D-30) |
| Completeness pass: compare code to plan item by item, implement missing items | Codex (D-31) |
| Tests that don't exist yet, after the completeness pass | A new Claude session: reads your plan and a list of existing test names, adds tests only, told by prompt to change no existing test (D-31, D-47) |
| Independent candidate review | Codex, as part of the completeness pass |
| Actual verification execution and factual records | Controller |
| Findings collation | Controller stores records; agent can propose deduplication |
| Integration, test-suite failure diagnosis and fixes | Round 1 Codex, round 2 Claude; at most 2 rounds, only when the controller's test run fails (D-46) |
| Fixing a verified finding | Same alternation (D-46). Claude gets the failure output and plan item, not the hidden test source |
| Repair verification | Controller reruns the test command itself (D-46) |
| Top-to-bottom run | Controller runs declared scenarios; Codex drives the program (D-34) |
| Explain-back of the functions and features you pick | Fresh Claude session, no build history, in the morning (D-49); chosen for its writing and to balance load against Codex |

These assignments reflect the requested workflow (revised Oct 9: the human authors, the agents harden and execute; revised again Oct 9 for D-30 to D-35, previous rows in [17](17-later.md)). They should remain configurable and can be evaluated against actual results.

## Shared contract

During daytime hardening, your plan pins observable behavior, entry points, signatures, data structures, errors, and relevant compatibility constraints. Give criteria stable IDs so tests and implementation changes can reference them.

Tests derive from your plan's criteria and keep/change/remove labels. A plan that looks wrong is challenged **during daytime hardening** (Plan mode). At night the interpretation rule in [14](14-plan-refinement-and-local-backlog.md) applies (D-29): the agent interprets, proceeds, and records it; a frozen test always wins over an interpretation. Interface changes require a recorded contract revision and coordinated updates to both branches.

## Independent work

Default production (revised Oct 9, D-30 to D-32): Codex writes the independent tests from your plan before code, in a folder Claude never sees; Claude implements code and unit tests from the plan alone; the controller combines and runs everything; Codex checks completeness and implements missing items; Claude adds missing tests; the finder fixes. Concurrent writing is no longer needed (D-23). Codex acceptance tests target stable observable behavior rather than guessing implementation internals. See [15](15-work-modes.md).

> **✅ DECISION C1 — Independent acceptance tests written before code** (accepted Oct 9; details to work through)  
> **Problem:** the implementer wrote the tests that judge it, so a misread requirement passed its own tests.  
> **Fix:** During daytime refinement, Codex writes a small executable acceptance test for each automatable criterion, before any implementation exists. The tests must fail on the baseline for the expected reason (missing feature, not a setup error). After plan approval they are frozen and **hidden from the implementer**: they live outside Claude's workspace and are combined with the code only in the controller's check workspace (D-30, section 12; previously read-only, which still let Claude read them). Claude still writes implementation-specific unit tests. No agent changes a frozen test at night; an objection becomes a test dispute for you in the morning (D-37). This replaces optional parallel test writing as the default source of independence (confirmed by D-23). Whether a test must fail or pass on the baseline depends on its keep/change/remove label; Codex also rewrites existing tests for changed behavior during the day; see [15](15-work-modes.md).

Neither branch has to be fully runnable by itself when the new feature is absent. Receipts must distinguish expected missing-feature failures from setup errors and existing regressions.

## Plan refinement and diagnosis collaboration

You author the plan; agents harden it through repository inspection and evidence-based critique, and return every open structural decision to you. See [14](14-plan-refinement-and-local-backlog.md). For difficult repair, optionally use a bounded diagnosis → other-vendor critique → revised proposal exchange. Require new evidence or a changed hypothesis; stop repeated no-progress debate. This exchange is deferred until the basic repair path works.

## Handoff contents

Each dispatch should include role, task ID, contract revision, base commit, workspace, allowed paths, relevant artifact links, unresolved findings, expected output schema, and stopping conditions.

**v1 (Oct 10, D-40):** much less. Each node is a **new session** given its predefined role, the plan, the workspace, and where to write its change receipt. The allowed scope is the plan. The plan defines the output; the next plan picks up from there. Every fix and missing-test prompt also carries the line “do not edit, delete, or skip existing tests; put any dispute in your change receipt” (D-47).

Pass concise context plus artifact references. Preserve full logs for inspection without feeding every previous conversation into every stage. A reviewer needs actual files and diffs, not only the author's summary.

## Permissions and ownership

Reviewers should be read-only by default. Writers should have the minimum required write scope. Declared ownership needs enforcement where practical; prompts alone do not provide filesystem isolation. Role access profiles and their enforcement are defined in [12 — Sandboxing and access](12-sandboxing-and-access.md).

Revised Oct 9 (D-32): fixes are not handed to the other vendor for review; the controller's rerun of every check verifies them, and the explain-back sample (D-35) can land on any of that code. Revised again (D-37): no agent changes an existing or frozen test at night, and there is no approval path. Revised Oct 10 (D-46, D-47): repairs alternate Codex then Claude, and the no-test-changes rule is a prompt instruction in v1, not a mechanical check. An agent that believes a test is wrong files a **test dispute** in the report; you decide in the morning.

### Hidden tests: what Claude sees (D-30)

- **Where the tests live (D-45, Oct 10):** in a separate clone, not a worktree (worktrees share `.git`, so `git log --all` would reveal them). Claude's settings deny reads of that path; the controller copies the tests into a check folder only.
- **During implementation:** your plan, the repository, its existing tests, and its own unit tests. Not the independent tests, and no commit that contains them; the controller copies only code commits into Claude's clone, so `git show` cannot reveal them.
- **Existing tests labelled “change”:** removed from Claude's clone, since Codex has rewritten them; the controller puts the rewritten versions back in the check workspace.
- **When a hidden test fails:** round 1 Codex fixes it; in round 2 Claude gets the plan item and the failure output, not the test source (D-46).
- **For the missing-tests step (D-37):** a **new** Claude session, not the implementer. Its instructions: read the plan document and the list of existing test names (plus plan item IDs where the plan has them, D-48; not bodies); write tests from the plan; do not change, delete, or skip any existing test; add tests only. It does not read tonight's implementation, so its tests are independent of the code too. It writes against the files, symbols, and interfaces your hardened plan names.

## Exploration

- Should role assignment vary by project or plan type?
- How independent should test authors remain after the first checkpoint?
- Who resolves a disagreement about expected behavior? (Partly settled: a test settles it; otherwise the implementer's interpretation stands and is reported, D-29.)
- Should review sessions start fresh to reduce anchoring?
