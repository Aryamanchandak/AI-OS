# 24 — Handoff to Execution

[Back to planning overview](20-planning-workflow-macro.md) · [Back to macro](00-macro.md) · Status: exploration draft for your comments · Created Oct 10

## Purpose

This document covers what must exist, and where, before a plan can be queued, so the agents find **everything they need in the repository** and nothing they shouldn't see. It also covers how plans that build on each other hand over.

## Where each file goes

| File | Where | Why there |
| --- | --- | --- |
| Final plan (`plan.md`) | **In the repo:** `docs/plans/<plan-folder>/plan.md`, copied in at queue time | The implementer must read it, and later plans can read it too |
| Attachments the implementer needs | **In the repo:** `docs/plans/<plan-folder>/attachments/` | Same |
| Change receipt | **In the repo:** `docs/plans/<plan-folder>/receipt.md`, written during the run | You read it in the morning, and the next plan reads it to see what was actually built |
| Repository conventions | **In the repo:** existing `CLAUDE.md` / `AGENTS.md` | Both agents read these automatically; keep them current |
| Independent tests | **Outside the repo:** `plans/<plan-folder>/tests/`, a separate clone | Claude must never see them (D-45). The controller copies them into a check folder only |
| Audit reports, question lists, earlier revisions | **Outside the repo:** `plans/<plan-folder>/hardening/` and `revisions/` | History for you. The implementer reads only the final plan, which has the answers built in |
| Run settings (run window, sandbox, working folder) | **Outside the repo:** the UI's `config.json` ([16](16-plan-ui.md)) | The controller reads them; agents don't need them |

This answers “everything required will be in the repo”. Everything the implementer needs is in it. Only the tests and the hardening history stay outside, the tests on purpose.

**Proposed:** the controller commits `docs/plans/<plan-folder>/` into the run clone at the start of that plan's run, so the plan arrives with the code it describes.

## Handoff checklist (queueing is blocked until all are true)

1. The plan meets the exit bar in [22](22-hardening-workflow.md): every required field filled, no open questions, every edge case answered, restatements agree.
2. Codex's tests are in the tests clone, the tests report shows the expected baseline results, and you have approved them.
3. The test command, build commands and every end-to-end scenario run on today's code, with setup problems fixed (the baseline check).
4. The plan's output contract names the receipt path, and any other documents to produce.
5. For a stacked plan, “Assumes from earlier plans” matches those plans' “Provides to later plans” exactly.
6. The run window, sandbox and working folder are set in the UI.
7. Repository conventions (`CLAUDE.md` / `AGENTS.md`) are current enough for this plan.

## Plans that build on each other

Plans run one after another; plan N+1 starts only once plan N is done, on top of its commits (D-44). You may write and queue several plans on the same day, before any of them has run, so:

- **Each plan declares its outputs** in “Provides to later plans”: the exact files, interfaces, data shapes and behaviour later plans can rely on. This is a contract.
- **Each later plan declares its inputs** in “Assumes from earlier plans”, naming that contract.
- **Hardening and tests for plan N+1** are checked against plan N's declared outputs, not the current code ([23](23-agent-prompts.md), P1 and P4).

**The risk is drift.** At execution time, plan N may be built slightly differently from its declaration, through an interpretation (D-29) or a fix. Plan N+1 would then rely on something that isn't there. Proposed handling, for you to decide:

1. Plan N's change receipt has a **“Provides — as built”** section that lists any difference from its declared outputs.
2. Plan N+1's implementer reads plan N's receipt first. Where it differs from what plan N+1 assumes, the implementer adapts plan N+1's code to what was actually built, and records it as an interpretation.
3. A difference that can't be bridged is reported in plan N+1's receipt for you.

This links to point 3 (what to do when a plan's verification is blocked or its tests still fail), which is parked as its own later plan ([17](17-later.md) L17).

## After the run

You review in the morning:
- the morning summary
- each plan's `receipt.md`
- the explain-back you choose (D-49)

Then you approve, or suggest changes that become a new revision of the plan and go back through hardening ([22](22-hardening-workflow.md)).

## Exploration

- Is `docs/plans/<plan-folder>/` the right place in the repo, or do you have an existing docs convention?
- Should plans stay in the repo permanently, as a project history, or be removed once accepted?
- Drift between declared and as-built outputs: is the proposed handling enough, or should a difference this large stop the chain?
- Should the baseline check (checklist item 3) be run by you by hand in v1, or wait for the controller?
