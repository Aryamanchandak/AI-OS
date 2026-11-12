# 01 — Intent and Scope

[Back to macro](00-macro.md) · Status: v1 direction settled (D-20 to D-56) · Rewritten Oct 10 with review comments built in

## Intent

You write tightly scoped, detailed English plans with every edge case thought out. The system takes them from there:

1. **Load** each plan through a local [UI](16-plan-ui.md), with its files, sandbox, working folder, and run window.
2. **Plan mode** (by day): Claude and Codex harden the plan against the repository until it can be executed with no surprises ([14](14-plan-refinement-and-local-backlog.md)).
3. **Execution mode** (in the plan's run window): the agents turn the settled English into code, tests, and evidence, without stopping for questions.
4. **Review:** you read the morning summary and change receipts, pick parts of the code to have explained, then approve or suggest changes. Suggestions become a new plan revision (C6, [03](03-plans-and-queue.md)).

The aim is to recover the time you spend today passing plans, changes, findings, and test failures between agents by hand. You should still be able to inspect the result, ask questions, and reverify the work afterwards.

Tight scoping matters because plans **layer**: each plan builds on the code of the one before it. All queued plans run one after another; plan N+1 starts only after plan N is confirmed done (D-44).

## Plan mode and Execution mode (D-28)

| | Plan mode (day) | Execution mode (run window) |
| --- | --- | --- |
| Purpose | Find every gap and possible misreading in your plan; close everything you want a say over | Turn the settled plan into code, tests, and evidence without stopping |
| Who decides | You | Agents, by recorded interpretation where needed (D-29) |
| Ends when | Both agents report no open gaps, their restatements agree, and you approve the tests | The agent says done and the controller has recorded its own test result, or the repair limit is reached |
| Defined in | [14](14-plan-refinement-and-local-backlog.md) | [04](04-workflow-stages.md) |

Plan mode is a workflow of its own, because simply handing a plan to Claude and Codex doesn't remove the surprises. Its aim is to find the gaps in the plan and the places an agent could misread you:

- **Restate-back:** Claude and Codex each independently write how they would build each part of the plan. Where the two readings differ, the wording is ambiguous, and the difference comes to you as a question.
- **Edge cases:** every edge-case dimension is answered, either “applies” or “n/a, because …”.

Naming: Plan mode and Execution mode are **modes of the workflow**. **Work mode** is a different thing: the kind of job the plan is (refactor, rewrite, or large feature, [15](15-work-modes.md)). Work mode decides which tests are needed: a refactor needs mostly *keep* tests, a feature mostly *change* tests. Plan mode is unrelated to Claude Code's built-in “plan mode” feature.

## Core capabilities (v1)

1. **Load** plans, files, sandbox, working folder, and run window through a local UI (backlog parked).
2. **Plan mode:** audit the plan against the repository and return gaps, questions, and likely misreadings until it is executable (D-28).
3. **Independent tests before code:** Codex writes the tests from your plan before any code exists. Claude writes the code without being able to see them. The two must stay independent of each other, or the tests can't do their job:
   - The tests live in a **separate clone**, and Claude's settings deny reading that path (D-30, D-45).
   - The tests meet the code only in a check folder the controller builds.
   - Writing tests and code *at the same time* stays parked ([17](17-later.md) L7). The tests are written before the code, so running both writers at once would save no time.
4. **Swap after implementation** (D-31). The order is Codex first, so Claude's new tests also cover what Codex added:
   - Codex checks the implementation against the plan item by item, reports what should have been implemented and wasn't, and implements it.
   - Then a **new** Claude session reads the plan and a list of existing test names, and **adds only the tests that don't exist yet**. It writes them from the plan, not from the code.
5. **Controller runs the tests itself** (D-46). It runs the real test suite against the combined code after the agent says done: the hidden independent tests, the existing repository tests, and Claude's tests, plus build, type check, and lint where configured. This is a plain shell command, so it uses no agent usage. An agent saying “all pass” is not evidence, and the controller's run is the record.
6. **Repair, at most 2 rounds** (D-46), only when the controller's run fails:
   - Round 1: Codex fixes.
   - Round 2: Claude fixes. It gets the failure output, not the hidden test source.
   - The controller reruns the tests after each round.
7. **No test changes at night** (D-37, D-47). Every fix and missing-test prompt says: do not edit, delete, or skip existing tests; put any dispute in your change receipt. You decide in the morning.
8. **Top-to-bottom run** (D-34). The agents also run the code from entry point to final output:
   - By day, every plan declares end-to-end scenarios: real inputs, run from the entry point to the final output.
   - After the checks pass, the controller runs each scenario and captures the output.
   - Codex then drives the program through the same scenarios and the plan's edge cases. Its transcript is kept, labelled as agent-run.
   - A failure goes back into repair if rounds are left.
   - Scope is CLI, library, and API projects. Driving a UI is deferred ([17](17-later.md) L14).
9. **Morning summary and change receipts** (D-53, D-40):
   - The controller writes one short summary. For each plan it gives done, stopped or skipped; why; the last commit; and the controller's test result.
   - Under it sits Claude's **change receipt**: what was written where, at the place the prompt names.
   - The receipt leads with the interpretations made, followed by what Codex's completeness pass added, which tests were added, test disputes, top-to-bottom output, out-of-scope suggestions, and what could not be tested and why. Full report design in [07](07-receipts-and-findings.md).
10. **Explain-back, chosen by you** (D-49). The point is to make the AI explain itself, so you can critique it and nothing gets lost in translation:
    - In the morning, after the code is final, you pick the functions and features to examine, focusing on what you judge important.
    - A fresh Claude session explains them from the code alone. It covers why each piece is structured that way, what it assumed, and how each feature works top-down.
    - Only then does it get your plan and list where its explanation disagrees.
    - No agent can prepare, because the choice doesn't exist until you make it. The implementer is told that part of its code will be audited, never which part.
11. **Approve or suggest changes** in the UI. Suggestions become a new plan revision or a new plan.

## Solving “X, Y, Z were not implemented”

**Why it happens today:**
- The agent decides when it is done, and a long plan outruns one session.
- Unclear parts get skipped with a note.
- Nothing checks the claim against the plan item by item.
- The leftovers come back to you as proposals, even though you already asked for those things.

**Fix (v1):**

1. **Approving the plan means agreeing to every item in it.** At night, “X was not implemented” is never a proposal for you to accept. A missing plan item is a defect, and it is implemented in the same run.
2. **Codex completeness pass.** After Claude implements, Codex checks the code against the plan item by item, including things a test can't see, and **implements what is missing** (D-31).
3. **“Unclear, so skipped” is not allowed.** An unclear item is interpreted, built, and flagged (D-29). It is never left out.

The plan-item coverage ledger (item IDs → tests → pass/fail) is parked for v1, and item IDs are optional ([17](17-later.md) L18, D-48).

**What still reaches you:**

- Plan items still failing after the repair limit, listed as **failed, with evidence**, not as suggestions.
- Things the agents think should exist but are **not in the plan**, listed as **out-of-scope suggestions**. Each one you agree to becomes a new plan revision or plan, never a silent addition at night.

## Autonomy: interpret, don't stop (D-29)

- **Plan mode is where you close everything you want a say over.** Its exit bar is high as a result: no open structural questions, every edge-case dimension answered, and Claude's and Codex's restatements agree.
- **During execution, nothing stops a plan for a question.** When the plan is unclear, contradictory, or silent, the agent picks the most reasonable reading, builds it, and records an **interpretation**: what was unclear, what it chose, why, and the main alternative. A plan that leaves something open is the plan's mistake, fixed through a new plan revision (C6).
- **Agents decide how to work inside the plan** (D-38). There are no allowed-action lists or per-stage gates; the scope is the plan.
- **Limits.** This list will grow, so add new limits here and in [14](14-plan-refinement-and-local-backlog.md):
  1. An interpretation never overrides a frozen test, because the approved test is your spec.
  2. It never widens the sandbox or touches protected paths.
  3. It never changes an existing or frozen test (D-37, by prompt in v1, D-47).
- **Interpretations come first in the change receipt.**

Things that do pause a plan are not questions:

- a usage reset (wait, then continue)
- the end of the run window or your Pause button
- an action the permission reviewer denied, which waits for you (D-50)
- a dependency waiting for your acceptance (a human gate, C6)

## Scope and boundary

- **One user, two agents:** Claude Code and Codex only. Multi-user support and other vendors are out of scope, not parked (D-36).
- **All queued plans per run, strictly in sequence**, in one run clone separate from your working folder (D-44).
- **One repository per run**, with a small set of known verification commands.
- **Work modes in scope:** refactors, rewrites, and large new features. Bug-fix mode is parked (D-26).
- **Runs on your laptop:** script mode in a visible Terminal window, `caffeinate` for the run only. A Mac mini or server comes later ([09](09-scheduling-and-recovery.md), [17](17-later.md) L19).
- **Kept outside v1:** deployment and main-branch promotion. Agents have no push credentials; you review, merge, and push.

## Human contribution (D-21)

You do the heavy lifting: you write the detailed plan in English, covering behaviour, structure, interfaces, and how you want it built.

- **The agents' daytime job** is to make that plan executable: map it to the code, expose gaps and contradictions, and ask until nothing structural is open.
- **Their execution job** is to convert the settled English into code. Load-bearing thinking happens by day, and the mechanical work happens in the run window.
- **Afterwards** you review every plan's result: the summary, the receipts, and the explain-back you picked. Then you approve or suggest changes.

Reports keep automated verification, agent feature exercise, and human acceptance separate.

**Planning workflow:** how your plans get complete, and get everything they need into the repository, is in [20](20-planning-workflow-macro.md)–[24](24-handoff-to-execution.md).

## Limits of confidence

A passing suite and two agreeing agents can still miss defects. The summary and receipts should keep these apart:

- implemented requirements
- verified behaviour
- review conclusions
- unverified assumptions

The goal is a useful, inspectable handoff with less manual coordination. The top-to-bottom run and your explain-back are the two checks that go beyond the tests.

## Open

- Should each repository have its own workflow policy?
- Point 3: what happens when a plan's verification is blocked or its tests still fail after repair ([17](17-later.md) L17).
