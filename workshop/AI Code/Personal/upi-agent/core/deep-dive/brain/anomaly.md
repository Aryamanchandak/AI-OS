# anomaly.py — Technical Documentation

**Last updated:** 2026-05-03
**Lines of code:** 289
**Language:** Python

---

## What This File Does (Plain English)

This file contains four independent anomaly detectors that each inspect a single payment and return either a finding or nothing. The detectors look for: first payments to a new counterparty above a threshold, amounts that are statistically unusual for their category, payments at unusual hours, and bursts of rapid successive debits. The reactor calls all four on each new payment and records any findings in `agent_events`.

---

## How It Actually Works

### Entry Points

- `run_all(payment, conn)` — called by the reactor for each new payment. Returns `list[AnomalyFinding]`.
- `dedup_key_for(payment_id, finding)` — constructs the `agent_events.dedup_key` for a finding.

### Data Flow

```
run_all(payment, conn)
  → for each detector in ALL_DETECTORS:
      try:
          finding = detector(payment, conn)   # returns AnomalyFinding or None
          if finding: append to results
      except: swallow silently
  → return list of findings
```

Each detector independently queries the DB for historical context, applies a threshold check, and constructs an `AnomalyFinding` if it fires.

### Severity Scale

| Level | Meaning | Used by |
|---|---|---|
| 0 | Info | (not used by any detector currently) |
| 1 | Notice | `detect_amount_zscore` (low z), `detect_odd_hour`, `detect_velocity` is 3 |
| 2 | Warning | `detect_new_large_counterparty`, `detect_amount_zscore` (high z) |
| 3 | Critical | `detect_velocity` |

The notifier surfaces severity >= 2 to macOS Notification Center.

### Key Functions / Classes

| Name | What it actually does |
|---|---|
| `detect_new_large_counterparty(payment, conn)` | Fires severity 2 if: direction=debit, amount > 3,000, VPA present, no prior payments to that VPA |
| `detect_amount_zscore(payment, conn)` | Fires severity 1 or 2 if: direction=debit, payment is 2.5+ σ above the category mean over the last 60 days (needs 10+ history points) |
| `detect_odd_hour(payment, conn)` | Fires severity 1 if: direction=debit, amount >= 500, hour falls outside the 5th–95th percentile of prior debit hours (needs 30+ history points) |
| `detect_velocity(payment, conn)` | Fires severity 3 if: 5+ debits within any 10-minute window ending at this payment |
| `run_all(payment, conn)` | Runs all four detectors, swallows individual exceptions, returns all findings |
| `dedup_key_for(payment_id, finding)` | Returns `anomaly:<detector>:payment=<id>` for most detectors; for velocity, uses the first payment ID in the cluster |
| `_percentile(values, pct)` | Linear-interpolated percentile, hand-rolled (no numpy dependency) |
| `_money(x)` | Formats a float as Indian-style rupee string (e.g., `₹1,23,456`) |

### AnomalyFinding Dataclass

```python
AnomalyFinding:
    detector: str       # 'new_counterparty' | 'zscore' | 'odd_hour' | 'velocity'
    severity: int       # 0..3
    title: str          # short one-liner shown in notifications
    explanation: str    # full sentence(s) for the dashboard
    payload: dict       # detector-specific numeric detail
```

### External Dependencies

- `sqlite3`, `statistics` (stdlib)
- `brain.config` — reads all threshold constants
- No network calls.

### Error Handling

- `run_all()` wraps each detector in `try/except`. A crashing detector is silently skipped. No error is logged or surfaced to the user.
- `_percentile()` raises `ValueError` on an empty list — but all callers check `len(rows) >= MIN_HISTORY` before calling it, so this should not occur in practice.
- `sigma == 0` check in `detect_amount_zscore()`: if all historical amounts are identical, stdev is 0 and the function returns `None` (can't compute a meaningful z-score).

---

## Non-Technical Decisions Embedded in the Code

- All four detectors only fire on `direction == 'debit'`. Credits are never flagged, regardless of amount. A large unexpected credit (possible fraud on the sender's side) is invisible to this system.
- `detect_velocity` queries payments where `occurred_at` is between `window_start` and `payment["occurred_at"]` inclusive — it includes the current payment in the count. If exactly 5 debits occur in 10 minutes (including the current one), the detector fires. The count threshold is `>= VELOCITY_COUNT (5)`.
- `detect_velocity` dedup key is anchored to the `first_payment_id` in the window, not the triggering payment. This means if payments 10, 11, 12, 13, 14 all arrive in a burst, the event is deduped under `anomaly:velocity:first=10` regardless of which payment triggers it. Re-running the reactor on payments 11–14 individually would all produce the same dedup key and only one event would be recorded.
- `detect_amount_zscore` uses `statistics.mean` and `statistics.stdev` (population correction: stdev requires `n >= 2`). For exactly 10 historical payments (the minimum), stdev uses N-1 = 9 degrees of freedom, which is fine.
- The `_money()` function is duplicated in `anomaly.py`, `goals.py`, and `narrator.py` — three separate implementations of the same Indian rupee formatter.

---

## Honest Gaps and Risks

- **Silent detector failures:** `run_all()` swallows exceptions without logging. If `detect_amount_zscore` has a bug, no anomaly fires and no error is visible. The developer has no way to detect this from outside.
- **`detect_new_large_counterparty` requires a VPA.** If the payment has only a `counterparty_name` (no VPA), the detector returns `None` immediately, even for very large amounts to unknown merchants.
- **`detect_velocity` includes the triggering payment in its count.** The window query is `occurred_at >= window_start AND occurred_at <= payment["occurred_at"]`. If the triggering payment's `occurred_at` is equal to another payment's, both are counted. This is correct behaviour but easy to misread.
- **`detect_odd_hour` uses the raw hour integer for percentile calculation.** Hour values are discrete (0–23). For a user who never pays between midnight and 5 AM, the 5th percentile of hours might be 6 (e.g., first outlier hour). A payment at 5 AM would be flagged; one at 6 AM would not — even though both are unusual. The percentile approach on discrete data is more precise than a simple cutoff but still has edge cases.
- **No deduplication across detector reruns for `velocity`.** If the reactor is run twice on the same batch (e.g., a bug or manual rerun), the velocity dedup key is based on `first_payment_id` which is stable — so velocity events won't duplicate. But the other three detectors use `payment_id`, which is also stable. All four are correctly idempotent via `INSERT OR IGNORE`.

---

## Developer Notes

- To add a new detector: implement `my_detector(payment: sqlite3.Row, conn: sqlite3.Connection) -> AnomalyFinding | None` and append it to `ALL_DETECTORS`. Return `None` if the detector does not fire.
- Update `dedup_key_for()` with a case for your detector's name, otherwise the default branch would not match and a `KeyError` would occur (actually there is no default — the function has only two branches and the `if finding.detector == "velocity"` check; any other detector falls to the second return which uses `payment_id`. This is safe but worth noting).
- The `_money()` helper is private to this file. If you need it in a new module, extract it to a shared utility module rather than copy it again.
- All thresholds are in `config.py`. Do not add numeric literals to detector bodies.
