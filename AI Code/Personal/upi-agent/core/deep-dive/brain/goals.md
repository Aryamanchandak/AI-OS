# goals.py — Technical Documentation

**Last updated:** 2026-05-03
**Lines of code:** 333
**Language:** Python

---

## What This File Does (Plain English)

This file manages user-declared spending promises. A goal is a rule the user sets — "don't spend at Swiggy this week", "keep Food under ₹3,000 this month", "order Uber at most twice a week". The file provides functions to create, query, pause, end, and evaluate these goals, plus a cache refresh function that pre-computes their current status. The reactor calls `evaluate()` on each active goal for every new payment; the narrator and dashboard read the cached results.

---

## How It Actually Works

### Entry Points

- `create_goal(conn, ...)` — called by `cli.py` when the user adds a goal.
- `evaluate(goal, conn, now, as_of_payment_id)` — called by the reactor per payment per active goal.
- `refresh_status_cache(conn, now)` — called by `cli.py goal check` and the narrator.
- `list_goals(conn, status)` — called by reactor, narrator, and CLI.
- `set_status(conn, goal_id, status)` — called by `cli.py goal pause/end`.

### Data Flow

```
Goal creation (CLI):
  create_goal(conn, description, kind, spec, scope, ...)
    → validate kind and scope
    → INSERT INTO goals
    → return new goal id

Goal evaluation (reactor):
  evaluate(goal, conn, now, as_of_payment_id)
    → period_bounds(goal.scope, now)    # compute start/end datetime for current period
    → _payments_in_scope(conn, scope, now, as_of_payment_id)
        → SELECT debit payments in [start, end) with id <= as_of_payment_id
    → branch on goal.kind:
        avoid_merchant → check if any payment matches spec.patterns
        budget_cap     → sum amounts for spec.category, compute progress vs cap
        frequency_cap  → count matching payments, compare to max_per_period
    → return GoalStatus(state, progress, message, offending_payment_ids)

Cache refresh:
  refresh_status_cache(conn)
    → for each active goal: evaluate() → UPSERT into goal_status_cache
```

### State Management

Goal state lives in two DB tables:
- `goals` — the goal definitions (immutable after creation except for `status` field)
- `goal_status_cache` — the last computed evaluation result per goal

The `as_of_payment_id` parameter in `evaluate()` lets the reactor advance through a batch of payments one at a time, so a budget that crosses both the 80% warn threshold and the 100% violation threshold within a single batch fires both events (not just the violation).

### Key Functions / Classes

| Name | What it actually does |
|---|---|
| `period_bounds(scope, now)` | Returns `(start_datetime, end_exclusive_datetime)` for the ISO week or calendar month containing `now`. Custom scope returns epoch–far-future. |
| `period_label(scope, now)` | Returns stable string label used in dedup keys (`2026-W17`, `2026-05`, `custom`) |
| `create_goal(conn, ...)` | Inserts a new goal row; validates kind and scope; returns new ID |
| `list_goals(conn, status)` | Returns all goals, optionally filtered by status, newest first |
| `get_goal(conn, goal_id)` | Returns one goal row or None |
| `set_status(conn, goal_id, status)` | Updates goal status to active/paused/ended |
| `evaluate(goal, conn, now, as_of_payment_id)` | Computes current GoalStatus for one goal |
| `refresh_status_cache(conn, now)` | Evaluates all active goals and upserts results to `goal_status_cache` |
| `_matches_pattern(payment, pattern)` | Case-insensitive substring match against name OR vpa |
| `_payments_in_scope(conn, scope, now, as_of_payment_id)` | Returns debit payments in the current period, optionally capped at a payment ID |

### GoalStatus Dataclass

```python
GoalStatus:
    state: str                    # 'ok' | 'warning' | 'violated'
    progress: float               # 0..1+ for budgets; 0 or 1 for boolean kinds
    message: str                  # human-readable current state
    offending_payment_ids: list[int]  # payments that caused the state
```

### Goal Kinds and Their spec_json Structure

