# 06 — Workspaces and Integration

[Back to macro](00-macro.md) · Status: exploration draft

## Workspace arrangement

Isolation confirmed Oct 9 (D-24): agents never work in your live checkout. Revised Oct 9 (D-30): because Claude must never see the independent tests, a plan run uses **separate folders**, even though the writers are not concurrent (concurrency stays parked, [17](17-later.md) L7):

```text
plans/<plan-id>/tests/      Independent tests, written by Codex by day; never inside Claude's clone
run workspace/
  implementation/           Claude's clone: code + its own unit tests; no independent tests, no commit containing them
  check/                    Controller's combined candidate: code + independent tests; Codex works here
  missing-tests/             New Claude session (D-37): base repository for test conventions + plan + list of existing test names (D-48); adds new test files only; no implementation from tonight
  artifacts/                Morning summary, change receipts, findings, explain-back, command logs (coverage ledger parked, D-48)
```

**Revised Oct 10 (D-44, D-45):** `plans/<plan-id>/tests/` is its own **clone**, not a worktree, and Claude's settings deny reads of it. There is **one run clone per run**: all queued plans run one after another inside it, each starting on top of the previous plan's commits once that plan is done, and the controller commits after every node. It is separate from your own working folder, agents have no push credentials, and you review, merge, and push.

Rules:

- The controller builds `check/` by applying Claude's code commits on top of the test commit. Only the controller moves commits between folders.
- Codex's fixes and additions in `check/` are committed by the controller **split by path**. Code changes are copied back into `implementation/` so the implementing Claude session can fix failures of the new missing tests on the final code; test-path changes from `check/` are never copied there.
- Existing tests labelled “change” are removed from `implementation/` (Codex rewrote them) and restored, rewritten, in `check/`.
- The final candidate branch handed to you is the `check/` branch: code and all tests together.

The layout below, from the earlier design, applies only if concurrent production returns:

```text
run workspace/
  implementation/   Claude branch
  tests/            Codex branch
  integration/      Combined candidate branch
  artifacts/        Reports, receipts, findings, command logs
```

Git worktrees isolate working files and branches. They share repository metadata and do not by themselves isolate processes, credentials, or network access. Apply sandboxing or containers separately where required; see [12 — Sandboxing and access](12-sandboxing-and-access.md).

> **✅ DECISION C4 — Agents get a local clone and read-only Git** (accepted Oct 9; details to work through)  
> **Problem:** sandboxed agents and worktrees conflicted over the shared `.git`.  
> **Fix:** Runs use a per-run local clone instead of worktrees, agents have read-only Git, and the controller commits and fetches results back; see the C4 decision in [12](12-sandboxing-and-access.md). Read “worktree” in this section as “run clone” wherever it means the agent's workspace.

## Scope and ownership

In standard production, assign implementation and local-test paths to the implementer. In expanded production, assign independent acceptance-test paths to Codex and implementation plus unit-test paths to Claude; avoid overlapping writers. Some shared files need special treatment: dependency manifests, schemas, fixtures, generated files, and test configuration. Assign an owner in the specification or defer the shared edit to integration.

After a stage, inspect its actual diff against allowed scope. A scope check detects unexpected changes; prevention requires suitable execution permissions.

## Integration process

Record both branch tips and receipts. Apply their commits to the integration branch in a defined order. Capture conflicts, their resolution, and any integration-only edits. Review material conflict resolutions and rerun required checks on the resulting commit.

Codex may perform integration edits, but the controller records Git state and invokes the verification commands. Preserve source branches until the result has been reviewed or a retention policy permits cleanup.

## Across multiple plans

v1 (Oct 10, D-44): plans run strictly one after another in the one run clone; plan N+1 starts only after plan N is confirmed done. What to do when a plan's tests still fail after repair, or its verification is blocked, is parked for you as its own later plan ([17](17-later.md) L17).

Maintain a checked candidate/review branch with one or more checkpoint commits per plan. Dependent plans can run sequentially in its worktree; a permanent worktree per plan is unnecessary. A successful plan advances the checked tip; continuation requires the dependency gate in [03](03-plans-and-queue.md). A failed attempt is preserved separately; reset or create a clean candidate from the last eligible checkpoint before continuing independent work.

When returning to main later, account for any main-branch changes made during the overnight run. Rebase or merge as appropriate, then reverify the resulting commit before claiming it is ready.

## Human corrections to earlier checkpoints

Preserve the original chain before applying corrections. Merge, rebase, or reconstruct affected changes into a revised candidate as appropriate. Record the relationship between old and new checkpoints, inspect affected consumers and assumptions, mark stale evidence, and rerun applicable checks plus final verification. Product/interface changes may require replanning; local corrections need not force a full rewrite. Do not let a controller and the user write concurrently into the same working directory; pause it or use a separate review/correction worktree.

> **✅ DECISION C6 — Conservative invalidation, stack limit, rejection path** (accepted Oct 9; details to work through)  
> **Problem:** affected descendants were undefined.  
> **Fix:** All descendants are invalidated and rechecked by default; see the C6 decision in [03](03-plans-and-queue.md).

## Folder-level replacement

Refactor and rewrite modes may replace a folder within the candidate worktree, optionally using a temporary sibling folder for comparison. Worktrees provide isolation; folder replacement is a production technique. Verify switching callers, imports, configuration, and tests to the replacement. See [15](15-work-modes.md).

## Repository preflight

Record existing work and avoid overwriting uncommitted changes. Define whether the runner requires a clean source checkout or always works from isolated committed snapshots. Capture baseline verification failures before agents modify anything.

## Exploration

- Which branch should hold the overnight sequence?
- How long should failed worktrees be retained?
- When should main-branch merging become automatic?
- Should each worktree use its own dependency environment?
- Does Claude's clone need the dependency environment of `check/`, or can it run only its own unit tests?
