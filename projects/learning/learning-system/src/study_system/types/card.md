# types/card.py — Technical Documentation

**Last updated:** 2026-04-27
**Lines of code:** 84
**Language:** Python

---

## What This File Does (Plain English)

`types/card.py` defines the Pydantic models for the flashcard layer: the card itself with its FSRS state, rating enums, review results, and session summaries. These types are shared between `generator.py` (which creates cards), `reviewer.py` and `quiz.py` (which present and rate them), and `sqlite_store.py` (which persists them).

---

## Type Reference

### `CardType` (str Enum)

| Member | `.value` | Meaning |
|---|---|---|
| `flashcard` | `"flashcard"` | Standard front/back card |
| `formula` | `"formula"` | Formula card (same front/back structure, different generation prompt in future) |
| `quiz_mcq` | `"quiz_mcq"` | MCQ card; `back` is a JSON string |
| `quiz_short` | `"quiz_short"` | Short-answer quiz (not currently generated) |

### `FSRSState`

Full FSRS-4.5 card state. All field names mirror FSRS parameter names.

| Field | Type | Default | Meaning |
|---|---|---|---|
| `stability` | `float` | `0.0` | S — expected days to 90% retention |
| `difficulty` | `float` | `5.0` | D — card difficulty (1–10 FSRS scale) |
| `elapsed_days` | `int` | `0` | Days since last review (stored; not computed dynamically) |
| `scheduled_days` | `int` | `0` | Next interval in days |
| `reps` | `int` | `0` | Total review count |
| `lapses` | `int` | `0` | Times rated "again" after first review |
| `state` | `str` | `"new"` | `'new'` / `'learning'` / `'review'` / `'relearning'` |
| `next_due_at` | `Optional[datetime]` | `None` | When to show the card next; None = due immediately |

All 8 fields are mirrored to individual columns in the `cards` SQLite table.

### `CardRating` (int Enum)

| Member | `.value` | Meaning |
|---|---|---|
| `again` | `1` | Forgot; show again soon |
| `hard` | `2` | Recalled with difficulty |
| `good` | `3` | Recalled correctly |
| `easy` | `4` | Recalled effortlessly |

Integer values are stored in `reviews.rating` and used directly in FSRS formulas via `CardRating(rating)`.

### `Card`

A flashcard with full provenance and FSRS state.

| Field | Type | Meaning |
|---|---|---|
| `id` | `str` | UUID (generated at card creation) |
| `concept_id` | `str` | FK to `concepts.id` |
| `front` | `str` | Question / prompt side |
| `back` | `str` | Answer side (or JSON string for quiz_mcq) |
| `source_anchor` | `SourceAnchor` | Where the content comes from |
| `card_type` | `CardType` | Default: `CardType.flashcard` |
| `created_at` | `datetime` | Creation time (default: `datetime.utcnow()`) |
| `model` | `str` | LLM model used for generation |
| `prompt_version` | `str` | Prompt template version string |
| `extraction_id` | `str` | Which extraction produced this card |
| `fsrs` | `FSRSState` | Embedded FSRS state (also mirrored to SQLite columns) |
| `verification_status` | `str` | `'pending'` / `'passed'` / `'failed'` / `'flagged'` |
| `deleted_at` | `Optional[datetime]` | Soft delete timestamp; None = active |

### `ReviewResult`

Result of a single card review — written to `reviews` table.

| Field | Type | Meaning |
|---|---|---|
| `card_id` | `str` | Which card was reviewed |
| `reviewed_at` | `datetime` | Review timestamp (default: now) |
| `rating` | `CardRating` | The rating given |
| `elapsed_days_at_review` | `int` | `FSRSState.elapsed_days` at time of review |
| `stability_before` | `float` | `FSRSState.stability` before update |
| `stability_after` | `float` | `FSRSState.stability` after update |

### `SessionSummary`

Aggregate statistics for one review session.

| Field | Type | Default | Meaning |
|---|---|---|---|
| `cards_reviewed` | `int` | `0` | Total cards shown in session |
| `again_count` | `int` | `0` | Cards rated "again" |
| `hard_count` | `int` | `0` | Cards rated "hard" |
| `good_count` | `int` | `0` | Cards rated "good" |
| `easy_count` | `int` | `0` | Cards rated "easy" |
| `started_at` | `datetime` | now | Session start |
| `ended_at` | `Optional[datetime]` | `None` | Set on session end |

`SessionSummary` is returned by `run_flashcard_session()` but not persisted to SQLite.

---

## Key Invariants

- `Card.fsrs` is the in-memory representation of FSRS state. The same data is mirrored to individual columns in `cards` table. They must be kept in sync via `store.update_card_fsrs()`.
- `Card.verification_status` has four valid values: `'pending'`, `'passed'`, `'failed'`, `'flagged'`. These are strings, not an Enum — any string can be written.
- `Card.back` for `card_type=quiz_mcq` is a JSON string containing `{"choices":..., "correct":..., "explanation":...}`. The `quiz.py` module parses this. The `reviewer.py` module does NOT special-case quiz_mcq cards — it will display the raw JSON as the back.
- `FSRSState.elapsed_days` is stored but not dynamically computed. It reflects the last-stored value, not actual days since last review.

---

## Non-Technical Decisions Embedded in the Code

- **FSRS state embedded in Card**: the `fsrs: FSRSState` field on `Card` is redundant with the individual FSRS columns in SQLite. The `Card` model is used as a transfer object during generation; the SQLite columns are the authoritative state for scheduling. The two must be kept in sync manually.
- **`verification_status` is a plain string**: using `'flagged'` as a status that is neither `'pending'` nor `'passed'` nor `'failed'` is an implicit state. The string is not validated by Pydantic — any value can be written. The `get_due_cards` query only excludes `'failed'`.
- **`deleted_at` soft-delete field**: there is no `delete_card()` method in `SqliteStore`. The field exists for future use. The `get_due_cards` query does filter `deleted_at IS NULL`.
- **`ReviewResult` stores both `stability_before` and `stability_after`**: this enables post-hoc analysis of scheduler performance and is the input data for `FSRSScheduler.maybe_retrain()` when it is eventually implemented.

---

## Developer Notes

- To add a new card type: add a member to `CardType`, create a new generator function in `generator.py`, and add a corresponding display path in `reviewer.py`
- `SourceAnchor` is imported from `types/extraction.py` — `types/card.py` depends on `types/extraction.py`
- `Card.source_anchor.model_dump_json()` is used in `sqlite_store.upsert_card()` to serialise the anchor to JSON for the `source_anchor_json` column
