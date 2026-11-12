# reactor.py — Technical Documentation

**Last updated:** 2026-05-03
**Lines of code:** 379
**Language:** Python

---

## What This File Does (Plain English)

This file is the orchestration hub of the brain layer. It receives a list of newly inserted payment IDs, runs each one through classification, anomaly detection, and goal checking in sequence, then runs a batch-level recurring payment pass at the end. All results are written to `agent_events` idempotently — if you run the reactor twice on the same payments, it produces zero duplicate events. There is also a backfill entry point that processes all payments that have never been through the brain.

---

## How It Actually Works

### Entry Points

- `on_new_payments(payment_ids, db_path, now)` — primary entry point; called by `agent.py` and `cli.py react --payment-id N`.
- `react_to_all_unprocessed(db_path, now)` — backfill entry point; called by `cli.py react` (no --payment-id).

### Data Flow

```
on_new_payments(payment_ids, db_path, now)
  → open connect(db_path)   # single connection for the whole batch
  → for each payment_id in payment_ids:
      fetch payment row from payments table
      _process_classifier(row, conn, report)
          → skip if category_source == 'user'
          → classifier.classify(row, conn)
          → if category found: UPDATE payments SET category, category_source='agent'
          → _emit_event('categorized', ...)
          → re-fetch row (so anomaly zscore sees the category just written)
      _process_anomalies(row, conn, report)
          → anomaly.run_all(row, conn)   # four detectors
          → _emit_event('anomaly', ...) for each finding
      _process_goals(row, conn, report, now)
          → goals.list_goals(conn, 'active')
          → for each goal:
              check payment against goal logic
              _emit_event('goal_warning' or 'goal_violation', ...)
      report.payments_processed += 1
  → _process_recurring(conn, report)   # once per batch
      recurring.previously_known(conn)
      recurring.refresh_recurring(conn)
      _emit_event('recurring_detected', ...) for new clusters
  → log report.summary()
  → return ReactorReport

react_to_all_unprocessed(db_path, now)
  → open connect(db_path)
  → SELECT payments with no 'categorized' event and no user-set category
  → close connection
  → call on_new_payments(ids, ...)
```

### State Management

No in-module state. The reactor is a stateless orchestrator. All persistence goes to `agent_events` and the `payments.category` column. The `_MIGRATED` set in `db.py` ensures migrations have run before the reactor touches the DB.

### Key Functions / Classes

| Name | What it actually does |
|---|---|
| `_emit_event(conn, ...)` | INSERT OR IGNORE into `agent_events` using `dedup_key`; returns True if a new row was created |
| `_process_classifier(payment, conn, report)` | Classifies payment and applies category; skips if user-set; emits categorized event |
| `_process_anomalies(payment, conn, report)` | Runs all anomaly detectors; emits one event per finding |
| `_process_goals(payment, conn, report, now)` | Checks all active goals against this payment; emits warning/violation events |
| `_process_recurring(conn, report)` | Batch-level: detects new recurring clusters after all payments are processed |
| `on_new_payments(payment_ids, ...)` | Main pipeline: runs all three per-payment passes then the recurring pass |
| `react_to_all_unprocessed(db_path, now)` | Finds unprocessed payments and calls on_new_payments |

### ReactorReport Dataclass

```python
ReactorReport:
    payments_processed: int
    categorized: int
    anomalies_emitted: int
    goal_events_emitted: int
    recurring_detected: int
    errors: list[str]
```

`summary()` returns a single-line string suitable for logging.

### Dedup Key Patterns

| Event kind | Dedup key format |
|---|---|
| categorized | `categorized:payment=<id>` |
| anomaly (most) | `anomaly:<detector>:payment=<id>` |
| anomaly (velocity) | `anomaly:velocity:first=<first_id>` |
| goal_violation (avoid_merchant) | `goal_violation:goal=<gid>:payment=<pid>` |
| goal_warning (budget/freq) | `goal_warning:goal=<gid>:period=<label>` |
| goal_violation (budget/freq) | `goal_violation:goal=<gid>:period=<label>` |
| recurring_detected | `recurring_detected:<kind>:<counterparty>:<cadence>` |
| weekly_story | `weekly_story:<label>` |

### External Dependencies

