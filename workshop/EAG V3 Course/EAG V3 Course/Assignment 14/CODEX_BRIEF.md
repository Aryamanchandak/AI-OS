# Assignment 14: finish-it brief for Codex

Review date: Tuesday 17 Nov 2026. Push to `eag-v3-assignment-14` (see `REPO.md`).

## What the assignment is

Fork `theschoolofai/S14Code` and build an application that answers only in composed interfaces: the agent picks trusted components and fills them with data, and never writes markup itself. Add one useful new component, show real variety, prove the three invariants hold with an adversarial prompt, and host the app. Submit a pull request, a screen recording and the hosted link.

## What is already here

Only the brief, the lecture and Aryaman's note. No code. `S14Code` is not in this folder yet; Aryaman will pull it in.

## How it fits the capstone

High value. Aryaman's note: this can be the capstone's screen, take it seriously. The learning loop needs exactly these components: a recall card, a grading verdict with the gap highlighted, a calibration chart, a "what now" task list.

## Step 1: read, then pitch. Write no code yet.

Read `Assignment.md`, the lecture, the notes file and every code file in this folder. Then reply to Aryaman with:

- A plain-English summary of what exists and whether it runs (run the tests and show the output).
- A checklist of each thing the brief asks for, marked done, partly done or missing.
- Two or three application ideas, at least one built around the learning loop above, each naming the new component, the components it composes and the adversarial prompt.
- Anything you are blocked on (keys, course code not yet in the folder, permissions, real data).

Then stop and wait for Aryaman's direction.

## Step 2: build what Aryaman picks

Once `S14Code` is in the folder and Aryaman has chosen, build on a branch of it. Keep the three invariants intact.

## Rules

- Existing code is taken to its natural finish. Extend it; never overwrite or restart it.
- Hand-written code only. No agent frameworks (LangChain, LangGraph, CrewAI, AutoGen).
- Turn Aryaman's examples into tests first, then write the least code that passes them.
- Never delete, skip or loosen a test to make it pass. If a test looks wrong, say so and stop.
- Use `uv` for Python. Ask before adding any dependency.
- Keys come from `.env` only. Never hardcode, print, log or commit them.
- Stay inside this folder. One task per commit. Show test output before calling anything done.
- Aryaman pulls course repos and opens pull requests himself. If course code is missing, ask him for it.
