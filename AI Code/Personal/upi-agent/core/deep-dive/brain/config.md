# config.py — Technical Documentation

**Last updated:** 2026-05-03
**Lines of code:** 161
**Language:** Python

---

## What This File Does (Plain English)

This file is the single source of truth for every tunable number and lookup table used by the brain layer. It is a constants-only module — no functions, no classes, no side effects beyond resolving `Path.home()` at import time. Every other brain module reads from here rather than embedding literals in its own logic. Changing how sensitive anomaly detection is, what counts as a recurring payment, or which merchants map to which category requires editing only this file.

---

## How It Actually Works

### Entry Points

Imported by every other brain module via `from . import config`. No callable entry points.

### Data Flow

No data flows through this file. Other modules read its attributes directly.

### State Management

None. All values are module-level constants set once at import time.

### Key Constants

| Name | Type | What it controls |
|---|---|---|
| `DATA_DIR` | `Path` | `~/.upi-agent/` — root for all runtime data files |
| `DB_PATH` | `Path` | `~/.upi-agent/data.db` — SQLite ledger |
| `STORIES_DIR` | `Path` | `~/.upi-agent/stories/` — weekly markdown output |
| `LOG_PATH` | `Path` | `/tmp/upi-agent.log` — log file location |
| `CATEGORIES` | `list[str]` | The 12 canonical spend categories (flat, no subcategories) |
| `CONFIDENCE_THRESHOLD` | `float` | 0.6 — minimum total signal weight before the classifier commits to a category |
| `TRIAGE_CONFIDENCE_THRESHOLD` | `float` | 0.7 — below this the dashboard flags the payment for manual review |
| `HISTORY_VPA_WEIGHT` | `float` | 0.9 — weight when a VPA has 3+ consistent historical hits |
| `HISTORY_VPA_MIN_HITS` | `int` | 3 — minimum VPA history hits to earn the high-confidence weight |
| `HISTORY_TOKEN_WEIGHT` | `float` | 0.5 — weight for a name-token rule match |
| `CALENDAR_WEIGHT` | `float` | 0.6 — weight for a calendar event keyword match |
| `MERCHANT_WEIGHT` | `float` | 0.7 — weight for a hand-curated merchant pattern match |
| `HEURISTIC_WEIGHT` | `float` | 0.3 — weight for amount/time tiebreaker heuristics |
| `MERCHANT_PATTERNS` | `list[tuple[str, str]]` | 45 `(pattern, category)` pairs; lowercased substring match; first-match-wins |
| `CALENDAR_KEYWORDS` | `list[tuple[str, str]]` | 5 `(regex, category)` pairs matched against calendar event titles |
| `NAME_STOP_TOKENS` | `set[str]` | Corporate suffixes and generic words stripped before name-token learning |
| `NEW_COUNTERPARTY_THRESHOLD` | `int` | 3,000 — first payment above this to a never-seen VPA fires an anomaly |
| `Z_THRESHOLD` | `float` | 2.5 — z-score cutoff for a severity-1 (notice) anomaly |
| `Z_HIGH_THRESHOLD` | `float` | 3.5 — z-score cutoff for a severity-2 (warning) anomaly |
| `Z_MIN_HISTORY` | `int` | 10 — minimum data points before z-score fires |
| `Z_LOOKBACK_DAYS` | `int` | 60 — days of history used to compute category mean/stdev |
| `ODD_HOUR_PERCENTILES` | `tuple[int, int]` | (5, 95) — transactions outside this band of the user's hour distribution are flagged |
| `ODD_HOUR_MIN_AMOUNT` | `int` | 500 — odd-hour check only triggers for payments above this |
| `ODD_HOUR_MIN_HISTORY` | `int` | 30 — minimum prior debits needed to build the hour distribution |
| `VELOCITY_COUNT` | `int` | 5 — number of debits within the window that triggers a velocity anomaly |
| `VELOCITY_WINDOW_MIN` | `int` | 10 — the window (minutes) for the velocity count |
| `RECURRING_MIN_OCCURRENCES` | `int` | 3 — minimum appearances before a payment is flagged as recurring |
| `RECURRING_CADENCE_TOLERANCE` | `int` | 4 — days a gap may deviate from 7/14/30 and still count |
| `RECURRING_AMOUNT_TOLERANCE` | `float` | 0.10 — 10% amount variation allowed within a recurring cluster |
| `DEFAULT_BUDGET_WARN_PCT` | `int` | 80 — percentage of a budget cap that triggers a warning event |
| `USE_LLM_NARRATOR` | `bool` | False — set True to let OpenAI rephrase the weekly story opener |
| `OPENAI_MODEL` | `str` | `gpt-4o-mini` — model used for the optional narrator rephrase |

### External Dependencies

- `pathlib.Path` (stdlib only)
- `Path.home()` is resolved at import time. All paths derived from it.

### Error Handling

None. If `Path.home()` fails (containerised environment without a home directory), every brain module import will crash.

---

## Non-Technical Decisions Embedded in the Code

- Two distinct confidence thresholds exist: `CONFIDENCE_THRESHOLD` (0.6) is the bar for writing a category, and `TRIAGE_CONFIDENCE_THRESHOLD` (0.7) is the bar for suppressing the triage flag. A payment classified at 0.65 gets a category written but still appears in the dashboard triage queue.
- `MERCHANT_PATTERNS` is ordered and first-match-wins. "jio postpaid" is listed before any bare "jio" entry because a bare "jio" placed higher would shadow it.
- The category list is explicitly labelled "flat, no subcategories in v1", suggesting hierarchy was considered and consciously deferred.
- `USE_LLM_NARRATOR = False` — the OpenAI SDK is an optional dependency, never exercised unless the developer opts in by changing this constant and setting `OPENAI_API_KEY`.
- `LOG_PATH = /tmp/upi-agent.log` is not inside `DATA_DIR`, so it is not backed up and is lost on reboot.

---

## Honest Gaps and Risks

- The gap between `CONFIDENCE_THRESHOLD` (0.6) and `TRIAGE_CONFIDENCE_THRESHOLD` (0.7) creates a confusing middle state: the system has committed to a category but the dashboard still asks the user to review it. This is probably unintentional.
- `MERCHANT_PATTERNS` will go stale as new Indian apps emerge. There is no mechanism to update it at runtime.
- No cross-validation between `CATEGORIES` and the categories embedded in `MERCHANT_PATTERNS` or `CALENDAR_KEYWORDS`. A typo in a pattern tuple would silently create payments in a non-canonical category that the rest of the system doesn't recognise.
- `LOG_PATH` pointing to `/tmp` means logs are lost on reboot and cannot be used for post-incident analysis.

---

## Developer Notes

- This is the only file to edit when adjusting brain sensitivity. The discipline of never putting magic numbers in module code depends on this convention being maintained.
- When adding a new category: update `CATEGORIES` here AND add patterns to `MERCHANT_PATTERNS` or `CALENDAR_KEYWORDS`. The classifier's `record_user_categorization()` silently rejects categories not in `CATEGORIES`.
- Consider aligning `CONFIDENCE_THRESHOLD` and `TRIAGE_CONFIDENCE_THRESHOLD` so a successfully-classified payment does not also appear in triage.
