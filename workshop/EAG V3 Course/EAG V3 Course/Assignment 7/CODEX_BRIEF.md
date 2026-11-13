# Assignment 7: finish-it brief for Codex

Review date: Tuesday 17 Nov 2026. Push to `eag-v3-assignment-07` (see `REPO.md`).

## What the assignment is

Build something that uses RAG (retrieval: finding the right stored text before answering) over a corpus of 50 or more items. Pass eight base queries (A to H) within their step limits. Design five queries that succeed with the index and fail without it; two must need semantic recall, where the query's words do not appear in the answering text. Submit a repo with the corpus list and all traces, plus a video.

## What is already here

Complete code: the Assignment 6 agent plus `vector_index.py`, `build_corpus.py` and document-indexing tools. 44 offline tests pass. 11 tests marked `live` or `network` have never been run. `sandbox/corpus/` holds 6 documents, well short of 50.

## How it fits the capstone

This is ask 1's second half: "where did I already establish it?" answered from Aryaman's own corpus. Aryaman's notes: use the ingestion pipeline here and for the capstone, and he likes the idea of indexing the intellectual websites he visits.

## Step 1: read, then pitch. Write no code yet.

Read `Assignment.md`, the lecture, the notes file and every code file in this folder. Then reply to Aryaman with:

- A plain-English summary of what exists and whether it runs (run the tests and show the output).
- A checklist of each thing the brief asks for, marked done, partly done or missing.
- Two or three ways to reach a 50-item corpus (the ingestion pipeline, indexing visited pages, or the corpus builder), with what each reuses.
- Anything you are blocked on (keys, course code not yet in the folder, permissions, real data).

Then stop and wait for Aryaman's direction.

## Step 2: build what Aryaman picks

Run the tests marked `live` and `network` with real keys in `.env` (`uv run pytest -m "live or network"`). They have never been run. Fix what breaks in the code, not in the tests. Grow the corpus to 50 or more items, run the eight base queries and the five custom ones with and without the index, and put the traces in the README.

## Rules

- Existing code is taken to its natural finish. Extend it; never overwrite or restart it.
- Hand-written code only. No agent frameworks (LangChain, LangGraph, CrewAI, AutoGen).
- Turn Aryaman's examples into tests first, then write the least code that passes them.
- Never delete, skip or loosen a test to make it pass. If a test looks wrong, say so and stop.
- Use `uv` for Python. Ask before adding any dependency.
- Keys come from `.env` only. Never hardcode, print, log or commit them.
- Stay inside this folder. One task per commit. Show test output before calling anything done.
- Aryaman pulls course repos and opens pull requests himself. If course code is missing, ask him for it.
