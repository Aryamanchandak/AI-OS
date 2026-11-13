# Assignment 9: finish-it brief for Codex

Review date: Tuesday 17 Nov 2026. Push to `eag-v3-assignment-09` (see `REPO.md`).

## What the assignment is

Build a browser agent that completes one real comparison task with at least three visible browser actions, and a replay view of the run: goal, plan graph, browser path chosen, actions, screenshots, extracted data, final table, step count and cost. The orchestrator must not be modified. Submit a video, a repo, the replay trace, the comparison output and a short architecture note.

## What is already here

`S9/code/` is the course agent with a new `report.py` replay viewer, a fixture builder and tests. `llm_gatewayV9/` is the gateway. `ARCHITECTURE.md`, `ideas.md` and `S9/code/VALIDATION.md` describe the design and an earlier run. A real end-to-end run needs a provider key.

## How it fits the capstone

This is the capstone's reader (turning a real page into usable input). It is unlikely to make the Sunday 22 Nov deadline, so finish it as an assignment and keep it portable.

## Step 1: read, then pitch. Write no code yet.

Read `Assignment.md`, the lecture, the notes file and every code file in this folder. Then reply to Aryaman with:

- A plain-English summary of what exists and whether it runs (run the tests and show the output).
- A checklist of each thing the brief asks for, marked done, partly done or missing.
- Which comparison task to submit, with two or three candidates and why each is safe to demo.
- Anything you are blocked on (keys, course code not yet in the folder, permissions, real data).

Then stop and wait for Aryaman's direction.

## Step 2: build what Aryaman picks

Run the chosen task for real with a key, produce the replay report and the comparison table, and add the evidence to the README.

## Rules

- Existing code is taken to its natural finish. Extend it; never overwrite or restart it.
- Hand-written code only. No agent frameworks (LangChain, LangGraph, CrewAI, AutoGen).
- Turn Aryaman's examples into tests first, then write the least code that passes them.
- Never delete, skip or loosen a test to make it pass. If a test looks wrong, say so and stop.
- Use `uv` for Python. Ask before adding any dependency.
- Keys come from `.env` only. Never hardcode, print, log or commit them.
- Stay inside this folder. One task per commit. Show test output before calling anything done.
- Aryaman pulls course repos and opens pull requests himself. If course code is missing, ask him for it.
