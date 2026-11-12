# 14 — Plan Mode: Plan Hardening (Local Backlog Parked)

[Back to macro](00-macro.md) · Status: revised Oct 9 — human-authored plans, agent hardening (D-21); named Plan mode with restate-back, full edge-case answers, item IDs, and end-to-end scenarios (D-28 to D-34)

## Purpose (revised Oct 9, D-21)

**You write the detailed plan in English; the agents make it executable.** The agents do not invent the plan from a rough idea. They audit your plan against the actual repository and return everything that would otherwise become a surprise in the code: gaps, ambiguities, conflicts with existing code, unstated interfaces, and missing edge cases. You revise until nothing load-bearing is left to the agents' judgment. Only then does the plan go to night execution, where turning settled English into code is the simple part.

This replaces the earlier idea of agents refining rough captures. Plans enter through the [UI](16-plan-ui.md).

**Superseded in part (Oct 10):** the planning workflow now has its own set, [20](20-planning-workflow-macro.md)–[24](24-handoff-to-execution.md). [22](22-hardening-workflow.md) owns the Plan mode steps and replaces the 10-step list below. The plan completeness checklist and template are in [21](21-plan-checklist-and-template.md), the prompts in [23](23-agent-prompts.md), and the handoff in [24](24-handoff-to-execution.md). This document still owns the interpretation rule, the edge-case dimensions and the worked example.

## Local backlog — PARKED (D-20)

Capturing rough ideas and bugs in a local backlog is deferred. The earlier design (Markdown items, `index.json`, a captured → investigating lifecycle) is preserved verbatim in [17 — Later](17-later.md) (L1–L3) and comes back after the simplest version works. For now an item exists only once you load a plan in the UI.

> **✅ DECISION C10 — One controller state model** (accepted Oct 9; details to work through)  
> **Problem:** three overlapping status vocabularies (this lifecycle, section 04 terminal states, section 07 finding statuses).  
> **Fix:** One controller state model. A **plan item** has one `status`: draft, hardening, ready, queued, running, paused (reason: usage reset or human gate; `question` removed Oct 9 by D-29, since nothing pauses for a question at night), ready_for_review, accepted, blocked, failed, cancelled. Separate fields record `acceptance` (pending, accepted, rejected) and `provisional` (true or false). **Findings** keep their own small set from section 07. Sections 04, 07, and 14 should point to this model rather than define their own; the full definition is still to be written. Backlog states (captured, refining, awaiting_answer, deferred) return with the backlog ([17](17-later.md) L3).

## Plan mode: how agents make your plan executable (D-28)

> Earlier draft, kept for reference. The current steps are in [22](22-hardening-workflow.md).

Plan mode is a workflow of its own: you asked for one because simply using Claude and Codex does not get a plan to “no surprises”. It is also now the **only** place you are asked anything (D-29), so its exit bar is high. Run from the UI with “audit this plan”. Both vendors audit independently, then the controller merges their output into one gap report.

1. **Map the plan to the repository.** For every part of your plan, name the actual files, symbols, entry points, callers, and tests it touches. Anything the agent cannot map is a gap (“the plan says ‘the export service’; there are two candidates: X and Y”).
2. **List every decision the plan leaves open.** Interfaces, data shapes, error behavior, file layout, naming, migration order, what happens to old code. Each open decision is a question to you, with the agent's recommended answer and the consequence of each option. Agents do not decide these silently.
3. **Label behavior: keep, change, or remove.** For each behavior your plan touches, state whether it is preserved, changed, or deliberately deleted. List the existing tests tied to change and remove behaviors: Codex rewrites the first, and the second are pre-approved for deletion. The labels drive which tests get written (see [15](15-work-modes.md), “Test types”).
4. **Find conflicts and risks.** Where your plan contradicts existing code, tests, or itself; callers that would break. **Edge cases: every dimension below gets an answer** for each feature, either “applies: here is the case and the expected behavior” or “n/a, because …”. An unanswered dimension is a gap.
5. **Restate back (find misreadings).** Claude and Codex each independently write, per plan item, how they would build it: the files, the interface, the data shape, and what happens in the edge cases. The controller lines the two up. **Where their readings differ, your wording is ambiguous**; each difference goes to you as a question showing both readings. Where they agree but differ from what you meant, you see it here, by day, instead of in the code.
6. **Item IDs and end-to-end scenarios.** Every plan item (criterion, labelled behavior, migration step) gets a stable ID for the coverage ledger (D-33; IDs optional in v1, ledger parked, D-48). Every feature gets at least one end-to-end scenario: command, real input, expected output (D-34).
7. **Testability check.** Codex attempts to write an executable test for each criterion. A criterion that cannot be turned into a test is not yet precise enough; it goes back to you as a gap. This is the strongest executability check.
8. **Runner dry run.** The controller runs the repository's runner profile once in a fresh workspace (C3) so setup problems appear during the day.
9. **You revise.** Answer questions and edit the plan; each edit is a new revision. Repeat until both agents report no open gaps, every edge-case dimension is answered, and the two restatements agree.
10. **Approve and queue.** You review the frozen tests (C1) and queue the plan. Approval is agreement to every item in the plan: at night a missing item is a defect to fix, never a question for you (D-33). The tests are then stored outside Claude's workspace (D-30).

