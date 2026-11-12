# 13 — Workflow Revision: Tests, Dependency Chains, and Work Modes

[Back to macro](00-macro.md) · Status: discussion record. Partly superseded by D-20 to D-26 (see [00](00-macro.md)); the simplified pipeline replaces the ordering below

This section records the October 9 discussion about simplifying the original workflow. The revision is now incorporated into the core sections; detailed refinement and work modes are in [14](14-plan-refinement-and-local-backlog.md) and [15](15-work-modes.md). Earlier fixed stage ordering and role assignments have been revised. Preserve section 12's access-control discussion; work modes do not remove isolation requirements.

## Test production and integration

Keep tests in the project's normal test locations and conventions. Folder placement alone does not guarantee discovery: verify runner configuration, fixtures, dependencies, and collected tests.

For independent production, start implementation and test branches from the same recorded commit. Combine both sets of commits into one candidate branch checked out in an integration worktree. Codex may diagnose and integrate; the controller invokes configured commands and captures actual outcomes. Run focused checks while repairing, followed by the required final suite on the exact final candidate. Disclose checks that cannot run.

Independent test work should target observable behavior and stable interfaces. Implementation-specific unit tests can be written by the implementer. Test-writing independence does not guarantee correctness; both agents can misunderstand the same requirement.

## Revised ordering and human acceptance

Proposed order: readiness check → production → combine candidate → fast checks → independent review and relevant feature checks → bounded repair → final verification → report.

Execution results should inform review. Tests do not replace code review, architecture review, or trying the feature. A build can pass while a user workflow fails. Distinguish automated checks passed, agent-exercised behavior, and human acceptance pending. Give the user a runnable candidate, reproduction steps, and relevant evidence. If a manual criterion is required for promotion, keep promotion pending; continuation into dependent work is a separate explicit policy.

## Dependent plans and human changes

A worktree is a working directory for a branch, not a requirement that each plan start from main. Dependent plans can run sequentially in one candidate worktree, with a checkpoint commit after each plan. Retain per-plan commits and evidence rather than creating a permanent worktree for every layer.

The user describes a real tradeoff: building downstream work before upstream human approval saves waiting, but upstream corrections can invalidate downstream work. Removing worktrees does not remove this dependency.

Choose per dependency whether to wait for human acceptance or continue provisionally from an automatically checked checkpoint. Structural uncertainty favors waiting; sufficiently settled behavior can justify provisional continuation. Provisional descendants are not human-approved merely because their parent passed tests.

When the user changes a checkpoint, preserve the old chain and create a revised candidate. Carry the correction forward by merging, rebasing, or rebuilding affected changes as appropriate. Inspect semantic effects even if Git reports no conflict. Mark dependent evidence stale where applicable and rerun affected checks plus required final verification. Changes to interfaces, schemas, or product assumptions may require replanning; a local fix does not automatically require rewriting everything.

Reports identify each plan's input commit, resulting commit, human acceptance status, and downstream assumptions. A structural correction should trigger inspection of dependent layers as well as their entry-point behavior. A passing top-level check does not establish that lower layers are sound.

## Work modes

| Mode | Production approach | Required emphasis |
| --- | --- | --- |
| Bug fix | Small isolated candidate; reproduce failure, add regression evidence, patch | Demonstrate the regression check fails before and passes after; inspect nearby behavior |
| Feature | Implementation with local tests; optional independent acceptance-test production | Observable requirements, combined execution, independent review |
| Refactor | Replace internals behind a defined boundary in an isolated candidate | Preserved behavior, characterization tests, callers, compatibility, and relevant performance |
| Redesign / rewrite | New behavior or architecture built in checkpoints | Explicit behavior changes, migration, downstream impact, and earlier human review of uncertain choices |

Folder-level replacement is an implementation technique compatible with worktrees. A sibling replacement folder can support comparison if useful, but avoid leaving two permanent implementations without an explicit migration strategy. Switching the replacement into use must include imports, registrations, callers, configuration, and tests. Rewriting a folder is not proof that behavior is preserved. Agent write scope must authorize the selected strategy.

## Daytime discovery without exhaustive planning — SUPERSEDED (D-21)

> Superseded Oct 9. The direction is now the opposite: the human writes a detailed plan and agents harden it until nothing structural is open. See [14](14-plan-refinement-and-local-backlog.md). The text below is kept only as a record of the earlier discussion.

The user supplies intent, examples of success and failure, excluded changes, and preferences where there is a meaningful tradeoff. Agents inspect existing code and tests, identify likely edge cases, and propose defaults. Questions should explain the consequence of each choice in product terms rather than requiring the user to design interfaces.

Use bounded discovery and, where valuable, a small prototype. Do not require every unknown to be resolved before execution. Record allowed technical assumptions. During implementation, distinguish a technical problem within scope from a new product decision or irreversible compatibility choice. Continue independent work while the latter waits for the user. Plans evolve through recorded revisions, with affected evidence reassessed.

Useful discovery prompts: what existing behavior could break; what happens with empty, invalid, duplicate, or partial input; what remains compatible; what evidence would show failure; and which unresolved choice changes what the user experiences. These reveal some risks, not all future problems.

## Thin first build and reporting

First trial: one plan, isolated candidate, implementation plus tests, executed checks, independent review, bounded repair, and generated report. Keep minimal durable records and recovery checkpoints. Add parallel production and scheduling after measuring their value.

The controller records commits, changed paths, invocations, timestamps, and captured results. Agents supply judgments, assumptions, and unresolved findings. Render Markdown from authoritative structured records where practical.

After a repair, review the new diff and its affected behavior; retain prior evidence for unchanged areas. Run required final verification on the resulting candidate.

## Backlog

- Bounded Codex–Claude diagnosis exchange: a diagnosis, an evidence-based critique, and a revised proposal. Limit exchanges and stop repeated no-progress failures. Product ambiguities still need the user's judgment.
- Local backlog and refinement role: capture rough ideas and bugs, inspect the repository, and derive ready plans using [14](14-plan-refinement-and-local-backlog.md). The user does not use Jira; an external tracker or permanently running third agent is unnecessary for the first version.
- Dependent-plan policy: classify edges as requiring automated verification or human acceptance; track provisional descendants and evidence invalidated by corrections.
- Measure time to usable result, human corrections, downstream rework, and defects found after automated checks, alongside agent usage.
