# Study Automation, MCP, and Configuration Plan

**Owner:** Study-system  
**Priority:** First implementation workstream

## 1. Objective

Build one study-engine core that supports two initial adapters:

1. unattended automation launched by a fail-fast shell script; and
2. MCP tools called by the unified chat interface.

There will be no duplicate business logic between the two adapters.

## 2. Core capabilities

The core should expose application-level methods approximately equivalent to:

- `generate_cards(request)`;
- `run_daily_generation()`;
- `get_due_cards(limit)`;
- `submit_review(card_id, rating, result_id)`;
- `start_feynman(concept_id | auto_select)`;
- `evaluate_feynman(attempt_id, explanation)`;
- `start_challenger(concept_id | auto_select)`;
- `grade_challenger(attempt_id, answer)`;
- `get_progress_summary()`;
- `set_temporary_override(request)`; and
- `cancel_temporary_override(override_id)`.

Names can change. The important rule is that adapters call these capabilities rather than implementing their own retrieval, generation, scheduling, or persistence.

## 3. Automation MVP

### Trigger

A user, cron job, launch agent, or future always-on service invokes one `.sh` launcher.

### Work performed

- acquire a single-run lock;
- load baseline config and active overrides;
- query candidate concepts from the final KG;
- select a deterministic unseen/underrepresented batch;
- retrieve current KG neighborhood and vector chunks;
- generate the configured card sets;
- run quality checks;
- persist accepted cards and provenance in central study SQLite;
- write one automation-run audit record; and
- release the lock and return status.

### Not performed in the MVP

- email or iCloud delivery;
- calendar-aware workload sizing;
- advanced mastery optimization;
- automatic baseline configuration edits;
- UI rendering; or
- personalized FSRS fitting.

## 4. Launcher requirements

The shell launcher must:

- use `set -euo pipefail` or equivalent fail-fast behavior;
- derive paths from the script location, not the caller's current directory;
- activate the expected environment;
- validate database, KG, vector, and gateway availability;
- prevent overlapping runs;
- write concise timestamped logs outside the code repository or to the approved runtime log location;
- pass through the process exit code; and
- never continue after a failed dependency or generation step.

Cron schedules the launcher; it does not contain study logic.

## 5. MCP surface

### Initial tools

| Tool | Effect | Write permission |
|---|---|---|
| `study_generate_cards` | Generate cards using validated request bounds | Cards and run records |
| `study_get_due_cards` | Return FSRS-due cards for chat presentation | None |
| `study_submit_review` | Apply one validated rating idempotently | Reviews and FSRS state |
| `study_start_feynman` | Return a grounded prompt and stateless concept handle | None |
| `study_evaluate_feynman` | Grade supplied chat history/explanation and store final evidence | Completed outcome audit only |
| `study_start_challenger` | Return a grounded prompt and stateless concept handle | None |
| `study_grade_challenger` | Grade supplied chat history/answer and store final evidence | Completed outcome audit only |
| `study_progress` | Return basic counts and due state | None |
| `study_set_temporary_override` | Add a bounded, expiring override | Overrides only |
| `study_cancel_temporary_override` | Revoke an override | Overrides only |

The unified chat interface decides presentation. A future flashcard pane can call the same tools or a stable HTTP adapter over the same core.

## 6. Baseline configuration

Baseline configuration controls system invariants and default policy. Examples:

- central study database path;
- final KG/vector endpoints;
- LLM gateway endpoint;
- card-generation model/prompt version;
- default daily card sets;
- cards per set;
- quality thresholds;
- maximum allowed temporary override values; and
- FSRS default weights.

Baseline config is loaded through a typed model and is not writable by MCP tools or normal automation.

## 7. Temporary overrides

Temporary overrides support instructions such as “for the next fourteen days, generate seven sets rather than five.”

Required fields:

- ID;
- setting name from an allowlist;
- validated value;
- start and expiry times;
- creator (`user`, `agent`, or system identity);
- original user instruction or concise reason;
- created timestamp; and
- revoked timestamp where applicable.

Rules:

- expiry is mandatory for agent-created policy changes;
- the setting must be explicitly allowlisted;
- values are bounded;
- baseline config remains unchanged;
- effective config is computed as baseline plus active overrides;
- every automated run records the effective values it used; and
- the user can inspect and cancel active overrides.

## 8. Due review answer

FSRS determines due cards through `next_due_at` and card state. `study_get_due_cards` queries those records and returns a bounded set to the chat interface. The user can explicitly ask to review; a later autonomous director may proactively mix due review into a session.

For the MVP, do not add exam weighting, time fitting, mastery scoring, or stale-strong verification on top of due-card selection.

## 9. Feynman and challenger MVP

These are separate shippable capabilities, even though they share infrastructure.

Each requires:

- current KG/vector retrieval;
- a versioned existing prompt;
- a callable service with structured input/output;
- caller-owned conversation history plus persisted final-outcome provenance;
- model-output validation;
- an MCP adapter; and
- focused tests.

They do not require a study-system frontend. The unified chat UI supplies the conversation,
and no mid-interaction session row is stored.

## 10. Safety and idempotency

- Each write tool accepts or creates an idempotency key.
- Review submission rejects unknown cards and invalid ratings.
- Card generation records source concept IDs and checks existing coverage/duplicates.
- Only study-system writes FSRS and learning records.
- KG/vector adapters are read only.
- Automation uses a lock to prevent concurrent duplicate batches.
- Override tools cannot alter paths, credentials, prompts, models outside an allowlist, or code.

## 11. Delivery slices

### Slice A — Core boundary and storage

Wrap generator, quality, scheduler, and SQLite behavior in services; centralize persistence; add characterization tests.

### Slice B — Automation

Add deterministic candidate selection, run audit, lock, and shell launcher.

### Slice C — Review MCP

Add due-card and submit-rating tools over preserved FSRS behavior.

### Slice D — Generation MCP and overrides

Add manual generation and bounded expiring policy overrides.

### Slice E — Feynman

Wire the existing prompt into a tested service and MCP flow.

### Slice F — Challenger

Wire the existing prompt into a tested service and MCP flow.

## 12. Done criteria

- Automation can run twice without uncontrolled duplicate output.
- A temporary seven-sets-for-fourteen-days override takes effect and expires automatically.
- The agent cannot mutate baseline configuration.
- Chat can fetch a due card and submit a rating that changes FSRS correctly.
- Feynman and challenger work through structured MCP calls.
- No runtime data is written inside the repository.
- Legacy terminal paths remain until the replacement has passed acceptance.
