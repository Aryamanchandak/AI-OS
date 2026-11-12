# narrator.py — Technical Documentation

**Last updated:** 2026-05-03
**Lines of code:** 572
**Language:** Python

---

## What This File Does (Plain English)

This file computes, renders, and saves the weekly spending summary. It queries the database for a given ISO week, produces a structured `WeeklyStory` object (with category breakdowns, top merchants, calendar correlations, goal status, and anomalies), renders that object to markdown, and writes the file to disk. Optionally, if `USE_LLM_NARRATOR` is enabled, it asks OpenAI to rephrase only the opening sentence in a more conversational tone. The numbers are always deterministic — the LLM cannot invent them.

---

## How It Actually Works

### Entry Points

- `generate_and_save_weekly(end_date, db_path)` — the full pipeline: compute, render, optionally rephrase, save to disk, emit `agent_events` row. Called by `cli.py story weekly`.
- `weekly_story(end_date, db_path)` — computes the `WeeklyStory` without rendering or saving. Useful for testing.
- `render_markdown(story)` — converts a `WeeklyStory` to a markdown string without any DB access.
- `maybe_rephrase_opener(story, markdown)` — conditionally rewrites the opening paragraph via OpenAI.

### Data Flow

```
generate_and_save_weekly(end_date, db_path)
  → _resolve_end_date(end_date)
      # Sunday after 18:00 or Monday before 12:00 → use as anchor for the just-ended week
  → _week_bounds(end_date)
      # compute Monday 00:00 → next Monday 00:00
  → connect(db_path):
      totals query (total spent, received, count)
      _compute_category_summary(conn, start, end)
          → this week by category (SUM, COUNT)
          → prior week by category (SUM)
          → compute delta_vs_prior_week_pct per category
      _compute_top_merchants(conn, start, end, limit=5)
          → GROUP BY counterparty name, ORDER BY SUM(amount) DESC
      _compute_calendar_correlations(conn, start, end)
          → fetch all debit payments with calendar_events
          → for each CALENDAR_KEYWORDS pattern:
              split days into "has this keyword" vs "doesn't"
              compute avg spend per category on each group
              emit CalendarCorrelation if gap >= 30% and both sides have 3+ days
      _compute_goal_snapshots(conn)
          → JOIN goals + goal_status_cache
          → if cache is missing: evaluate live
      anomaly events in the week (from agent_events table)
      uncategorized debit count
  → build WeeklyStory(...)
  → render_markdown(story)
  → maybe_rephrase_opener(story, markdown)
      → if USE_LLM_NARRATOR=True and OPENAI_API_KEY set:
          extract opening line, call gpt-4o-mini, replace if response non-empty
      → on any failure: return original markdown unchanged
  → write to STORIES_DIR/YYYY-Www.md
  → INSERT OR IGNORE into agent_events (kind='weekly_story')
  → return file path
```

### State Management

No in-module state. The DB is the source of truth. The `STORIES_DIR` on disk is the output store.

### Key Functions / Classes

| Name | What it actually does |
|---|---|
| `weekly_story(end_date, db_path)` | Full data computation; returns WeeklyStory |
| `_resolve_end_date(end_date)` | Adjusts anchor date for "just past Sunday" edge cases |
| `_week_bounds(end_date)` | Returns ISO week Monday 00:00 → next Monday 00:00 |
| `_compute_category_summary(conn, start, end)` | Per-category spend + delta vs prior week |
| `_compute_top_merchants(conn, start, end, limit)` | Top 5 counterparties by spend |
| `_compute_calendar_correlations(conn, start, end)` | Compares category spend on days with vs without keyword-matching calendar events |
| `_compute_goal_snapshots(conn)` | Reads goal status from cache or evaluates live |
| `render_markdown(story)` | Pure function: WeeklyStory → markdown string |
| `_delta_arrow(pct)` | Returns `↑N%`, `↓N%`, `(≈)`, or `(new)` based on delta value |
| `maybe_rephrase_opener(story, markdown)` | Optionally calls OpenAI to rephrase first paragraph |
| `generate_and_save_weekly(end_date, db_path)` | Full pipeline: compute + render + save + emit event |

### WeeklyStory Dataclass

```python
WeeklyStory:
    period_start: date
    period_end: date               # inclusive Sunday
    total_spent: float
    total_received: float
    txn_count: int
    by_category: dict[str, CategorySummary]
    top_merchants: list[dict]      # [{"name", "amount", "txns"}]
    calendar_correlations: list[CalendarCorrelation]
    goals_status: list[GoalStatusSnapshot]
    anomalies: list[dict]          # [{"title", "severity"}]
    uncategorized_count: int
```

### Output Files

Stories are saved to `~/.upi-agent/stories/YYYY-Www.md` (e.g., `2026-W17.md`). The week label uses the ISO week of the `period_end` date (Saturday/Sunday of the week).

### External Dependencies

