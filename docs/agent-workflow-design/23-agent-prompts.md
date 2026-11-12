# 23 — Agent Prompts for the Planning Workflow

[Back to planning overview](20-planning-workflow-macro.md) · [Back to macro](00-macro.md) · Status: exploration draft for your comments · Created Oct 10

These are the prompts for steps 2, 3, 5 and 7 of the [hardening workflow](22-hardening-workflow.md). To use them by hand, paste them into a **fresh** Claude Code or Codex session started in the repository, and replace each `<…>`. The controller will use the same text later.

Rules that apply to every prompt:

- Use a **new session** each time, so no earlier conversation leaks in.
- The audit, compare and fold-in steps are **read-only on the repository**: they write only their own report file.
- Save every output in `plans/<plan-folder>/hardening/` ([22](22-hardening-workflow.md)).

---

## P1 — Audit (Claude and Codex, separately)

Run this once in Claude and once in Codex. **Neither may see the other's report.**

```text
You are auditing an implementation plan before any code is written. You are not implementing it.

Plan: <path to plan.md>
Attachments: <path to attachments/ or "none">
Repository: the current working directory.
Completeness checklist: <path to 21-plan-checklist-and-template.md>
Earlier plans this plan builds on (their "Provides to later plans" sections): <paths, or "none">
Revision: r<N>. <For round 2+: "Changed since r<N-1>: <summary or diff path>. Re-check changed parts fully and the rest briefly.">

Rules:
- Do not edit any file except your report. Do not write code.
- Never fill a gap silently. If the plan does not say something, it is a gap, even if you think you know the answer.
- Cite real paths and symbols from the repository. If you cannot find something the plan refers to, say so.
- Where this plan depends on an earlier plan, check against that plan's declared outputs, not the current code (that code may not exist yet).

Write your report to: <plans/<plan-folder>/hardening/r<N>-audit-<claude|codex>.md>
Use exactly these sections:

A. Repository map
   For every part of the plan: the files, symbols, entry points, callers and existing tests it touches. Mark anything you could not map.

B. Checklist gaps
   For every checklist field: complete / missing / incomplete (and what is missing). "If applicable" fields must be filled or say "n/a, because ...".

C. Open decisions
   Every decision the plan leaves open (interfaces, data shapes, error behaviour, file layout, naming, order of changes, what happens to old code). For each:
   - the question
   - the options
   - your recommended answer and why
   - the consequence of each option

D. Conflicts and risks
   Where the plan contradicts the existing code, existing tests, an earlier plan's declared outputs, or itself; callers that would break; anything risky.

E. Edge cases
   For each feature, every dimension in the checklist: is it answered in the plan? If not, propose an answer ("applies: case -> expected behaviour" or "n/a, because ...") and mark it as a proposal.

F. Restatement
   For each part of the plan, how you would build it: files created and changed, exact interfaces and data shapes, and the behaviour in each edge case. Be concrete enough that someone could compare your version with another agent's line by line.

G. Untestable or vague statements
   Statements that could not be turned into a test or a scenario as written, and what would make them precise.

H. Summary
   The number of gaps, open decisions and conflicts, and the 3 most important things for the author to fix.
```

---

## P2 — Compare (third fresh session, or you)

```text
Two agents audited the same plan independently. Merge their reports into one question list for the plan's author.

Plan: <path to plan.md>
Report 1 (Claude): <path to r<N>-audit-claude.md>
Report 2 (Codex): <path to r<N>-audit-codex.md>

Rules:
- Do not edit any file except your output. Do not add your own opinions about the plan; work only from the two reports and the plan.
- Keep every distinct point. Merge duplicates, and keep both reasons when they differ.

Write to: <plans/<plan-folder>/hardening/r<N>-questions.md>
Use exactly these sections, numbering every item so the author can answer by number:

1. Restatement differences
   Every place the two restatements (section F) differ: files, interfaces, data shapes, or edge-case behaviour. Show as "Claude would: ... / Codex would: ...". These mean the plan's wording is ambiguous. End each with the question the author must answer.

2. Open decisions
   From both section C lists, merged. Show the options and both recommendations (marking where they agree).

3. Checklist gaps
   From both section B lists, merged.

4. Edge cases not answered
   From both section E lists: feature, dimension, and the proposed answers.

5. Conflicts and risks
   From both section D lists.

6. Untestable or vague statements
   From both section G lists.

7. Agreement
   Points where both agents raised the same issue (higher confidence), and points only one raised.

Leave an "Answer:" line under every numbered item for the author to fill in.
```

---

## P3 — Fold in your answers (fresh session)

```text
Update a plan with its author's answers so the plan reads as one clean document. Questions and answers must not be left alongside the plan.

Current plan: <path to plan.md> (revision r<N>)
Answered question list: <path to r<N>-questions.md>
Completeness checklist: <path to 21-plan-checklist-and-template.md>

Rules:
- Build every answer into the right section of the plan text. The result must read as if it had always been written that way.
- Do not add anything the author did not answer or write. If an answer is unclear, or contradicts another part of the plan, do not guess: list it under "Open questions".
- Keep the author's own wording wherever it is not being changed.
- Keep the template's section order.

Write:
1. the new plan to <plans/<plan-folder>/plan.md>, saving the old one as <revisions/plan-r<N>.md>
2. a short change list to <plans/<plan-folder>/hardening/r<N+1>-changes.md>: for each answered item, which section changed and how
```

---

## P4 — Write the tests (Codex, in the tests clone)

```text
Write the independent tests for an approved-in-principle plan, before any implementation exists.

Plan: <path to plan.md>
Repository (read-only for you): <path to the repo>
Write tests only in: <path to the separate tests clone> (D-45). Never write in the repository.
Earlier plans this plan builds on: <paths to their "Provides to later plans" sections, or "none">

Rules:
- Test observable behaviour and the interfaces the plan names, not implementation internals.
- Follow the repository's existing test framework, conventions and file layout, so the tests can be copied in and discovered as-is.
- For every behaviour in the plan's "Behaviour changes" section:
  - Keep: a test that passes on today's code.
  - Change: a test that fails on today's code for the expected reason (the feature is missing, not a setup error), and asserts the new behaviour.
  - Remove: a test that shows the old behaviour is present today and asserts it is gone afterwards.
- Every "applies" edge case gets a test, unless it is covered by an end-to-end scenario.
- Do not invent behaviour the plan does not state. If you cannot test something as written, do not guess: list it.
- If an earlier plan's outputs do not exist yet, write the tests against its declared interfaces and mark them "depends on <plan>".

Then run the tests against today's code and write a report to <plans/<plan-folder>/hardening/tests-report.md>:
1. Each test: file, name, behaviour covered, keep/change/remove, and its result on today's code (pass / fails as expected / fails for the wrong reason)
2. Untestable or vague statements, and what would make each one precise
3. Edge cases covered by scenarios rather than tests
4. Anything about running the tests that the plan's "How to run and verify" section should say
```

---

## Notes

- **Which vendor writes which prompt.** P1 must run on both vendors. P2 and P3 are suggested for Claude (you prefer its writing), and P4 is Codex (D-23). Any of these can be changed.
- **Reasoning effort.** Use the highest setting for P1 and P4, where the depth of thinking pays off. P2 and P3 are mostly mechanical.
- **Where this is still open:** whether P3 should be done by an agent at all; see [22](22-hardening-workflow.md), Exploration.

## Exploration

- Do these sections match what you look for when you review a plan by hand today?
- Anything you always end up asking an agent that should be built into P1?
- Should P1 also suggest how to split a plan that's too big for one run?
