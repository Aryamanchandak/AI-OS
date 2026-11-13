# Assignment 6: finish-it brief for Codex

Review date: Tuesday 17 Nov 2026. Push to `eag-v3-assignment-06` (see `REPO.md`).

## What the assignment is

Build an agent with four separate layers (memory, perception, decision, action), typed with Pydantic on every boundary, calling models only through the gateway and tools only through the MCP server. It must pass four target queries within twice the expected step count, and remember a fact across runs. Submit a repo whose README shows real terminal output for all four queries, plus a video.

## What is already here

Complete code for the four layers, `agent6.py`, `schemas.py`, `gateway.py` and `mcp_server.py`. 21 offline tests pass. 7 tests marked `live` or `network`, including the four target queries, have never been run with real keys.

## How it fits the capstone

This is the hand-written agent loop the capstone rules require, so it is the natural base for the capstone's orchestrator. Aryaman's note: `workshop/AI Code/AI Agent` in the AI OS repo is a more advanced version of this; compare the two and say what is worth bringing across.

## Step 1: read, then pitch. Write no code yet.

Read `Assignment.md`, the lecture, the notes file and every code file in this folder. Then reply to Aryaman with:

- A plain-English summary of what exists and whether it runs (run the tests and show the output).
- A checklist of each thing the brief asks for, marked done, partly done or missing.
- A short comparison with the AI Agent module and two or three ideas for what to bring across without breaking the assignment's rules.
- Anything you are blocked on (keys, course code not yet in the folder, permissions, real data).

Then stop and wait for Aryaman's direction.

## Step 2: build what Aryaman picks

Run the tests marked `live` and `network` with real keys in `.env` (`uv run pytest -m "live or network"`). They have never been run. Fix what breaks in the code, not in the tests. Run the four target queries from a clean `state/` folder, check each stays within its step limit, and paste the real terminal output into the README.

## Rules

- Existing code is taken to its natural finish. Extend it; never overwrite or restart it.
- Hand-written code only. No agent frameworks (LangChain, LangGraph, CrewAI, AutoGen).
- Turn Aryaman's examples into tests first, then write the least code that passes them.
- Never delete, skip or loosen a test to make it pass. If a test looks wrong, say so and stop.
- Use `uv` for Python. Ask before adding any dependency.
- Keys come from `.env` only. Never hardcode, print, log or commit them.
- Stay inside this folder. One task per commit. Show test output before calling anything done.
- Aryaman pulls course repos and opens pull requests himself. If course code is missing, ask him for it.
