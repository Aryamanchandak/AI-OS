# classifier.py — Technical Documentation

**Last updated:** 2026-05-03
**Lines of code:** 323
**Language:** Python

---

## What This File Does (Plain English)

This file auto-categorises UPI payments into one of the 12 canonical categories. It runs four independent classifiers against each payment, aggregates their weighted votes by category, and picks the winner if the total weight clears a threshold. If nothing clears the threshold, the payment is left uncategorised. When a user manually corrects a category on the dashboard, this file also records that correction as a learned rule that future classifications will use.

---

## How It Actually Works

### Entry Points

- `classify(payment, conn)` — main inference path, called by the reactor for each new payment.
- `record_user_categorization(payment_id, category, conn)` — called by the dashboard when a user sets a category manually.

### Data Flow

```
classify(payment, conn)
  → run ALL_CLASSIFIERS in order:
      history_signals(payment, conn)   # DB lookup: category_rules by VPA + name tokens
      calendar_signals(payment, conn)  # parse calendar_events JSON column, match keywords
      merchant_signals(payment, conn)  # substring match against MERCHANT_PATTERNS
      heuristic_signals(payment, conn) # amount + time-of-day rules
  → collect all Signal objects (each has classifier, category, weight, reason)
  → sum weights per category across all signals
  → find category with max total weight
  → if max weight < CONFIDENCE_THRESHOLD (0.6): return category=None
  → else: return ClassificationResult(category=winner, confidence=winner_weight, signals=all)
```

### State Management

No state in this module. The learned rules live in the `category_rules` DB table. The `_MIGRATED` set in `db.py` ensures the table exists before this module queries it.

### Key Functions / Classes

| Name | What it actually does |
|---|---|
| `history_signals(payment, conn)` | Queries `category_rules` table: one signal for VPA match (weight 0.9 if hits >= 3, else 0.25), one signal per name token match (weight 0.5 each) |
| `calendar_signals(payment, conn)` | Parses `calendar_events` JSON on the payment row; matches event titles against `CALENDAR_KEYWORDS` regex patterns; returns at most one signal (first match wins) |
| `merchant_signals(payment, conn)` | Lowercased substring match of counterparty name + VPA against `MERCHANT_PATTERNS`; returns at most one signal (first match wins) |
| `heuristic_signals(payment, conn)` | Two rules: (1) morning hour + small amount → Food; (2) early-month + round large amount → Rent or Bills |
| `classify(payment, conn)` | Runs all four, sums weights by category, returns winner or None |
| `record_user_categorization(payment_id, category, conn)` | Upserts `category_rules` rows for VPA + name tokens; increments hits; marks `payments.category_source = 'user'` |
| `name_tokens(name)` | Lowercases name, extracts 3+ character alphanumeric tokens, strips stop words |

### Data Structures

```python
Signal:
    classifier: str    # which classifier produced this
    category: str      # which category it voted for
    weight: float      # how strongly
    reason: str        # human-readable explanation

ClassificationResult:
    category: str | None   # winning category, or None if below threshold
    confidence: float      # total weight of winning category
    signals: list[Signal]  # ALL signals including losers (for audit)
```

### External Dependencies

- `sqlite3` (stdlib)
- `brain.config` — reads all weight constants, `MERCHANT_PATTERNS`, `CALENDAR_KEYWORDS`, `NAME_STOP_TOKENS`, `CONFIDENCE_THRESHOLD`, `CATEGORIES`
- No OpenAI. No network calls.

### Error Handling

- Each classifier call in `classify()` is wrapped in a `try/except`. A crashing classifier is replaced by a zero-weight `Signal(category="Other", weight=0.0, reason=f"classifier error: {e}")`. Classification continues with remaining classifiers.
- `record_user_categorization()` silently returns without doing anything if the `category` argument is not in `config.CATEGORIES`. No error is raised.
- `_calendar_titles()` catches `json.JSONDecodeError` and `TypeError` on the `calendar_events` column — returns empty list.

---

## Non-Technical Decisions Embedded in the Code

- The VPA history rule has two tiers: weight 0.9 if the VPA has 3+ hits to the same category, weight 0.25 (`HISTORY_TOKEN_WEIGHT * 0.5`) if it has fewer. This means even a single prior observation produces a weak signal, not silence.
- Calendar signals return at most one signal — the first matching event title/keyword pair. Multiple calendar events on the same day don't stack.
- Merchant patterns use first-match-wins. The ordering in `config.MERCHANT_PATTERNS` is therefore semantically significant.
- `heuristic_signals()` defines "morning" as 07:00–11:00 and "small" as ₹50–₹400. These are hardcoded in the function body despite the design intent in `config.py` to centralise all thresholds.
- The ensemble sums weights across all classifiers. If history gives 0.9 for Food and the merchant pattern gives 0.7 for Food, the total is 1.6 — well above the 0.6 threshold. There is no cap on total weight.
- `record_user_categorization()` also writes name-token rules, not just VPA rules. This means a user categorising a payment from "PRIYA SHARMA" as "Transfer" will teach the system that "priya" and "sharma" suggest Transfer for all future counterparties — potentially a bad generalisation.

---

## Honest Gaps and Risks

- **Heuristic thresholds are hardcoded:** `7 <= hour < 11`, `50 <= amount <= 400`, `amount >= 5000`, `amount % 100 == 0`, `amount >= 10000` — none of these are in `config.py`. The design convention is violated here.
- **Name-token learning pollutes rules with personal names:** If a user's landlord is "Amit Kumar", categorising rent payments from him teaches that "amit" and "kumar" → Rent, which will incorrectly influence payments from other "Amits".
- **calendar_signals() returns on the first matching title** across all event titles. If the payment timestamp has two calendar events and the second matches the right category but the first matches the wrong one, the wrong signal wins.
- **No decay of category_rules hits.** A VPA seen 50 times as "Food" then switched to "Health" will need many corrections before the new category overtakes the old one's hit count.
- **No signal is emitted when the caller's `conn` lacks `row_factory = sqlite3.Row`**. If `history_signals()` is called with a plain dict-style row, `payment["counterparty_vpa"]` still works (dicts support string keys), but named-column access on `conn.execute().fetchall()` results would fail. In practice `db.connect()` always sets `row_factory`, but tests that bypass `db.connect()` could trip this.
- **Dead import:** `field` (from `dataclasses`) is imported at the top of the file but never used anywhere in the module. The only dataclass in this file (`Signal`, `ClassificationResult`) does not use `field()` for any of its members. It should be removed.

---

## Developer Notes

- To add a new classifier, implement a function `my_classifier(payment: sqlite3.Row, conn: sqlite3.Connection) -> list[Signal]` and append it to `ALL_CLASSIFIERS`. The ensemble runs them all automatically.
- The `signals` list in `ClassificationResult` is stored in the `agent_events.payload_json` column, so the full reasoning trace for every categorisation is available for later inspection.
- `record_user_categorization()` is the only write path for `category_rules`. The dashboard must call this (not raw SQL) to ensure both VPA and name-token rules are updated together.
- The `_haystack()` helper concatenates `counterparty_name` + `counterparty_vpa` with a space. Merchant patterns that might match a VPA alone (e.g., `swiggy@upi`) will match correctly, but patterns that span the space boundary would never match.
