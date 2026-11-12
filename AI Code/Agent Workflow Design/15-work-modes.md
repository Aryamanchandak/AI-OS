# 15 — Work Modes: Refactor, Rewrite, and Large Feature

[Back to macro](00-macro.md) · Status: revised design proposal

Modes change production and evidence requirements, not the need for isolated candidates, recorded commits, scope controls, or manual main-branch promotion.

**Active modes (D-26):** refactor, rewrite, and large new feature. Bug-fix mode is parked.

## Test types: keep / change / remove (D-27, applies to every mode)

During hardening ([14](14-plan-refinement-and-local-backlog.md)), every behavior your plan touches gets one label: **keep**, **change**, or **remove**. The label decides which tests exist and what they must do on today's code (“before”) and after Claude's work. Codex writes the independent tests from your plan before Claude writes code (C1, D-23).

### v1 test set

| Test type | Written by, when | Before (today's code) | After | If “before” is wrong |
| --- | --- | --- | --- | --- |
| **Change** (new or different behavior) | Codex, day, before code | **Fails** for the expected reason (feature missing) | Passes | A pass means the test doesn't test the new thing; a setup error means the environment is broken |
| **Keep** (characterization: behavior that must survive) | Codex, day, before code | **Passes** | Still passes | A fail means the test misdescribes today's code; fix the test, not the code |
| **Keep at the caller layer** (code that uses a replaced module still works) | Codex, day, before code | Passes | Still passes | Same as keep. Also covers the refactor half of C9 (a test at the layer where the change lives) |
| **Remove** (behavior deliberately deleted) | Codex, day, before code | Old behavior **present** | Old behavior **gone** (e.g. old endpoint or option errors as the plan specifies) | Old behavior missing today means the plan misdescribes the code |
| **Existing repo tests** | Already in the repository | Pass (known failures recorded in the C3 dry run) | Pass, except those tied to change/remove behavior (see below) | Unrecorded failures are baseline defects, reported separately |
| **Claude's unit tests** | Claude, night, during implementation | Don't exist | Pass | — (not frozen; reviewed by Codex) |
| **Missing tests** (D-31, D-37) | New Claude session, night, after Codex's completeness pass, from your plan and the list of existing test names; adds only (prompt instruction, D-47) | Don't exist | Pass | The implementing Claude session fixes the code; if it thinks the test is wrong, the test is marked disputed and listed for you |
| **Smoke / feature exercise** | Runner profile exercise command (C3) | App runs | App still runs its main command | Setup problem; fix during the day |
| **End-to-end scenarios** (D-34) | You + agents, day, in Plan mode | Keep scenarios pass; change scenarios fail | All pass; controller-run and Codex-driven top to bottom | A keep scenario failing today means the scenario misdescribes today's code |
| **Static checks** (build, type check, lint) | Repository configuration | Pass (or recorded baseline) | Pass | Recorded as baseline |
| **Migration** (only if the plan touches stored data or config formats) | Codex, day, before code | Fails (new code absent) | Old-format data loads correctly into the new code | — |

Refactors are mostly **keep**. Large features are mostly **change**. Rewrites mix all three, which is why the plan must label each behavior.

### How labels interact with the test-weakening check (C2)

At night, a legitimate test update and an agent cheating to make a test pass look identical in the diff. So every planned test edit is settled **during the day**:

- **Existing tests covering “change” behavior:** Codex rewrites them during hardening to assert the new behavior. You approve them with the other frozen tests.
- **Existing tests covering “remove” behavior:** listed during hardening and **pre-approved for deletion**. Codex adds the remove test that proves the old behavior is gone.
- **Everything else stays protected:** any other edit, deletion, new skip, or drop in the collected-test count at night is a C2 violation and is rejected outright; objections become test disputes for you (D-37). *v1 (D-47): enforced by a prompt instruction; the mechanical check is parked ([17](17-later.md) L18).*

All Codex-written and pre-approved tests are frozen after your approval and **hidden from the implementer** (D-30): they live outside Claude's workspace, and existing tests labelled “change” are removed from Claude's clone. They meet the code only in the controller's check workspace ([06](06-workspaces-and-integration.md)). Mechanism (D-45): a separate tests clone plus a deny-read rule in Claude's settings.

### Later test types

Old-vs-new comparison, performance, property-based/fuzz, and manual UI acceptance are parked in [17 — Later](17-later.md) (L14).

## Bug fix — PARKED (D-26)

Bug-fix mode, the C8 light path, and the bug-fix half of C9 are parked until small bug fixes come back into scope. Their full text is preserved in [17 — Later](17-later.md) (L4); concurrent writing is L7.

## Large feature

Default (revised Oct 9, D-30 to D-34): Codex writes the acceptance tests from your plan before any code, in a folder Claude never sees (C1); Claude then implements code and implementation-specific unit tests; the controller combines and runs everything; Codex checks completeness against the plan and implements missing items; test failures are repaired in at most 2 rounds, Codex then Claude (D-46); a new Claude session adds missing tests from the plan; the controller runs the end-to-end scenarios. Concurrent test and code writing is not needed (D-23). Integrate before fast checks and review. Place tests in normal project locations, confirm discovery, preserve existing tests, and exercise the feature where possible. The controller captures authoritative check results.

> **✅ DECISION C1 — Independent acceptance tests written before code** (accepted Oct 9; details to work through)  
> **Problem:** no independent executable check existed in the default feature path.  
> **Fix:** Frozen acceptance tests are written during refinement, before code; see the C1 decision in [05](05-roles-and-handoffs.md).

Your hardened plan pins the interfaces and structure you care about. Where it is unclear at night, the implementer interprets and records it rather than stopping; frozen tests always win ([14](14-plan-refinement-and-local-backlog.md), interpretation rule, D-29).

## Refactor

> **C9 (refactor half, still active):** the plan states the layer each change lives in, and a test exists at that layer, not only at the top-level entry point.

List preserved behavior and public boundaries. Characterize important existing behavior before replacing internals. A characterization check is evidence of current behavior, not proof that every existing behavior is desirable; separate existing defects from intended compatibility.

Replace a module or folder within an isolated candidate if that is the clearest approach. A temporary sibling folder can support comparison, but establish how the replacement enters use and when the old copy is removed. Check callers, imports, configuration, fixtures, persistence, error semantics, and relevant performance. Compare old and new behavior using the same representative inputs where feasible.

Make structural checkpoints so a failed replacement can be inspected or reverted. Review the architecture as well as the diff. Avoid combining unrelated feature changes unless explicitly included in the plan.

## Redesign or major rewrite

Declare behavior and architecture changes, migration needs, compatibility boundaries, and downstream assumptions. Use a disposable prototype for uncertain choices when useful. Break production into reviewable checkpoints, with human acceptance before dependent work where structural uncertainty warrants it.

Dependent plans can otherwise continue provisionally on automatically checked commits in the same candidate worktree. Record that provisional status. A correction to a foundation creates a revised chain; reassess affected descendants even if Git applies the change without conflicts. Inspect internal layers and direct consumers, not just the top-level demonstration.

## Common completion evidence

Every mode reports the exact candidate commit, executed checks, exercised feature behavior, unverified/manual criteria, assumptions, and human acceptance status. Main remains unchanged until manual promotion. Reverify the result if promotion changes the tested commit or integrates other changes.

Review repairs according to their actual scope and semantic effects. A tiny diff that changes a shared contract may need broader review than a larger isolated refactor.