Agents check each other: Claude's gap report is reviewed by Codex and vice versa only where they disagree. Stop repeated rounds that produce no new gaps.

## Interpretation rule during execution (D-29, replaces the deviation rule)

If the implementer finds at night that the plan is unclear, contradictory, or silent, it **does not stop**. It picks the most reasonable reading, builds it, and records an **interpretation**: what was unclear, what it chose, why, and the main alternative. This holds for structural matters too (interface, data shape, architecture, behavior, scope). Anything you wanted a say over should have been closed in Plan mode; a wrong interpretation is fixed through a new plan revision (C6).

Limits (confirmed by you Oct 9; expected to grow, so add new ones here and in [01](01-intent-and-scope.md)):

- A **frozen test wins** over any interpretation: the approved test is your spec.
- An interpretation never widens the sandbox, writes outside `writable_paths`, or touches protected paths. If the only reading needs that, the agent builds what it can, and the blocked part is a finding.
- No existing or frozen test is changed at night by any agent; an objection is a test dispute for you (D-37; enforced by prompt in v1, D-47).
- An action the permission reviewer denies pauses the plan for you (D-50); it is not something to interpret around.

Interpretations are the first section of the report. Each one is also a signal that Plan mode missed something; feed it back into the hardening prompts.

The original deviation rule is preserved in [17](17-later.md).

## Required content of a hardened plan

- Your problem statement and intended behavior, with revision number. The agents add to it; they do not replace your words.
- Repository observations with paths, symbols, and recorded baseline commit.
- Work mode: refactor, rewrite, or large feature (bug-fix mode parked, D-26).
- Scope, exclusions, affected modules, and callers.
- Criteria with stable IDs and concrete examples; include negative cases where relevant. Every plan item has an ID and at least one mapped test or declared manual check (D-33; optional in v1, D-48).
- Every touched behavior labelled **keep**, **change**, or **remove**; existing tests to rewrite or delete; compatibility and migration requirements.
- Proposed checkpoints and which choices need early human review.
- Verification commands, test-discovery expectations, end-to-end scenarios for every feature (D-34), and manual acceptance steps.
- An answer for every edge-case dimension, per feature (“applies …” or “n/a, because …”).
- The two agents' restatements, with differences resolved.
- Sandbox (from the UI), repair limit, and an empty list of open structural questions.

Attach detail where it affects decisions or execution. The bar is: nothing structural is left for the implementer to decide.

## Edge-case discovery: every dimension answered

Revised Oct 9 (D-28): you asked for plans with all edge cases thought out, and Plan mode is now the only place to settle them, so every dimension below must be answered for each feature. Dimensions: empty/missing/invalid input; duplicate actions and retries; interruption and partial completion; concurrent activity; large inputs and resource limits; permissions; schema compatibility; external-system failure; and downstream assumptions. Each one is answered “applies” (with the case and expected behavior, which becomes a test or end-to-end scenario) or “n/a, because …”. Record why a relevant case is deferred or unverified.

For a rewrite, trace behavior through layers: entry point → service → storage/external boundary, plus direct callers of replaced modules. For a bug, test the smallest reproducer and nearby cases sharing the same cause. This helps expose lower-layer defects that a top-level demonstration could miss.

## Worked example

Your plan says: “Add CSV export for the table.” (Real plans should be far more detailed; this shows what hardening returns on a thin one.)

Hardening should determine how filtering, column order, pagination, and permissions currently work. The agent might ask: “Should export include all filtered rows or only the current page? We recommend all filtered rows because it matches the current filter; large exports may need a different execution path.” This is an unresolved product choice, not a requirement the agent may silently add.

Once that choice is settled, a refined criterion can say: “AC-01: exporting a filtered table includes all matching rows in displayed column order, even across pages.” Other relevant criteria could cover CSV quoting, empty results, permission boundaries, and failure feedback. Each gets a check or an explicit manual-evidence requirement.

The technical plan identifies the actual table/query/export modules, proposes a stable export interface, assigns implementation and tests, and specifies how to reproduce the user workflow. It must not guess those paths before repository inspection.

## Changes discovered during implementation

Keep the original capture immutable; create a new derived plan revision. Record the discovery, affected criteria, checkpoint, and dependent assumptions.

Revised Oct 9 (D-29): nothing discovered at night stops the plan. Technical detail, a new user-visible decision, expanded scope, or incompatible behavior: interpret, build, and record it under the interpretation rule above, within the sandbox and frozen tests. You correct any of it in the morning by suggesting changes, which creates a new plan revision and reruns affected evidence (C6).

## First build

Begin with one plan loaded in the UI and one hardening session. Record which interpretations still had to be made at night despite hardening, and which restatement differences you missed; each is a gap in the Plan mode prompts to fix. Backlog and external trackers are outside the current scope.
