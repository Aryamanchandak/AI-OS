# Assignment 17: finish-it brief for Codex

Review date: Tuesday 17 Nov 2026. Push to `eag-v3-assignment-17` (see `REPO.md`).

## What the assignment is

Build a product on top of S17Code (the engine), with your own front end, where the run is visible: nodes appearing, commands running, a test going red then green, and a failure shown too. Separately, fix a real bug in glc_v5 or S17Code with a failing-then-passing test. Say plainly which parts the agent wrote and which Aryaman wrote.

## What is already here

Only the brief and the lecture. No code. S17Code is not in this folder yet; Aryaman will pull it in.

## How it fits the capstone

Medium value. A notebook-style product over Aryaman's own study notes (notes in, cards and explanations out, with the run visible) would double as a front end for the learning loop. It is unlikely to make the Sunday 22 Nov deadline.

## Step 1: read, then pitch. Write no code yet.

Read `assignment.md`, the lecture, the notes file and every code file in this folder. Then reply to Aryaman with:

- A plain-English summary of what exists and whether it runs (run the tests and show the output).
- A checklist of each thing the brief asks for, marked done, partly done or missing.
- Two or three product ideas, at least one being the study-notes product above, each with what the user sees and what the visible run looks like.
- Anything you are blocked on (keys, course code not yet in the folder, permissions, real data).

Then stop and wait for Aryaman's direction.

## Step 2: build what Aryaman picks

Once S17Code is in the folder and Aryaman has chosen, build the product and find the bug for the pull request.

## Rules

- Existing code is taken to its natural finish. Extend it; never overwrite or restart it.
- Hand-written code only. No agent frameworks (LangChain, LangGraph, CrewAI, AutoGen).
- Turn Aryaman's examples into tests first, then write the least code that passes them.
- Never delete, skip or loosen a test to make it pass. If a test looks wrong, say so and stop.
- Use `uv` for Python. Ask before adding any dependency.
- Keys come from `.env` only. Never hardcode, print, log or commit them.
- Stay inside this folder. One task per commit. Show test output before calling anything done.
- Aryaman pulls course repos and opens pull requests himself. If course code is missing, ask him for it.
