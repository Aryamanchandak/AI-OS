# Assignment 15: finish-it brief for Codex

Review date: Tuesday 17 Nov 2026. Push to `eag-v3-assignment-15` (see `REPO.md`).

## What the assignment is

Reproduce the two test suites and five proofs. Then build a routing and budget policy (which model tier handles which task, and when to stop spending) for a workload of at least fifteen tasks from your own domain. Measure cost per call and cost per resolved task against always using the top model, find the break-even point, show one task the policy got wrong, and attack the budget with an adversarial test. Submit a pull request with one evidence section.

## What is already here

Untouched course code: `S15Code/` and `glc_v4/`. No policy or task file has been started.

## How it fits the capstone

High value. The capstone's gateway needs a grading profile: which model grades a recall answer, and at what cost. Using recall-answer grading as the workload makes this assignment the measurement behind that choice.

## Step 1: read, then pitch. Write no code yet.

Read `Assignment.md`, the lecture, the notes file and every code file in this folder. Then reply to Aryaman with:

- A plain-English summary of what exists and whether it runs (run the tests and show the output).
- A checklist of each thing the brief asks for, marked done, partly done or missing.
- Two or three workloads, at least one being recall-answer grading on Aryaman's study cards, each with where the fifteen real tasks would come from. The tasks must be real ones from Aryaman, so ask him for them.
- Anything you are blocked on (keys, course code not yet in the folder, permissions, real data).

Then stop and wait for Aryaman's direction.

## Step 2: build what Aryaman picks

Reproduce the floor first and keep the four captured runs. Then build the policy, the task file, the judge and the adversarial test, and write the evidence section.

## Rules

- Existing code is taken to its natural finish. Extend it; never overwrite or restart it.
- Hand-written code only. No agent frameworks (LangChain, LangGraph, CrewAI, AutoGen).
- Turn Aryaman's examples into tests first, then write the least code that passes them.
- Never delete, skip or loosen a test to make it pass. If a test looks wrong, say so and stop.
- Use `uv` for Python. Ask before adding any dependency.
- Keys come from `.env` only. Never hardcode, print, log or commit them.
- Stay inside this folder. One task per commit. Show test output before calling anything done.
- Aryaman pulls course repos and opens pull requests himself. If course code is missing, ask him for it.
