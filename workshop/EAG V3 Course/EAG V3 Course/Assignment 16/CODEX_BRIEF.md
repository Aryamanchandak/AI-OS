# Assignment 16: finish-it brief for Codex

Review date: Tuesday 17 Nov 2026. Push to `eag-v3-assignment-16` (see `REPO.md`).

## What the assignment is

Build a personal executive assistant that works on five live channels, with a written subscription (what it watches, what it may do, what it may spend). On video, show five live conversations, something it chose to ignore and why, a question it waited on across a restart, and the morning report and liveness alarm. Separately, fix one real bug in glc_v5 or S16Code with a pull request. The assistant's code is not submitted.

## What is already here

Only the brief, the lecture and Aryaman's note. Related code elsewhere in the AI OS repo: `Multi Channel/switchboard` and `Lecture 11/glc_v1_whatsapp` in the course folder. glc_v5 and S16Code are not in this folder yet.

## How it fits the capstone

High value. This is the capstone's Telegram surface and ask 5 ("given my calendar and backlog, what now?"). The subscription with limits is the capstone's charter in working form. Aryaman's note: a great reason to build the multiple surfaces we want, and to do it well.

## Step 1: read, then pitch. Write no code yet.

Read `Assignment_16.md`, the lecture, the notes file and every code file in this folder. Then reply to Aryaman with:

- A plain-English summary of what exists and whether it runs (run the tests and show the output).
- A checklist of each thing the brief asks for, marked done, partly done or missing.
- Which five channels to use and why, a draft subscription with spending ceilings, and two or three candidate bugs for the pull request once the course code is in the folder.
- Anything you are blocked on (keys, course code not yet in the folder, permissions, real data).

Then stop and wait for Aryaman's direction.

## Step 2: build what Aryaman picks

Build read-only first, with "ask first" on anything that leaves the machine. This repo is private and must stay so: no tokens, sessions or real messages are ever committed.

## Rules

- Existing code is taken to its natural finish. Extend it; never overwrite or restart it.
- Hand-written code only. No agent frameworks (LangChain, LangGraph, CrewAI, AutoGen).
- Turn Aryaman's examples into tests first, then write the least code that passes them.
- Never delete, skip or loosen a test to make it pass. If a test looks wrong, say so and stop.
- Use `uv` for Python. Ask before adding any dependency.
- Keys come from `.env` only. Never hardcode, print, log or commit them.
- Stay inside this folder. One task per commit. Show test output before calling anything done.
- Aryaman pulls course repos and opens pull requests himself. If course code is missing, ask him for it.
