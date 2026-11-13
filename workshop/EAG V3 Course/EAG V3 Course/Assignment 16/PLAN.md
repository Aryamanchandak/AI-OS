# Personal Watchlist Assistant

Build a screener that watches selected sources against a question you write, identifies meaningful changes, and helps you decide what deserves attention or follow-up.

## First version

Start with a few public web pages and one watch question, such as: “Track changes to these companies’ expansion plans.” Save an initial baseline, then compare later versions against it. The first capture establishes context; it is not reported as a new change. Podcasts, audio transcription and communication channels are outside this first version.

Each watch records its URLs, question, checking frequency and spending ceilings. Incoming page content is evidence only: it cannot change the watch, grant permissions or trigger external actions. Use only sources you explicitly select.

## What it produces

Attention: identify relevant changes, rank their importance and explain why they matter to your question. Record why repeated announcements, unrelated edits and weak matches were ignored.

Preparation: produce a local Markdown brief containing what changed, the previous and current evidence, source links, observation times and unresolved questions. Separate observed facts from interpretations.

Follow-through: suggest a task or draft a question when a change may require action. If your intent is unclear, save the question and resume the same item after your answer, including after a restart. Suggestions remain local; sending messages, creating external tasks and other external changes require approval.

## Next implementation step

First, you provide a few public URLs, one watch question and examples of a relevant change and an irrelevant change. Confirm checking frequency and spending ceilings before any paid run. Turn those examples into tests before implementation.

Inspect the existing course code and reusable project components before choosing libraries. Reuse existing fetching, scheduling and storage plumbing behind thin adapters; ask before adding dependencies. Keep all model calls on the AI OS gateway path. Any required trunk changes need your approval before implementation.

Implement and verify one journey: capture baseline → capture changed page → compare → assess relevance → save the decision and evidence → generate the local brief. Verify fetching on your chosen real pages before connecting the remaining stages. Record fetch or model failures explicitly rather than treating them as “no change.”

Persist source versions, decisions and waiting items locally. Avoid processing the same source version twice. Set checking and spending limits before operation, and expose when monitoring last succeeded so a quiet source can be distinguished from failed monitoring.

## Done when

- A known relevant change is reported with accurate before-and-after evidence and a source link.
- A repeated announcement and an irrelevant edit are ignored with recorded reasons.
- Rechecking unchanged content creates no duplicate finding.
- A saved clarification survives restart and your answer completes the same item.
- A report shows findings, ignored changes, failures, pending questions and monitoring status.
- Agreed limits hold, relevant tests pass with their actual output shown, and you review the real-page results before a commit.

## Later fit

This combines screening, attention, preparation and follow-through as one capability: “watch this for me.” It can later supply findings to AI OS. It partially addresses Assignment 16; five live communication channels, an independently observed liveness alarm and a verified course-code bug-fix pull request remain separate requirements. No podcast support or additional integration is planned in this step.
