# 07 — Receipts and Findings

[Back to macro](00-macro.md) · Status: exploration draft

## Artifact structure

```text
runs/<run-id>/plans/<plan-id>/
  input-plan.md
  specification.md
  contract.json
  stages/<stage-id>/<attempt>/
    receipt.md
    receipt.json
    events.jsonl
  findings.json
  coverage.json
  verification/
    results.json
    command-logs/
  final-report.md
runs/<run-id>/explain-back/
  sample.json, blind.md, against-plan.md
```

Keep attempt-specific artifacts immutable. A later repair produces a new receipt instead of overwriting evidence from an earlier attempt.

## Change receipt contents

The controller records task/stage IDs, invocation/session metadata where available, input/output commits, contract revision, changed paths, timestamps, and captured command results. Writers supply criteria addressed, design decisions, assumptions, interpretations made under D-29 (what was unclear, what was chosen, why, main alternative), and unresolved issues. Agent-reported command execution remains distinct from controller-captured results.

Every reviewer records the commit reviewed, criteria inspected, findings, evidence, and limits of the review. Distinguish author-reported checks from checks the controller actually executed.

Keep validated structured records authoritative and generate Markdown views from them; agents need not independently maintain duplicate factual receipts. Validate structured outputs before trusting fields used for transitions. Malformed or missing receipts should trigger a bounded retry or a recorded failure.

## Findings model

A finding should include stable ID, source, severity, affected criterion, file or artifact location, evidence, expected behavior, assigned owner, status, and resolution evidence.

Suggested statuses: `open`, `assigned`, `fixed_pending_verification`, `closed`, `disputed`, and `deferred`.

Deduplicate related findings while retaining both reviewers' evidence. Agent disagreement should remain visible. A finding closes when its required evidence is satisfied, not merely when the fixer reports completion.

> **✅ DECISION C5 — Mechanical rule for blocking findings** (accepted Oct 9; details to work through)  
> **Problem:** severity, and so blocking, was the reviewing agent's judgment, and disputes had no tie-breaker.  
> **Fix:** A finding **blocks** only if it names a criterion ID (or a protected-behavior item) **and** includes evidence: a reproducing test or command, or a cited line that demonstrably breaks the criterion. All other findings are **advisory** and are listed in the report. On a dispute, a reproducing test settles it; without one, the finding stays advisory, the implementer's reading stands as a recorded interpretation, and it is listed for you in the report. The plan does not pause (revised Oct 9, D-29).

## Morning report

**v1 (Oct 10, D-53):** the controller writes one short **morning summary** first: per plan, done / stopped / skipped, why, the last commit, and the controller's own test result. Claude's **change receipt** (what was written where, at the place the prompt names, D-40) sits under it, with interpretations first. The fuller report below is the target; build only what v1 needs. Usage data is for the controller, not the report.

Start with overall status and the exact branch and commit. Revised Oct 9 (D-29, D-31, D-33 to D-35): each plan's section opens with the items below, in this order, before the existing list.

1. **Interpretations made at night.** What was unclear, what the agent chose, why, and the main alternative. These come first because they are yours to correct.
2. **Plan coverage ledger** *(parked for v1, D-48)*. Every plan item ID, its tests, and pass/fail. A missing item shows as failed with evidence, never as “not implemented, please confirm”.
3. **What the swap changed.** Items Codex found missing and implemented; tests the missing-tests session added.
4. **Test disputes (D-37, D-47).** Any test an agent believes is wrong, with its reasoning, taken from the change receipts. Nothing should have been changed at night (prompt instruction in v1); you decide.
5. **Top-to-bottom run.** Each declared scenario: command, input, output, pass/fail; plus Codex's agent-run transcript, labelled as such.
6. **Explain-back** (see below; you run it in the morning, D-49), including where an explanation disagrees with your plan.
7. **Out-of-scope suggestions.** Things the agents think should exist but are not in the plan; you agree or disagree, and agreed ones become a new plan revision or plan.
8. **Not tested or not verifiable,** and why.

Then, for each plan:

- Intended outcome and behavior delivered.
- Important files and design decisions.
- Acceptance criteria satisfied and remaining gaps.
- Automated checks passed, agent-exercised behavior, and human acceptance pending or granted.
- Input/output checkpoints, provisional dependencies, and evidence invalidated by upstream corrections.
- Commands run, results, skips, and baseline failures.
- Findings fixed, disputed, or deferred.
- Repair rounds and available usage data.
- Assumptions, blockers, and questions needing your judgment.
- How to reproduce verification and inspect the changes.

Link details instead of burying the result in full agent transcripts. Include a run-level index covering all plans, including those not attempted.

## Coverage ledger (D-33) — parked for v1 (D-48)

Kept as the design for later ([17](17-later.md) L18). In v1, Codex's completeness pass against the plan covers “nothing silently unimplemented”.

One record per plan item: item ID, text from your plan, keep/change/remove label, mapped tests, latest result, and the commit it was checked on. The controller writes it from executed results; agents cannot set an item to done. Plan mode refuses to queue a plan with an item that has no mapped test or declared manual check. Stored at `runs/<run-id>/plans/<plan-id>/coverage.json` and rendered in the report.

## Explain-back audit (D-35)

Purpose: make the agent explain the code so you can critique it and catch anything lost in translation.

- **When.** In the morning, after the final commit, across any plans that ran (D-49).
- **Chosen by you, and unknown beforehand.** You pick the functions and features, focusing on what you judge important (revised Oct 10, D-49; the random draw is parked, [17](17-later.md) L20). The choice doesn't exist until you make it, so no agent can prepare for it. The implementer's prompt says that part of its code will be audited, never which part.
- **Who.** A fresh **Claude** session with no access to the build conversation (settled Oct 9). You prefer how Claude writes, and it balances the load, since Codex does most of the heavy non-coding work.
- **How.** Two passes:
  1. **Blind:** from the code alone, for each function: what it does, why it is structured this way, alternatives it rules out, assumptions it embodies. For each feature: a top-down walk from entry point through each layer to the output.
  2. **Against the plan:** only then the explainer gets your plan and the night's interpretations, and lists every place its explanation disagrees with them. Each disagreement is an advisory finding in the report; nothing is changed at night.
- **Then you.** You read the explanations with the report and approve, or suggest changes in the UI ([16](16-plan-ui.md)). Suggestions create a new plan revision through the C6 rejection path ([03](03-plans-and-queue.md)).

Artifacts: `runs/<run-id>/explain-back/` with `sample.json` (the items you picked), `blind.md`, `against-plan.md`.

## Exploration

- What level of detail makes a morning report useful to you?
- Which receipt fields must be mandatory?
- Should reports include screenshots or other product evidence?
- ~~Is 5 functions + 2 features the right explain-back sample to start with?~~ Settled Oct 10: you pick (D-49).
- How long should logs and artifacts remain available?
