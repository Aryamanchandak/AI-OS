# 04 — Workflow Stages

[Back to macro](00-macro.md) · Status: exploration draft

## Stage definitions (simplified Oct 9, D-22)

Day stages carry the load. The night is one linear pass with one bounded repair loop and no stopping for questions.

**v1 (Oct 10, D-38):** the controller does not enforce per-stage gates. The “Done when” column describes what each stage is expected to produce; the controller only moves on when the agent says done (D-51), records its own test result (D-46), and commits after every node (D-44). Each node is a new session (D-40). The original 9-stage table is preserved in [17](17-later.md) L11.

| # | Stage | When | Who | Done when |
| --- | --- | --- | --- | --- |
| 1 | Load plan | Day (Plan mode) | You, in the [UI](16-plan-ui.md) | Plan, files, sandbox, working folder, and mode saved |
| 2 | Harden plan | Day (Plan mode) | Claude + Codex audit and restate back; you revise | No open structural questions; every edge-case dimension answered; the two restatements agree; every plan item has an ID; end-to-end scenarios declared ([14](14-plan-refinement-and-local-backlog.md)) |
| 3 | Write tests + dry run | Day (Plan mode) | Codex writes tests into the separate tests folder (C1, D-30); controller runs runner profile (C3) | Tests behave correctly on baseline per keep/change/remove label ([15](15-work-modes.md)); affected existing tests rewritten or pre-approved for deletion; you approve and queue |
| 4 | Implement | Night | Claude, in its own clone, **without** the independent tests (D-30) | Controller commits the result and checks scope; interpretations recorded (D-29) |
| 5 | Combine + run checks | Night | Controller | Code and hidden tests combined in the check folder (D-45); the controller runs the test command itself (D-46) |
| 6 | Completeness pass | Night | Codex, against your plan item by item and the diff | Missing or partial plan items implemented; review findings listed, blocking only per C5 (D-31) |
| 7 | Missing tests | Night | A **new** Claude session, from your plan and a list of existing test names (not bodies); told by prompt to change no existing test (D-47) | Tests added for anything not yet covered, including Codex's additions; no existing test touched (D-31) |
| 8 | Verify + repair (≤2 rounds) | Night | Controller reruns the tests; only if they fail: round 1 Codex fixes, round 2 Claude fixes (D-46) | Tests pass, or 2 rounds used; what happens next is open ([17](17-later.md) L17) |
| 9 | Top-to-bottom run | Night | Controller runs declared scenarios; Codex drives the program through them (D-34) | Outputs captured; a failure returns to stage 8 if rounds are left |
| 10 | Morning summary | End of the plan | Controller | Per plan: done / stopped / skipped, why, last commit, test result; Claude's change receipts and interpretations under it (D-53, [07](07-receipts-and-findings.md)) |
| 11 | Explain-back | Morning, after the final commit | You pick the functions and features; a fresh Claude session explains them (D-49) | Explanations saved; disagreements with the plan listed |
| 12 | Your review | Morning | You, in the UI | Approve, or suggest changes → new plan revision (C6) |

Revised Oct 9 after your comments on [01](01-intent-and-scope.md) (D-28 to D-36); the previous 8-stage night table is preserved in [17](17-later.md). Nothing at night pauses for a question (D-29). Stages 5–9 are one bounded loop.

Any stage can pause for a usage reset (`paused: usage reset`), the end of the run window or your Pause button, or an action the permission reviewer denied (D-41, D-50, [09](09-scheduling-and-recovery.md)). After stage 10 the controller starts the next plan, on top of this one, once this one is done (D-44). The explain-back (stage 11) is yours in the morning and can pick from any plan that ran (D-49). A dependent plan waits for its dependency gate (automated or human acceptance) and builds on the recorded checkpoint. Your morning rejection creates a new plan revision and goes back to stage 2, invalidating all descendants (C6, [03](03-plans-and-queue.md)).

## Reviews and repair sequence

Run cheap checks on the combined candidate before review. Preserve failures as evidence and diagnose within limits; a reviewer can use that evidence without waiting for every issue to be repaired. Tests do not replace feature exercise, architecture review, or user judgment. Reviewer assignments and production effort vary by [work mode](15-work-modes.md).

After a repair, review the changed diff and affected behavior. Retain prior evidence for unchanged areas, recording its applicability; a small patch to a shared contract can require broader review. Repeat required final checks on the exact final candidate.

## Controller invariants

- No stage succeeds solely because the agent process exits successfully.
- Both parallel branches identify the same base commit and contract revision.
- Stage results identify their exact input and output commits.
- Required findings have explicit dispositions.
- Completeness: the agent says done, Codex's completeness pass checks the code against the plan, and the controller's own test result is recorded beside it (D-46, D-48).
- The implementer's workspace never contains the independent tests or any commit that includes them (D-30); they live in a separate clone Claude is denied from reading (D-45).
- You pick the explain-back sample only after the final commit (D-49).
- Final verification applies to the commit presented for review.
- Queue advancement uses a recorded verified checkpoint and satisfies each dependency's automated or human gate.
- Changed upstream assumptions invalidate affected downstream evidence.
- Automated success, agent feature exercise, and human acceptance are separately recorded.

## Completion states

Use the single plan status list in C10 ([14](14-plan-refinement-and-local-backlog.md)); terminal outcomes are `ready_for_review`, `blocked`, `failed`, and `cancelled`. Track main-branch promotion separately. “Ready for review” means the configured gates passed; it does not imply deployment or unlimited correctness.

## Exploration

- Who drafts the initial specification, and who reviews it?
- Which feature-exercise evidence can agents collect, and which criteria require the user?
- Which findings block completion?
- Can low-impact findings be deferred automatically?
