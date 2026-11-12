# Study System

Reusable learning logic for deterministic card generation, FSRS review, and
Feynman/challenger practice. This repo is a pure library — no MCP server, no
automation runner, no adapter code of any kind. Runtime data is stored under
the central `Database/` root rather than this repository. Two sibling
projects import this package as a library and call `StudyCore`:

- the separate `mcp_server` project's `study` group (the MCP surface, ten
  tools) — see `plans/09_MCP_ADAPTER_RELOCATION.md`;
- the separate `study-automation` project (the headless generation job and
  its shell launcher) — see `plans/10_AUTOMATION_ADAPTER_RELOCATION_PLAN.md`.

## Quick start

```bash
# 1. Clone and install
pip install -e ".[dev]"

# 2. Configure config/baseline.json
# Set kg_concepts_path and vector_snippets_path to final read-only exports.
# The default LLM gateway is http://127.0.0.1:8107.

# 3. Verify unattended dependencies without generating cards, and run one
# locked generation batch, from the sibling study-automation project:
cd ../study-automation
python generate.py --check
./scripts/run_study_automation.sh
```

This repo has no MCP server of its own. The tools below are exposed by the
`study` group in the separate shared `mcp_server` project
(`/Users/aryamanchandak/Documents/AI Code/mcp_server/tools/study/`), which
imports this package as a library. Run that project's server to exercise the
tools; see `plans/09_MCP_ADAPTER_RELOCATION.md`.

## Plan 02 capabilities

`mcp_server`'s `study` group exposes exactly:

- `study_generate_cards`
- `study_get_due_cards`
- `study_submit_review`
- `study_start_feynman` / `study_evaluate_feynman`
- `study_start_challenger` / `study_grade_challenger`
- `study_progress`
- `study_set_temporary_override` / `study_cancel_temporary_override`

All write tools accept an idempotency key and create one when omitted.
Overrides are allowlisted, bounded, attributed, expiring, and stored separately
from the read-only baseline file. `study_progress` includes final-KG coverage,
unseen concepts, due reviews, recent generation/review/practice activity, and
active override records.

Feynman and challenger starts are deterministic, read-only calls. They return
a stateless concept handle; the chat client passes that handle and its
`conversation_so_far` on evaluation. Only completed evaluation evidence is
audited. The central SQLite database therefore contains exactly the four
approved tables: `cards`, `review_state`, `generation_runs`, and `overrides`.

These tools are also the chat-experience contract: the unified chat presents
due cards and controls answer reveal, submits FSRS ratings, starts generation
or temporary campaigns, conducts Feynman/challenger turns, and renders basic
progress. No learning or scheduling logic is duplicated in a chat client.

## Baseline configuration

`config/baseline.json` controls generation/review limits, models, prompt
versions, central SQLite location, final KG/vector sources, gateway URL, and
quality thresholds. `generation_backend` is `gateway` in the checked-in
baseline; `template` exists only for deterministic offline tests.

The JSON read adapters expect these shapes:

```json
{"concepts": [{"id": "c1", "name": "Duration", "domain": "Fixed Income", "summary": "...", "source_version": "hash"}], "neighborhoods": {}}
```

```json
{"items": [{"id": "chunk-1", "concept_id": "c1", "text": "...", "version": "hash"}]}
```

## Project layout

```
src/study_system/core/          shared services, config, gateway adapter
src/study_system/repositories/   final KG/vector read contracts + JSON adapters
src/study_system/storage/       study-owned SQLite persistence
src/study_system/scheduling/    FSRS scheduler
src/study_system/types/         MVP domain records
tests/                          unit + integration tests
```

No `mcp/` package and no `automation/` package. The MCP adapter
(`StudyMCPTools`, `build_mcp_core`) and server live in the separate
`mcp_server` project's `study` tool group (`plans/09_MCP_ADAPTER_RELOCATION.md`).
The headless generation job and its shell launcher live in the separate
`study-automation` project (`plans/10_AUTOMATION_ADAPTER_RELOCATION_PLAN.md`).
Both import this package as a library; neither duplicates its logic.
