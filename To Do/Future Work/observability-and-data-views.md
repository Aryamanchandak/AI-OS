# Future work — observability and data views

Parked out of the GLC/ingestion Gateway migration (`To Do/Gateway to do/GLC
and ingestion gateway migration/`) so it doesn't blur that migration's exit
gates. Not scheduled; catalogued for later.

## The idea

Raised while reviewing `00-program-roadmap.md`: once LLM calls, ingestion
runs, and eventually channel/voice activity all pass through Gateway, there
should be a way to *see* what's happening without going table-by-table
through SQLite files.

Two related but separable pieces:

1. **A view over all SQL tables.** A prefab UI (or an existing tool) that
   lets Aryaman browse the tables under `Database/sqlite/*` (ledger, audit,
   ingestion, cache, etc.) without hand-writing queries each time.
2. **OpenTelemetry.** Standard tracing/metrics across Gateway's domains
   (LLM calls, ingestion runs, eventually channels) instead of ad hoc
   per-domain logging.

## Why it's parked, not dropped

The migration's whole point is a mechanical, low-risk move — characterize,
move, verify, repeat. Observability tooling is a real product feature, not a
migration step, and folding it into Plan 01 or Plan 02 would give those
plans an open-ended, unreviewable exit gate. It's real, it's wanted, it
should get its own plan once the migration exit gates are met.

## What it depends on

- The final table/schema layout that Plan 03 (database decision) and Plan 06
  (ingestion) settle on — no point designing a table browser before the
  tables stop moving.
- Whether the LLM-call-is-always-logged invariant (Plan 04, pipeline stage 9)
  is still enforced the same way once/if any domain moves behind an
  MCP-style call boundary — the audit stage is what any view like this would
  read from.
