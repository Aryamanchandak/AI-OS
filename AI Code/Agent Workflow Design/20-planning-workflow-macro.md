# 20 — Planning Workflow: Overview

[Back to macro](00-macro.md) · Status: exploration draft for your comments · Created Oct 10

## What this set covers

Documents 01–17 describe the **implementation workflow**: how a finished plan becomes code. This set (20–24) describes the **planning workflow**: how you get from a plan you've drafted to a plan the agents can execute with **no surprises**, with everything they need already in the repository.

You do the load-bearing thinking. Claude and Codex audit your plan against the repository, find the gaps and the places they could misread you, and turn your answers back into the plan, until nothing is left for them to assume.

## Documents

| Doc | What it is |
| --- | --- |
| [21 — Plan checklist and template](21-plan-checklist-and-template.md) | **Everything a plan needs to be complete**, as a fill-in template you can paste. Each field is marked required or if applicable |
| [22 — Hardening workflow](22-hardening-workflow.md) | The steps from draft to approved plan: who does what, what each step produces, and when the plan counts as executable. Owns the Plan mode design (replaces the step list in [14](14-plan-refinement-and-local-backlog.md)) |
| [23 — Agent prompts](23-agent-prompts.md) | The actual prompts for Claude and Codex: audit, compare, fold answers in, write tests. Usable **by hand tomorrow**, and unchanged once the controller runs them |
| [24 — Handoff to execution](24-handoff-to-execution.md) | What must exist, and where, before a plan can be queued; how plans layer on each other |

## The flow

```text
1. You draft the plan from the template (21)
        |
2. Audit: Claude and Codex, each in its own fresh session, read-only (23: P1)
        |
3. Compare: the two reports merged into one question list for you (23: P2)
        |
4. You answer → answers folded into the plan as a new revision (23: P3)
        |                                 ^
        +-- new gaps? ------ repeat 2–4 --+
        |
5. Codex writes the tests from the plan, in the separate tests clone, and checks them on today's code (23: P4)
        |   anything it can't test → back to 4
        |
6. You approve the tests and queue the plan with its run window (24)
```

**Exit bar** (detail in 22):
- no open questions
- every edge-case dimension answered
- the two agents' restatements agree
- every testable behaviour has a test
- the test command and scenarios run on today's code

## How it runs in v1

- **Tomorrow, by hand:** paste the prompts from 23 into a fresh Claude Code session and a fresh Codex session, each pointed at the repo. Save each report to the plan folder, then run the compare prompt. No controller is needed.
- **Once the controller exists:** the same prompts run through `run_claude()` / `run_codex()` in script mode with read-only permissions, triggered by the UI's “audit this plan” button ([16](16-plan-ui.md)).

The prompts are the same in both cases, so nothing is wasted.

## Open design points (need your call)

1. **Stacked plans can't be checked against code that doesn't exist yet.** If you write and queue plans 1–3 on the same day, plan 2's audit and plan 2's tests depend on plan 1's code, which hasn't been written.
   - **Proposal:** each plan declares **“What this plan provides to later plans”** (files, interfaces, data shapes), and each later plan declares **“What this plan assumes from earlier plans”**.
   - Plan 2 is audited, and its tests are written, against plan 1's declared outputs rather than the current code.
   - Both fields are in the template (21). The risk is that plan 1's implementation drifts from its declaration; see 24.
   - **Alternative:** harden plan 2 only after plan 1 has run. That's safer, but it serialises your day.
2. **“Everything required will be in the repo” vs hidden tests.**
   - The plan, its attachments and context documents go **in the repo**, so the implementer can read them.
   - Codex's tests **cannot** go in the repo, or Claude would see them (D-45). They live in the separate tests clone.
   - Details in 24.
3. **Independent readings vs how you work today.**
   - Restate-back only finds ambiguity if Claude and Codex read the plan **independently**: separate fresh sessions, neither seeing the other's output.
   - That favours two separate audit runs plus a compare step, rather than one interactive chat. You refine plans interactively today.
   - **Recommendation:** do the audit and compare as separate runs, and do your revising interactively however you like.
4. **Answers folded into the plan, not kept as Q&A.** The implementer should read one clean plan, not a plan plus a pile of questions and answers. Same idea as rewriting 01 and 02 clean. Proposal: after each round, an agent folds your answers into the plan text (P3), and you check the diff.

## Not in v1

Agents drafting plans from rough ideas and the local backlog stay parked ([17](17-later.md) L1, L2). You write the plan.

## Exploration

- Is this the right set of documents, or should any be merged or split?
- Stacked plans: declared outputs (proposal) or harden after the previous plan has run?
- Should the compare step be done by a third fresh session, or by you reading both reports side by side?
- How many audit rounds before you'd rather stop and just run it?
