# Assignment 8: finish-it brief for Codex

Review date: Tuesday 17 Nov 2026. Push to `eag-v3-assignment-08` (see `REPO.md`).

## What the assignment is

Build a DAG-based agent (one that plans its work as a graph of steps, some run side by side). Pass five base queries, show one query with three parallel branches, one where the Critic both passes and fails and recovers, fill in the Coder skill, and add one new skill through config and a prompt file only. Submit a video and a README with logs for all five parts.

## What is already here

Three separate projects: `Assignment 8 existing/` (the DAG agent), `Consequence And What if?/` (a causal scenario engine) and `What If Analyser ?/`. `INTEGRATION_PLAN.md` proposes merging two of them and records test baselines of 58 and 8 passing.

## How it fits the capstone

The scenario engine is the pattern behind ask 3 (strongest case against my view) and ask 4 (what did I predict, and was I right): it produces predictions that can be scored later.

## Step 1: read, then pitch. Write no code yet.

Read `Assignment 8 existing/Assignment.md`, the lecture, the notes file and every code file in this folder. Then reply to Aryaman with:

- A plain-English summary of what exists and whether it runs (run the tests and show the output).
- A checklist of each thing the brief asks for, marked done, partly done or missing.
- Two or three consolidation shapes for these three projects (for example: one repo with the engine as the agent's new skill; keep them apart and submit the agent alone), each with what moves, what is dropped and the risk. Do not move or merge any file until Aryaman has said what the consolidation should look like.
- Anything you are blocked on (keys, course code not yet in the folder, permissions, real data).

Then stop and wait for Aryaman's direction.

## Step 2: build what Aryaman picks

Carry out the consolidation Aryaman describes, keeping both test baselines passing, then cover the five parts of the brief with logs in the README.

## Rules

- Existing code is taken to its natural finish. Extend it; never overwrite or restart it.
- Hand-written code only. No agent frameworks (LangChain, LangGraph, CrewAI, AutoGen).
- Turn Aryaman's examples into tests first, then write the least code that passes them.
- Never delete, skip or loosen a test to make it pass. If a test looks wrong, say so and stop.
- Use `uv` for Python. Ask before adding any dependency.
- Keys come from `.env` only. Never hardcode, print, log or commit them.
- Stay inside this folder. One task per commit. Show test output before calling anything done.
- Aryaman pulls course repos and opens pull requests himself. If course code is missing, ask him for it.
