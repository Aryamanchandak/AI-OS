# Assignment 10: finish-it brief for Codex

Review date: Tuesday 17 Nov 2026. Push to `eag-v3-assignment-10` (see `REPO.md`).

## What the assignment is

Build a computer-use skill that drops into the Session 9 skill catalogue and solves three real tasks on macOS, recording every run. At least one task must use vision, one the Electron page path, and one must finish with zero vision calls.

## What is already here

`code/computer/` holds the full skill. `STATUS.md` is the handoff: the `vscode` task passes end to end; `calculator` and `canvas` are written but never run; two small reporting bugs are listed. The unrun tasks need macOS Accessibility and Screen Recording permission and the gateway running.

## How it fits the capstone

Low value for the capstone and not part of the Sunday 22 Nov scope. It still has to be finished and submitted.

## Step 1: read, then pitch. Write no code yet.

Read `Assignment.md`, the lecture, the notes file and every code file in this folder. Then reply to Aryaman with:

- A plain-English summary of what exists and whether it runs (run the tests and show the output).
- A checklist of each thing the brief asks for, marked done, partly done or missing.
- A short plan for the two unrun tasks and the two known bugs, and exactly what Aryaman must do by hand (grant permissions, start the gateway).
- Anything you are blocked on (keys, course code not yet in the folder, permissions, real data).

Then stop and wait for Aryaman's direction.

## Step 2: build what Aryaman picks

Fix the two known bugs in `STATUS.md`. After Aryaman grants the permissions, run `calculator` and `canvas`, fix what breaks, and keep the recorded runs as evidence.

## Rules

- Existing code is taken to its natural finish. Extend it; never overwrite or restart it.
- Hand-written code only. No agent frameworks (LangChain, LangGraph, CrewAI, AutoGen).
- Turn Aryaman's examples into tests first, then write the least code that passes them.
- Never delete, skip or loosen a test to make it pass. If a test looks wrong, say so and stop.
- Use `uv` for Python. Ask before adding any dependency.
- Keys come from `.env` only. Never hardcode, print, log or commit them.
- Stay inside this folder. One task per commit. Show test output before calling anything done.
- Aryaman pulls course repos and opens pull requests himself. If course code is missing, ask him for it.