- `sqlite3`, `json`, `statistics`, `collections`, `datetime`, `re`, `os` (stdlib)
- `brain.config` — reads `STORIES_DIR`, `CALENDAR_KEYWORDS`, `USE_LLM_NARRATOR`, `OPENAI_MODEL`
- `brain.goals` — calls `goals.evaluate()` for live fallback when cache is empty
- `brain.db.connect`
- `openai` SDK — optional, only imported inside `maybe_rephrase_opener()` if `USE_LLM_NARRATOR=True`

### Error Handling

- `_compute_calendar_correlations()` catches `json.JSONDecodeError` and `TypeError` on `calendar_events` per-payment.
- `_compute_goal_snapshots()` falls back to live `goals.evaluate()` if the cache row has no `state` value (e.g., cache not yet populated for a new goal).
- `maybe_rephrase_opener()` catches all exceptions and returns the original markdown on any failure. It also silently returns original if: `USE_LLM_NARRATOR=False`, `OPENAI_API_KEY` not set, or `openai` not installed.
- `generate_and_save_weekly()` has no error handling around file write or DB event insert. If `STORIES_DIR` cannot be created, the `mkdir(parents=True, exist_ok=True)` call raises and propagates.

---

## Non-Technical Decisions Embedded in the Code

- `_resolve_end_date()` has special logic for Sunday evening (after 18:00) and Monday morning (before 12:00). The intent is to capture the "just ended week" when the story job runs at Sunday 20:00 (per the launchd plist). Outside those windows, `_resolve_end_date()` returns `end_date` unchanged — which means running the story on a Tuesday returns the story for the *current incomplete week*, not the completed prior week.
- Calendar correlations require at least 3 data points on each side of the split (days with / days without the keyword). One week of data (7 days) provides at most 7 data points across both groups. With 5 keyword groups and 7 days, most correlations will not have enough data to emit — especially for categories like Health or Entertainment where spending is infrequent.
- The 30% relative gap threshold for calendar correlations is hardcoded in `_compute_calendar_correlations()`, not in `config.py`. This violates the design convention.
- `_compute_goal_snapshots()` has a bug in its live-evaluation fallback: it queries `goals WHERE description = ?` using the description string — not the goal ID. If two goals have the same description, it fetches the first one and evaluates that, which may be the wrong goal.
- The LLM rephrase prompt explicitly says "STRICT RULES: only rephrase, do not invent numbers". This is a soft constraint — the model could still fabricate if it ignores the instruction. The structured data is passed in the prompt as a grounding check but not validated on output.
- The weekly story event in `agent_events` uses `explanation = markdown` (the full markdown document) as the explanation field. This is the largest possible value for that column and means the `agent_events` table stores a full copy of each weekly story.

---

## Honest Gaps and Risks

- **`_resolve_end_date()` returns the current incomplete week** for most weekdays. Running `generate_and_save_weekly()` on a Wednesday produces a story for the current partial week (Mon–now), not last week. The label in the filename would be the current ISO week. This is likely confusing.
- **30% correlation threshold is hardcoded**, not in config. It cannot be tuned without editing this file.
- **Goal snapshot fallback has a description-based lookup bug.** `conn.execute("SELECT * FROM goals WHERE description = ?", (r["description"],)).fetchone()` returns the first matching goal, which may not be the goal whose snapshot is being computed.
- **The story's `anomalies` list is fetched by `created_at`, not by the payment's `occurred_at`.** An anomaly event created on Monday for a Sunday payment would appear in the Monday week's story, not Sunday's. In practice the reactor runs shortly after ingestion so the gap is small, but it's a subtle mismatch.
- **No handling for weeks with zero transactions.** `totals["spent"]` is `None` when there are no rows (SQL aggregate on empty set returns NULL). The `or 0` fallback handles this, but `by_category` will be an empty dict, which the renderer handles with `_No spending this week._`.
- **`re` is only available in this file via a local import inside `_compute_calendar_correlations()`** (`import re as _re`). It is NOT imported at the module top level — so the local import is functionally necessary, not redundant. The `as _re` alias is unnecessary since there is no name conflict at that scope; it adds confusion without preventing anything.
- **Dead imports at the top level:** `Counter` (from `collections`) and `field` (from `dataclasses`) are imported at the top of the file but never used anywhere in the module. They should be removed.

---

## Developer Notes

- The story's primary output path is the file in `STORIES_DIR`. The `agent_events` row (kind=`weekly_story`) serves as an audit trail, not the primary storage — but the `explanation` column contains the full markdown, so the DB has a copy too.
- The `generate_and_save_weekly()` function uses two separate `connect()` blocks: one inside `weekly_story()` and one at the end to insert the `agent_events` row. The file write happens between these two DB connections. If the process crashes after the file write but before the event insert, the file exists but no event is recorded — safe, but the story won't appear in the dashboard's event feed.
- To generate a story for a specific past week: `generate_and_save_weekly(datetime.fromisocalendar(2026, 15, 7, 20, 0, 0))` — pass a Sunday-evening datetime for that week. The `--week` CLI flag does this automatically.
- `maybe_rephrase_opener()` relies on the markdown structure having the H1 on line 0, a blank line on line 1, and the opener paragraph on line 2. If `render_markdown()` ever changes this structure, the rephrase will silently return the original unchanged (the check `if len(lines) < 3 or not lines[0].startswith("#")` guards this).
