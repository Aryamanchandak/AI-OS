# Decisions

- 2026-11-14: Standard library only, no added dependencies. A local single-user app needs nothing more, and it avoids a dependency decision.
- 2026-11-14: The engine's JSON journal (`GET /v1/agent/runs/{id}`) is polled instead of its AG-UI event stream. The AG-UI mapping drops the capability name and the nodes a planner patch added.
- 2026-11-14: Interpretation calls glc_v5 `/v1/chat` directly; only generation goes through S17Code. A full engine run for one structured reply costs three or more model calls.
- 2026-11-14: Generated tools keep their arithmetic in one `<script id="calc">` block. The check runs that block alone in Node's `vm`, so no browser or jsdom is needed.
- 2026-11-14: Documents are `.txt`/`.md` only. No real sample document exists yet, so no extraction library was chosen.
- 2026-11-14: One build at a time. S17Code reads one workspace path from its environment.
- 2026-11-14: The app re-runs the check itself after every run, under Node's permission mode. The engine's report of success is not trusted as the result.
- 2026-11-14: After any follow-up, every known answer must be re-confirmed. They were worked out under the old rules.
- 2026-11-14: S17Code and glc_v5 are git-ignored here and patched from `upstream/`. They are separate repositories with their own history.
