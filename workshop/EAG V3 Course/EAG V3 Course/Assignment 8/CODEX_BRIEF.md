# Assignment 8: finish-it brief for Codex

Review date: Tuesday 17 Nov 2026. Push to `eag-v3-assignment-08` (see `REPO.md`).

## To do when the API key is ready

Saved checkpoint: `1f2770a` is pushed to the assignment repo. Active agent verification: `110 passed, 14 warnings in 4.76s`. Submission evidence is still incomplete.

- [ ] Aryaman: copy `DAG Agent/.env.example` to `DAG Agent/.env` and fill in `ANTHROPIC_API_KEY` locally. Keep the key out of chat and Git.
- [ ] Aryaman: tell Codex, "Assignment 8: the key is in the local .env. Continue the checklist in CODEX_BRIEF.md."
- [ ] Codex: check the local key is configured without displaying it, then run one live comparison end to end and have Aryaman judge its answer against the supplied sources.
- [ ] Codex: check the available course material for the exact five base-query limits and patched Session 8 starter. If missing, ask Aryaman to provide the course code or limits.
- [ ] Codex: run the five base queries (`hello`, `A`, `I`, `J`, `K`) verbatim, including interruption and resume, and save fresh logs with timings and step counts against the confirmed limits.
- [ ] Codex: capture live evidence for three independent branches running together; Critic pass and fail followed by successful recovery; Coder computation; and the added skill. Clearly distinguish live evidence from historical or scripted logs.
- [ ] Codex: report any failures or required behaviour changes before changing code; rerun the relevant tests after approved fixes.
- [ ] Codex: update `DAG Agent/README.md` with results and log links for all five assignment parts, and show verification output for review before committing.
- [ ] Aryaman: review the results, then record and upload the YouTube demo showing all five parts. Add the video link to the README.
- [ ] Aryaman: approve the final commit and push, then submit the README and video links to the course.

## What the assignment is

Build a DAG-based agent (one that plans its work as a graph of steps, some run side by side). Pass five base queries, show one query with three parallel branches, one where the Critic both passes and fails and recovers, fill in the Coder skill, and add one new skill through config and a prompt file only. Submit a video and a README with logs for all five parts.

## What is already here

`DAG Agent/` is the active assignment workspace, copied from the existing agent without behaviour changes. The three original projects are preserved under `Previous Implementations/`: `Assignment 8 existing/`, `Consequence And What if?/`, and `What If Analyser ?/`.

The old proposal is archived at `Previous Implementations/INTEGRATION_PLAN.md`; it is not the selected approach. Keep the scenario applications separate while finishing the DAG assignment. Verified on 2026-11-13: original DAG agent 62 passed; What If Analyser 24 passed; Consequence Radar 69 passed and 1 failed. The Radar failure accesses `claims` on the candidate-selection schema; do not silently change the test.

## How it fits the capstone

The scenario engine is the pattern behind ask 3 (strongest case against my view) and ask 4 (what did I predict, and was I right): it produces predictions that can be scored later.

## Step 1: read, then pitch. Write no code yet.

Read `DAG Agent/Assignment.md`, the lecture, and the active agent code. The initial review and folder consolidation are complete; discuss the proposed behaviour changes before implementation. Then reply to Aryaman with:

- A plain-English summary of what exists and whether it runs (run the tests and show the output).
- A checklist of each thing the brief asks for, marked done, partly done or missing.
- Two or three consolidation shapes for these three projects (for example: one repo with the engine as the agent's new skill; keep them apart and submit the agent alone), each with what moves, what is dropped and the risk. Do not move or merge any file until Aryaman has said what the consolidation should look like.
- Anything you are blocked on (keys, course code not yet in the folder, permissions, real data).

Then stop and wait for Aryaman's direction.

## Runtime decision

Aryaman explicitly requires independent operation: `DAG Agent/` calls the model provider directly through `agent/llm.py`. Do not reconnect it to the AI OS gateway, shared configuration, shared services, or shared database. Provider credentials belong only in the agent’s local `.env`. Supplied-evidence mode runs without a model key.

## Step 2: finish the selected DAG agent

Extend `DAG Agent/` in place. Keep the archived implementations unchanged. Preserve all 62 existing agent tests and add acceptance tests for the base queries, Critic gating, and resume before implementation. The base-query wording is in `lecture.md`; the exact acceptance bounds and patched Session 8 starter still need confirmation. Cover all five assignment parts with honest logs in the agent README.

## Rules

- Existing code is taken to its natural finish. Extend it; never overwrite or restart it.
- Hand-written code only. No agent frameworks (LangChain, LangGraph, CrewAI, AutoGen).
- Turn Aryaman's examples into tests first, then write the least code that passes them.
- Never delete, skip or loosen a test to make it pass. If a test looks wrong, say so and stop.
- Use `uv` for Python. Ask before adding any dependency.
- Keys come from `.env` only. Never hardcode, print, log or commit them.
- Stay inside this folder. One task per commit. Show test output before calling anything done.
- Aryaman pulls course repos and opens pull requests himself. If course code is missing, ask him for it.
