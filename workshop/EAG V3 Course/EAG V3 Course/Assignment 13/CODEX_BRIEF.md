# Assignment 13: finish-it brief for Codex

Review date: Tuesday 17 Nov 2026. Push to `eag-v3-assignment-13` (see `REPO.md`).

## What the assignment is

Reproduce four benchmark cases on glc_v3 and name one honest limitation. Then build one meaningful extension in one track (live graph, memory, semantic indexing or A2A), prove it with an end-to-end run, and attack it with one adversarial test shown failing before the fix and passing after. Submit one pull request with one README section.

## What is already here

Untouched course code: `glc_v3/` (reference only), `S13Code-2/` (where the change goes) and `S13Proof/`. No extension has been started.

## How it fits the capstone

The memory track fits best. "A correction with preserved history, and provenance in the final answer" is exactly what the capstone needs to remember a misconception Aryaman once held (ask 2) and to say where a claim was established (ask 1).

## Step 1: read, then pitch. Write no code yet.

Read `Assignment.md`, the lecture, the notes file and every code file in this folder. Then reply to Aryaman with:

- A plain-English summary of what exists and whether it runs (run the tests and show the output).
- A checklist of each thing the brief asks for, marked done, partly done or missing.
- Two or three extension ideas, at least one from the memory track, each with the user-visible capability, the proof run and the adversarial test it would need.
- Anything you are blocked on (keys, course code not yet in the folder, permissions, real data).

Then stop and wait for Aryaman's direction.

## Step 2: build what Aryaman picks

Reproduce the four cases first and keep the traces. Then build the chosen extension, its proof and its adversarial test, and write the single README section the brief lists. Use made-up test identities only.

## Rules

- Existing code is taken to its natural finish. Extend it; never overwrite or restart it.
- Hand-written code only. No agent frameworks (LangChain, LangGraph, CrewAI, AutoGen).
- Turn Aryaman's examples into tests first, then write the least code that passes them.
- Never delete, skip or loosen a test to make it pass. If a test looks wrong, say so and stop.
- Use `uv` for Python. Ask before adding any dependency.
- Keys come from `.env` only. Never hardcode, print, log or commit them.
- Stay inside this folder. One task per commit. Show test output before calling anything done.
- Aryaman pulls course repos and opens pull requests himself. If course code is missing, ask him for it.
