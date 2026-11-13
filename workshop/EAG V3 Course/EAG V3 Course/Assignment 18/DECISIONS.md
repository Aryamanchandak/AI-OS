# Decisions

- 2026-11-14: Hand-written harness instead of forking S18Code. S18Code was not in the folder and the course asks for hand-written code.
- 2026-11-14: Standard library only (`unittest`, `urllib`). No dependency to approve or pin.
- 2026-11-14: Local `gemma4:12b` through Ollama with thinking off and replies capped at 1500 tokens. With thinking on, one step took 4.5 minutes and the server errored.
- 2026-11-14: Ollama's "token repeat limit reached" abort is journaled as an unusable reply, not a server failure. The model was generating; it got stuck.
- 2026-11-14: The grader restores protected paths before the acceptance check. A shortcut that edits the tests cannot produce a pass.
- 2026-11-14: Journals are never overwritten. A rerun needs a new repeat number.
