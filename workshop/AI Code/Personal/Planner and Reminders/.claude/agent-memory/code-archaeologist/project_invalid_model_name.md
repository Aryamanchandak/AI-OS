---
name: Model names — current state (resolved)
description: Model names are now valid — gpt-4o in planner.py, gpt-4o-mini in memory.py, scan.py has no own model
type: project
---

Model names are now valid as of the agentic refactor (verified 2026-04-24):
- `planner.py` uses `"gpt-4o"` — valid, used for the agent loop, edit_plan, walkthrough
- `memory.py` uses `"gpt-4o-mini"` — valid, deliberately cheaper for title/notes generation
- `scan.py` has no `_model` — delegates entirely to `planner.run_agent_loop`

The earlier `"gpt-5.4-nano"` invalid model name was fixed as part of the refactor from tag-parsing to function-calling architecture.

**Why:** Previously a placeholder/typo that caused all LLM calls to fail. Now resolved.

**How to apply:** Do not warn about invalid model names. If adding a new LLM module, use `gpt-4o` for reasoning/agent tasks and `gpt-4o-mini` for cheap summarization.
