# 22 — Hardening Workflow (Plan Mode)

[Back to planning overview](20-planning-workflow-macro.md) · [Back to macro](00-macro.md) · Status: exploration draft for your comments · Created Oct 10

This document owns the **Plan mode** steps. It replaces the 10-step list in [14](14-plan-refinement-and-local-backlog.md), which stays as the earlier draft. 14 still holds the interpretation rule (what happens at execution time when something is unclear) and the worked example.

## Goal

Take the plan you drafted from the [template](21-plan-checklist-and-template.md) and make it executable: every field complete, no open decisions, and no wording two agents read differently. Everything you want a say over is closed here, because execution never stops to ask (D-29).

## Steps (v1)

| # | Step | Who | Produces | Prompt |
| --- | --- | --- | --- | --- |
| 1 | **Draft** | You | `plan.md` from the template, plus attachments | — |
| 2 | **Audit** | Claude and Codex, each in its **own fresh session**, read-only, not seeing each other's output | Two audit reports: repo map, gaps against the checklist, open decisions with a recommended answer, conflicts and risks, edge-case table, restatement, untestable statements | P1 |
| 3 | **Compare** | A third fresh session (Claude suggested), or you | One **question list** for you: merged gaps, each restatement difference shown as “Claude reads X, Codex reads Y”, edge-case dimensions left unanswered | P2 |
| 4 | **Answer** | You | Answers in the question list, or edits to the plan directly | — |
| 5 | **Fold in** | One agent (Claude suggested) | A new plan revision with your answers built into the plan text, not left as Q&A. You check the diff | P3 |
| 6 | **Repeat 2–5** | — | Until the exit bar is met, or a round finds nothing new | P1–P3 |
| 7 | **Tests** | Codex, in the **separate tests clone** (D-45) | Tests for every testable behaviour: keep tests pass on today's code, change and remove tests fail for the expected reason. Also a list of statements it couldn't test, which go back to step 4 as gaps | P4 |
| 8 | **Baseline check** | Controller, or you by hand in v1 | The test command, build and scenarios run on today's code; setup problems found now, not in the run window | — |
| 9 | **Approve and queue** | You | Tests approved; plan queued with its run window; handoff checklist met ([24](24-handoff-to-execution.md)) | — |

Approving the plan means agreeing to every item in it. During execution a missing item is a defect to fix, never a question for you (D-33).

## Exit bar: the plan is executable when

1. Every **required** field in the checklist is filled in, and every **if applicable** field is filled in or says “n/a, because …”.
2. The **open questions** list is empty.
3. Every **edge-case dimension** is answered for every feature.
4. The two **restatements agree**: Claude and Codex would build the same files, interfaces, data shapes and edge-case behaviour.
5. Every behaviour Codex was asked to test **has a test**. Anything it couldn't test was made precise or marked as a manual check.
6. The **test command and scenarios run** on today's code. Keep tests pass; change and remove tests fail for the right reason.
7. For stacked plans: the **assumes from earlier plans** section matches what those plans **provide** ([24](24-handoff-to-execution.md)).

## Why the steps look like this

- **Independent audits (step 2):** two readings only expose ambiguity if neither agent has seen the other's. Where they differ, your wording is ambiguous. Where they agree with each other but not with you, you see it now rather than in the code.
- **A recommended answer for every open decision:** you choose rather than write from scratch. The agent never decides silently.
- **Fold answers in (step 5):** the implementer reads one clean plan. Q&A attached alongside a plan gets missed or contradicts the plan text.
- **Tests as the final executability check (step 7):** a statement that can't be turned into a test isn't precise enough yet.
- **Baseline check by day (step 8):** a missing dependency or broken test command shouldn't cost a run window.

## Cost and stopping

Each round costs one audit per vendor plus a compare and a fold-in. To keep usage sensible:

- **Round 2 onwards:** the audit prompt is told what changed since the last revision. It re-checks those parts fully and the rest briefly.
- **Stop** when a round produces no new gaps, even if you haven't hit a set number of rounds.
- **Small edits** (wording, an extra example) can skip a full round. Fold them in and re-run only the compare on the changed sections.

## Running it

- **Tomorrow, by hand:** paste the prompts from [23](23-agent-prompts.md). Use fresh sessions for steps 2, 3 and 5, and save every report in the plan folder.
- **With the controller:** the “audit this plan” button runs steps 2 and 3 through `run_claude()` / `run_codex()` in script mode with read-only permissions, and shows the question list in the UI ([16](16-plan-ui.md)). Steps 5 and 7 are buttons too.

## Where things are saved

```text
plans/<plan-folder>/          (outside the repo; the UI's plan folder)
  plan.md                      the current revision (copied into the repo at queue time, see 24)
  revisions/plan-r1.md, ...    earlier revisions
  attachments/
  hardening/
    r1-audit-claude.md
    r1-audit-codex.md
    r1-questions.md            the compare output; you write your answers in it
  tests/                       the separate tests clone (D-45)
```

## Exploration

- Should step 3 be a third agent session, or do you prefer reading both audit reports yourself?
- Should step 5 (folding in answers) be done by an agent, or would you rather edit the plan yourself?
- Do you want a limit on rounds, or only “stop when nothing new”?
- Should Codex write the tests (step 7) before the last audit round, so untestable statements surface earlier?
