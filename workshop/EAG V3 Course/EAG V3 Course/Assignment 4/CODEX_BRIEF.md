# Assignment 4: finish-it brief for Codex

Review date: Tuesday 17 Nov 2026. Push to `eag-v3-assignment-04` (see `REPO.md`).

## What the assignment is

Write an MCP server (a program that offers tools to an AI agent) with three tools: one that uses the internet, one that creates, reads, updates and deletes in a local file, and one that shows a screen built with Prefab. Then show one prompt that makes an agent use all three. Submit a YouTube demo and a GitHub link. 500 points base, up to 2,500 for pushing Prefab further.

## What is already here

Complete code: `server.py` (three tools), `notes_store.py`, `ui.py`, `preview.py`. 15 offline tests pass. One test marked `network` has never been run. No agent has yet been driven through all three tools with a real model.

## How it fits the capstone

This is the tool boundary the capstone needs. The notes file already carries `verified` and `unverified` status, which is the seed of the claim store behind ask 1 ("is this claim true, and where did I already establish it?"). Aryaman's note: write it all by hand here; it gets swapped for open-source parts later.

## Step 1: read, then pitch. Write no code yet.

Read `Assignment.md`, the lecture, the notes file and every code file in this folder. Then reply to Aryaman with:

- A plain-English summary of what exists and whether it runs (run the tests and show the output).
- A checklist of each thing the brief asks for, marked done, partly done or missing.
- Two or three ideas for a richer Prefab screen that would lift the score above the 500 base, each with what it reuses and how long it takes.
- Anything you are blocked on (keys, course code not yet in the folder, permissions, real data).

Then stop and wait for Aryaman's direction.

## Step 2: build what Aryaman picks

Run the tests marked `live` and `network` with real keys in `.env` (`uv run pytest -m "live or network"`). They have never been run. Fix what breaks in the code, not in the tests. Then drive the server from a real MCP client with one prompt that uses all three tools, and paste the logs into the README.

## Rules

- Existing code is taken to its natural finish. Extend it; never overwrite or restart it.
- Hand-written code only. No agent frameworks (LangChain, LangGraph, CrewAI, AutoGen).
- Turn Aryaman's examples into tests first, then write the least code that passes them.
- Never delete, skip or loosen a test to make it pass. If a test looks wrong, say so and stop.
- Use `uv` for Python. Ask before adding any dependency.
- Keys come from `.env` only. Never hardcode, print, log or commit them.
- Stay inside this folder. One task per commit. Show test output before calling anything done.
- Aryaman pulls course repos and opens pull requests himself. If course code is missing, ask him for it.
