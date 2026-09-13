# Activation state — Plan 01 Work Package E

Per the program roadmap (`To Do/Gateway to do/GLC and ingestion gateway migration/00-program-roadmap.md`)
and program rules therein. This is "is it mounted/started by default once it
lands," independent of "does it get moved" — everything in scope gets moved.
Recorded here once so Plans 03 and 05 don't each re-decide it.

| Domain | Plan | Lands as | Why |
|---|---|---|---|
| Gateway foundation (DI, lifecycle, config, existing ingestion surface) | 02 | Active | It's the container everything else mounts into; nothing dormant about infrastructure that's already load-bearing today (gateway already serves `/api/ingestion/*`). |
| Security, audit, control | 03 | **Always-on, active** | Program rules: "always-on, fail-hard for security-critical configuration... not part of the dormancy decision." Not eligible for dormant status by design, regardless of what else is toggled. |
| LLM orchestration and providers | 04 | Active | Core function already serving live traffic (ingestion's `glc.client.LLM` calls, once inside the process, become the in-process `LLMService` — same active usage, different transport). |
| Channels and voice | 05 | **Dormant by default** | Program roadmap: "moved under Gateway but registered disabled by default (not mounted, no worker started) until explicitly turned on. Aryaman doesn't use most of these today and doesn't want them live just because the code moved." Still gets full characterization tests before Plan 05's exit gate — dormant is not the same as untested. |
| Ingestion (API, coordinator, pipeline, readers, writers) | 06 | Active | It's the working, routinely-used pipeline; ingestion is a peer caller of GLC's LLM domain both before and after the move, not something newly enabled. |

No domain in this sequence is ambiguous between active/dormant; the only
domain the program roadmap flagged as needing an explicit dormancy rule
(channels/voice) already has one on record above.
