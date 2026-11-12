# recurring.py — Technical Documentation

**Last updated:** 2026-05-03
**Lines of code:** 169
**Language:** Python

---

## What This File Does (Plain English)

This file scans all historical debit payments and identifies counterparties that are paid on a regular cadence — weekly, fortnightly, or monthly. It groups payments by counterparty (VPA preferred, name as fallback), checks whether gaps between consecutive payments are consistent with a known cadence, and requires amounts to be consistent within 10%. Results are upserted into the `recurring_payments` table. The reactor calls this once per ingestion batch and emits events for newly discovered clusters.

---

## How It Actually Works

### Entry Points

- `refresh_recurring(conn)` — called by the reactor after each ingestion batch. Upserts clusters to DB, returns full cluster list.
- `previously_known(conn)` — called by the reactor before `refresh_recurring()` to identify which clusters are new.
- `find_recurring(conn)` — pure detection logic; returns clusters without writing to DB. Used by `refresh_recurring()`.

### Data Flow

```
refresh_recurring(conn)
  → find_recurring(conn)
      → SELECT all debit payments with non-null amount, ordered by occurred_at
      → group by counterparty key:
          VPA (lowercased) if present, else name (lowercased, stripped)
      → for each group with >= 3 members:
          compute dates list
          _amounts_consistent(amounts)   # all within 10% of median
          compute gaps (days between consecutive payments)
          median_gap = statistics.median(gaps)
          _classify_cadence(median_gap)  # 7±4, 14±4, or 30±4 days → name
          verify >= 70% of individual gaps also fit the cadence
          if all checks pass: emit RecurringCluster
  → for each cluster: UPSERT into recurring_payments
  → return clusters
```

### State Management

- `recurring_payments` DB table stores the persistent state.
- `previously_known()` reads this table to return a set of `(counterparty, kind, cadence)` tuples before the upsert runs. The reactor uses this set to determine which clusters are genuinely new.

### Key Functions / Classes

| Name | What it actually does |
|---|---|
| `find_recurring(conn)` | Scans all debits, groups by counterparty, filters for cadence + amount consistency, returns list of RecurringCluster |
| `refresh_recurring(conn)` | Calls `find_recurring()`, upserts all results to DB, returns clusters |
| `previously_known(conn)` | Returns set of (counterparty, kind, cadence) already in recurring_payments table |
| `_classify_cadence(median_gap_days)` | Maps a median gap to 'weekly' / 'fortnightly' / 'monthly' or None; tolerance from config |
| `_amounts_consistent(amounts)` | Returns True if all amounts are within `RECURRING_AMOUNT_TOLERANCE` (10%) of the median |

### RecurringCluster Dataclass

```python
RecurringCluster:
    counterparty: str           # VPA or name, lowercased
    counterparty_kind: str      # 'vpa' | 'name'
    cadence: str                # 'weekly' | 'fortnightly' | 'monthly'
    typical_amount: float       # median of amounts in the cluster
    occurrences: int            # number of payments in the cluster
    first_seen: datetime
    last_seen: datetime
    next_expected: datetime     # last_seen + target_gap days
    payment_ids: list[int]
```

### Cadence Detection Logic

```
candidates: weekly=7d, fortnightly=14d, monthly=30d
tolerance: ± RECURRING_CADENCE_TOLERANCE (4 days)
weekly:       median gap in [3, 11]
fortnightly:  median gap in [10, 18]  (overlaps with weekly at boundary)
monthly:      median gap in [26, 34]

Secondary check: at least 70% of individual gaps must also fit the cadence.
First match in [weekly, fortnightly, monthly] wins.
```

### External Dependencies

- `sqlite3`, `json`, `statistics`, `collections`, `datetime` (stdlib)
- `brain.config` — reads `RECURRING_MIN_OCCURRENCES`, `RECURRING_CADENCE_TOLERANCE`, `RECURRING_AMOUNT_TOLERANCE`

### Error Handling

None in this module. All errors propagate to the reactor's `try/except` in `_process_recurring()`.

---

## Non-Technical Decisions Embedded in the Code

- VPA is always preferred over name for grouping. Two payments to the same person via different VPAs would form separate clusters. Two payments to the same person's name (no VPA, name spelled identically) would be one cluster.
- `next_expected` is computed as `last_seen + target_gap_days`. For a monthly payment, `target_gap` is always 30 — not calendar-month-aware. A payment on January 31 would have `next_expected = March 2` (30 days later), not February 28.
- The 70% threshold for individual gaps is hardcoded: `if consistent < len(gaps) * 0.7`. One missed payment in a series of 4 (3 gaps, 1 miss) = 2/3 = 67% — would fail the threshold. A series of 5 (4 gaps, 1 miss) = 3/4 = 75% — would pass.
- `statistics.median` is used for both typical amount and median gap. For an even number of values, Python's `statistics.median` interpolates between the two middle values, producing a non-integer gap in days.
- The weekly and fortnightly cadence windows overlap: weekly allows up to 11 days, fortnightly starts at 10. A 10-day gap matches both. The candidates list is ordered `[weekly, fortnightly, monthly]` and `_classify_cadence` returns the first match, so a 10-day median gap is classified as weekly, not fortnightly.

---

## Honest Gaps and Risks

- **Full table scan on every reactor invocation.** `find_recurring()` fetches all debit payments with non-null amount, regardless of date range. As the payment history grows, this query grows proportionally. There is no date-bounded lookback — a 2-year-old payment can contribute to or prevent a cluster from being detected.
- **Weekly/fortnightly overlap at 10–11 days.** A biweekly payment with gaps averaging 10 days would be misclassified as weekly.
- **`next_expected` uses 30 days for monthly, not actual calendar month.** A monthly subscription charged on the 1st of each month would drift by 1–2 days in `next_expected` predictions over time.
- **Amount consistency check uses all payments in the group, including historical ones.** If a subscription raised its price 12 months ago, the old amounts may drag the median far from the current charge and fail the consistency check, preventing detection.
- **No handling for payments that appear in multiple clusters.** If one counterparty has both weekly small charges and monthly larger charges (e.g., a service with different tiers), the amount consistency check (`_amounts_consistent`) would likely fail because the amounts span two distinct ranges.
- **The reactor emits one `recurring_detected` event per new cluster, deduped by `(kind, counterparty, cadence)`.** If a cluster is detected, its entry removed from the table (which never happens — only upserts occur), and the cluster redetected, the event would not fire again because the dedup key is in `agent_events` — not in `recurring_payments`.

---

## Developer Notes

- The 70% gap consistency threshold is hardcoded in `find_recurring()` as `len(gaps) * 0.7`. If you want to make it configurable, add it to `config.py` (there is already a `RECURRING_CADENCE_TOLERANCE` constant established there).
- `refresh_recurring()` always upserts regardless of whether a cluster changed. The upsert updates `typical_amount`, `occurrences`, `last_seen`, `next_expected`, and `payment_ids` even for existing clusters. `first_seen` is NOT updated on conflict — this is correct since the UPSERT only sets `excluded.*` for the listed columns.
- `previously_known()` must be called before `refresh_recurring()` if the reactor wants to know which clusters are new. Calling it after would return the updated set, making everything appear "known".
- The `payment_ids` field is stored as a JSON array string in the DB. When reading it back, you need `json.loads(row["payment_ids"])`.
