# 16 — Plan Loading UI

[Back to macro](00-macro.md) · Status: new section, direction accepted Oct 9 (D-20); design to work through

## Purpose

The UI is where work enters the system. It replaces the local backlog (parked) and the hand-written YAML plan fields in [03](03-plans-and-queue.md) and [12](12-sandboxing-and-access.md). Everything an overnight run needs is defined here during the day, so the agents never have to guess.

## What the UI must let you do

| Action | What you supply | What it becomes |
| --- | --- | --- |
| Load a plan | Your detailed English plan (paste or upload Markdown) | `plan.md`, immutable per revision |
| Attach files | Specs, examples, reference code, screenshots, data samples | Read-only context in the artifacts folder |
| Pick the repository and working folder | Repo path, base branch or commit, the folder(s) the work happens in | Base commit and `writable_paths` |
| Define the sandbox | Visible paths, writable paths, protected paths, allowed network hosts | The role access profiles in [12](12-sandboxing-and-access.md) |
| Choose the mode | Refactor, rewrite, or large feature | Mode rules in [15](15-work-modes.md) |
| Set the run window | Start and end time (IST) for this plan, e.g. 00:00–09:00 or 09:00–15:00 (D-41) | `run_window` in `config.json` |
| Start, Pause, Resume | Buttons. Start can be delayed (press before bed). Pause stops the agents and keeps their sessions; Resume continues them with “continue” (D-41) | Controller commands |
| Run Plan mode | Button: “audit this plan” | Gap report, questions, edge-case answers, and the two agents' restatements side by side, with differences highlighted ([14](14-plan-refinement-and-local-backlog.md)) |
| Answer questions and revise | Edits to the plan, answers to questions | New plan revision |
| Approve tests and queue | Review the frozen acceptance and characterization tests; approve | Plan marked ready and queued |
| See results | Morning summary (per plan: done / stopped / skipped, why, last commit, test result, D-53), change receipts with interpretations first, branch, findings, top-to-bottom run output, status (including “waiting for usage reset”, “paused”, “permission denied”, “stopped: weekly limit”) | Read-only view of run output |
| Run the explain-back | Pick the functions and features you want explained (D-49) | A fresh Claude session explains them, blind and against the plan; read alongside the summary |
| Approve or suggest changes | Approve, or write suggested changes; agree or disagree with each out-of-scope suggestion | Approve sets acceptance to accepted; suggestions create a new plan revision through C6 ([03](03-plans-and-queue.md)) |

## Design rule: the UI is thin

The UI writes plain files into a plan folder; the controller reads that folder. The UI holds no workflow logic and no separate database. This keeps the controller runnable without the UI and lets you inspect or edit any plan by hand.

```text
plans/<plan-id>/
  plan-v1.md, plan-v2.md      your English plan, one file per revision
  attachments/                files you added
  config.json                 repo, base, working folder, sandbox, mode, run window, limits
  hardening/                  agent gap reports and your answers
  tests/                      frozen independent tests, as a separate clone; Claude denied reading it (D-30, D-45)
  runs/<run-id>/              morning summary, change receipts, logs, status, explain-back, your review
```

## Local, not remote

Start as a local web page served by the controller on your Mac (localhost only). Remote access is deferred; see [09](09-scheduling-and-recovery.md). Remote monitoring is not wanted on the laptop; revisit with a Mac mini or server ([17](17-later.md) L19).

## Exploration

- Single page with tabs (plan, files, sandbox, hardening, results), or a step-by-step wizard?
- Folder picker for the sandbox, or typed path lists?
- Should the sandbox have saved per-repository defaults so each plan only overrides?
- How should the hardening conversation look: a list of questions with answer boxes, or inline comments on the plan text?