| Kind | spec_json keys | Meaning |
|---|---|---|
| `avoid_merchant` | `patterns: list[str]` | Violated if any debit in period matches any pattern |
| `budget_cap` | `category: str`, `amount: float`, `warn_at_pct: int` | Warning at warn_at_pct%, violated above 100% |
| `frequency_cap` | `patterns: list[str]`, `max_per_period: int` | Warning at exactly max, violated above max |

### External Dependencies

- `sqlite3`, `json`, `datetime` (stdlib)
- `brain.config` — reads `DEFAULT_BUDGET_WARN_PCT`

### Error Handling

- `create_goal()` raises `ValueError` on unknown kind or scope.
- `set_status()` raises `ValueError` on invalid status string.
- `evaluate()` raises `ValueError` on unknown goal kind — this propagates to the reactor, which catches it as a payment-level error.
- `refresh_status_cache()` has a defensive check: forces `conn.row_factory = sqlite3.Row` if it's not already set, because `evaluate()` accesses columns by name.

---

## Non-Technical Decisions Embedded in the Code

- Week scope uses ISO weeks (Monday–Sunday). A payment on Sunday 2026-05-03 and a payment on Monday 2026-05-04 are in different weeks.
- Month scope uses calendar months (1st to last day). There is no support for "rolling 30 days" — it's always the calendar month.
- Goals are never deleted from the DB — they are only status-updated to `'ended'`. The `ON DELETE CASCADE` on `goal_status_cache` therefore never fires.
- `_payments_in_scope()` only returns debits — credits never count toward any goal type.
- `frequency_cap` hits `state="warning"` when `len(matching) == max_n` (exactly at limit) and `state="violated"` when `len(matching) > max_n`. This means the warning fires at the boundary itself, not before it.
- The `NowFn = Callable[[], datetime]` type alias and `_default_now()` function exist to allow test injection of a clock. Production code passes `None` and gets `datetime.now()`.

---

## Honest Gaps and Risks

- **`evaluate()` re-reads all debit payments in the period on every call.** For a period with many payments, this is a full table scan filtered by date. With `as_of_payment_id` the query grows to include an AND clause. No indexing guidance is given for the `(direction, occurred_at)` combination — the `payments` table's indexes are defined by the base agent, not this file.
- **`avoid_merchant` pattern matching is a simple substring check.** The pattern `"air"` would match payments to "Airtel", "Air India", "AirBnB", and anyone with "air" in their VPA. No word-boundary anchoring.
- **`frequency_cap` warning fires at exactly the limit, not before it.** A user who sets max=3 and makes their 3rd qualifying payment gets a warning event at that payment — they cannot reduce their frequency to stay under the limit retroactively. The semantics are "you've hit your limit" not "you're approaching it".
- **`refresh_status_cache()` calls `evaluate()` without an `as_of_payment_id`**, so it always evaluates the full current period. This means the cache reflects the full-period state, not the incremental state the reactor saw during batch processing. This is correct for the narrator and dashboard, but the cache lags the reactor's incremental view.
- **`_payments_in_scope()` is called once per goal per payment in the reactor.** If there are 10 active goals and 100 new payments, this is 1,000 DB queries, each returning the same expanding set of payments. There is no memoisation.

---

## Developer Notes

- `_matches_pattern()` is accessed from `reactor.py` via `goals._matches_pattern(...)` — this is calling a private (underscore-prefixed) function from another module. This is a coupling point: renaming `_matches_pattern` would break `reactor.py` silently until runtime.
- The `NowFn` injectable clock (`now: NowFn | None = None`) is used consistently in `evaluate()` and `refresh_status_cache()`. When writing tests, pass `now=lambda: fixed_datetime` to control the period.
- `create_goal()` does not validate that `spec` contains the required keys for the given `kind`. Passing `{"amount": 1000}` for a `budget_cap` without `"category"` will create the goal successfully but crash with a `KeyError` the first time `evaluate()` runs it.
- `set_status()` does not check that `goal_id` exists. If given an ID that doesn't exist, it executes `UPDATE ... WHERE id = ?` which silently affects 0 rows. No error is raised.
