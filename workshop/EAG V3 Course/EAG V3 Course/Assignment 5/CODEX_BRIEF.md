# Assignment 5: finish-it brief for Codex

Review date: Tuesday 17 Nov 2026. Push to `eag-v3-assignment-05` (see `REPO.md`).

## What the assignment is

Take a prompt, have it qualified against the lecture's prompt rules, build something new on that qualified prompt, and share a README showing the prompt passing the evaluation, plus a video. It must be multi-step, and must not be a summariser or a stock or crypto analyser.

## What is already here

`veritas/` is a working claim-verification agent (decompose, search PubMed and arXiv, extract, grade, synthesise, audit) with a later essay mode and a Streamlit screen. `prompt_plan_workbench/` and `bridge/` sit beside it. `EVALUATION.md` and several prompt files are at the top. It is unclear which parts are the submission.

## How it fits the capstone

Veritas is the closest existing thing to ask 1 (claim checking). The prompt-qualification rules are also how the capstone's grading prompts (ask 2) should be judged. Aryaman's note asks: what does this lecture offer, and how can it be folded into our system? Answer that in the pitch.

## Step 1: read, then pitch. Write no code yet.

Read `Assignment.md`, the lecture, the notes file and every code file in this folder. Then reply to Aryaman with:

- A plain-English summary of what exists and whether it runs (run the tests and show the output).
- A checklist of each thing the brief asks for, marked done, partly done or missing.
- A direct answer to Aryaman's note, plus two or three options for what the submission should be (Veritas as is, Veritas plus the workbench, or a narrower piece), with what each still needs.
- Anything you are blocked on (keys, course code not yet in the folder, permissions, real data).

Then stop and wait for Aryaman's direction.

## Step 2: build what Aryaman picks

Finish the chosen option: a README that shows the final qualified prompt and its evaluation output, tests that pass, and a run with real keys.

## Rules

- Existing code is taken to its natural finish. Extend it; never overwrite or restart it.
- Hand-written code only. No agent frameworks (LangChain, LangGraph, CrewAI, AutoGen).
- Turn Aryaman's examples into tests first, then write the least code that passes them.
- Never delete, skip or loosen a test to make it pass. If a test looks wrong, say so and stop.
- Use `uv` for Python. Ask before adding any dependency.
- Keys come from `.env` only. Never hardcode, print, log or commit them.
- Stay inside this folder. One task per commit. Show test output before calling anything done.
- Aryaman pulls course repos and opens pull requests himself. If course code is missing, ask him for it.