- `brain.anomaly`, `brain.classifier`, `brain.config`, `brain.goals`, `brain.recurring` — all imported at module level
- `brain.db.connect` — connection factory
- `logging` (stdlib) — logs to `brain.reactor` logger
- No OpenAI. No subprocess calls.

### Error Handling

- Per-payment errors: wrapped in `try/except Exception`. Error message appended to `report.errors`, logged via `log.exception()`. Processing continues with the next payment.
- Recurring pass errors: same `try/except` pattern; appended to `report.errors`.
- `_emit_event()`: `INSERT OR IGNORE` means duplicate dedup keys silently do nothing — no error, returns `False`.
- `react_to_all_unprocessed()` uses a separate `connect()` block to read IDs, then closes the connection before calling `on_new_payments()` which opens its own connection. This avoids holding a write lock during the ID fetch.

---

## Non-Technical Decisions Embedded in the Code

- After classification, the reactor re-fetches the payment row before running anomaly detection. This is because `_process_classifier` may have written a `category` to the DB, and the anomaly `detect_amount_zscore` detector needs that category to look up historical baselines. Without the re-fetch, zscore would always see `category=None` and skip the check.
- The recurring pass runs once per batch invocation, not once per payment. This is deliberate: recurring cluster detection looks at all history, so running it once after all new payments are ingested is sufficient and avoids recomputing the full cluster set for every payment in the batch.
- `_process_goals` uses `goals.evaluate(goal, conn, now=lambda: now, as_of_payment_id=payment["id"])` for budget and frequency caps. The `lambda: now` wraps the frozen `now_dt` datetime. If `now_dt` is not passed in (defaults to `datetime.now()`), the `now` captured in the lambda is the exact moment `on_new_payments` was called — consistent for the entire batch.
- `_process_goals` directly accesses `goals._matches_pattern()` — a private function in the goals module — for the `avoid_merchant` check rather than calling `goals.evaluate()`. This is a performance shortcut (avoids fetching all in-scope payments for a simple pattern match) but creates hidden coupling.
- The reactor uses a single `connect()` context for the entire batch. All individual payment operations commit as part of one transaction at the end of the `with connect()` block.

---

## Honest Gaps and Risks

- **Single transaction for the batch.** All category writes, event inserts, and goal updates from an entire batch commit atomically. If the process crashes mid-batch, no partial results are committed — the reactor will simply re-process those payments on the next run. This is correct behaviour but means a large batch that runs for minutes holds a SQLite write lock for its entire duration.
- **`react_to_all_unprocessed()` identifies payments by absence of a `categorized` event.** A payment that has been intentionally left uncategorized (user chose not to set a category) will be re-processed on every run of `react_to_all_unprocessed()`. The `INSERT OR IGNORE` dedup prevents duplicate events, but the classifier and anomaly detectors run again, consuming time and potentially re-writing the same auto-detected category.
- **No notification is triggered by the reactor.** The reactor creates `agent_events` but does not call `notifier.notify_severe()`. The notifier must be called separately (by `cli.py notify` or a scheduled job). There is no automated notification pipeline.
- **`_process_goals()` calls `goals.list_goals()` on every payment.** For a batch of 100 payments with 10 active goals, `list_goals()` is called 100 times — each time fetching all active goals from the DB.
- **Goal evaluation for budget/frequency caps calls `goals.evaluate()` which calls `_payments_in_scope()` which is a full table-scan filtered query.** For each goal, for each payment in the batch, this query grows larger as more payments are processed. This is O(payments × goals × payments_in_period) in the worst case.

---

## Developer Notes

- The ordering within `_process_goals()` matters: `avoid_merchant` uses direct pattern matching (fast), while `budget_cap` and `frequency_cap` call `goals.evaluate()` which fetches all in-scope payments. If you add a new goal kind, follow the existing pattern.
- The `now` parameter in `on_new_payments()` is designed for testability — in tests, pass a fixed `datetime` to make period calculations deterministic.
- The reactor is the only writer of `category` and `category_source` on the `payments` table (aside from `classifier.record_user_categorization()` which the dashboard calls). If the dashboard writes a category, it sets `category_source='user'` which the reactor checks to avoid overwriting.
- Logging is at `INFO` level for the summary. Individual payment errors are logged via `log.exception()` which includes a traceback. To see these, configure the `brain.reactor` logger to at least `ERROR` level.
