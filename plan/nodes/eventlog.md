---
id: eventlog
stage: 0
part: trunk
provides: [I2]
uses: []
builder: claude
reviewer: codex
line_budget: 80
existing: pull pieces (workshop/Original Code/AI Code/Learning System/src/study_system/storage/mvp_store.py — connection setup only)
status: detailed
---

# Store

**Job:** open the one SQLite file and apply each node's own table changes. Nothing else.

**Done when:**
1. Two different owners each migrate their own tables into one fresh file.
2. Running the migrations again changes nothing.
3. The file lives where `AIOS_DB` says, or by default `Database/sqlite/aios.sqlite`. Assumed.

**Build:**
- `core/store.py`, with `connect` and `migrate` as described in I2.
- A `migrations` table that records owner, step number and date.
- WAL mode and foreign keys switched on.

From the old `mvp_store.py`, take only the connection settings. Its tables, idempotency keys and override records stay behind.

**Delayed:**
- The events table and task queue (Stage 3).
- Litestream backup (Stage 3).
- Postgres (only if two machines ever write at once).
