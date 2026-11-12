# scheduler.py — Technical Documentation

**Last updated:** 2026-04-27
**Lines of code:** 175
**Language:** Python

---

## What This File Does (Plain English)

`scheduler.py` implements the FSRS-4.5 spaced repetition scheduling algorithm. Given a card's current state and a review rating, it computes the new stability, difficulty, state label, and next review interval. It uses only stdlib — no external ML dependencies. The weights are the FSRS-4.5 reference defaults and are never retrained in the current codebase.

---

## How It Actually Works

### Entry Points

`FSRSScheduler` is instantiated in `app.py`'s `review` command and passed to `run_flashcard_session()`. Its only actively used method is `rate()`.

### Data Flow

```
FSRSScheduler.rate(state: FSRSState, rating: int, now: datetime) → new FSRSState
  
  if state.state == "new" or state.reps == 0:
    [First review branch]
    new_stability = _initial_stability(rating, w)   # w[rating-1]
    new_difficulty = _initial_difficulty(rating, w)
    interval = 1  (again/hard)  OR  round(new_stability)  (good/easy)
    new_state = "relearning"/"learning"/"review"

  else:
    [Subsequent review branch]
    retrievability = _forgetting_curve(elapsed_days, stability)
    new_difficulty = _next_difficulty(d, rating, w)
    if rating == again:
      new_stability = _next_stability_forget(...)
      interval = 1
      new_state = "relearning"
    else:
      new_stability = _next_stability_recall(...)
      interval = round(_fuzz(new_stability))
      new_state = "review"

  lapses += 1 if rating==again AND reps>0 else 0
  next_due = now + timedelta(days=interval)
  return new FSRSState
```

### Key Formulas

- **Forgetting curve**: `R(t) = (1 + FACTOR * t / S)^DECAY` where `DECAY=-0.5`, `FACTOR=19/81`
- **Initial stability**: `w[rating-1]` — the first four weights directly encode per-rating initial stability
- **Initial difficulty**: `w[4] - exp(w[5] * (rating-1)) + 1`, clamped to [1, 10]
- **Difficulty update**: delta toward mean-reversion via `w[6]` and `w[7]`
- **Stability recall**: complex function of S, D, R, rating — applies hard penalty (`w[15]`) and easy bonus (`w[16]`)
- **Stability forget**: `w[11] * D^(-w[12]) * (S+1)^w[13] * exp(w[14]*(1-R))`

### Key Functions / Classes

| Name | What it actually does |
|---|---|
| `DEFAULT_WEIGHTS` | 19-element list of FSRS-4.5 reference weights; used as default if none supplied |
| `_forgetting_curve(elapsed_days, stability)` | Computes retrievability R at elapsed_days given stability S |
| `_initial_stability(rating, w)` | First-review stability: just `w[rating-1]` |
| `_initial_difficulty(rating, w)` | First-review difficulty from rating and w[4]/w[5] |
| `_next_difficulty(d, rating, w)` | Update difficulty using w[6], w[7], and mean-reversion |
| `_next_stability_recall(s, d, r, rating, w)` | Post-review stability when card is recalled |
| `_next_stability_forget(s, d, r, w)` | Post-review stability when card is forgotten |
| `FSRSScheduler.__init__(weights, fuzz_range)` | Sets weights (defaulting to FSRS-4.5 reference) and fuzz multiplier range |
| `FSRSScheduler.rate(state, rating, now)` | Apply a rating and return new FSRSState — the only method called in production |
| `FSRSScheduler._fuzz(stability)` | Multiplies stability by a uniform random value in fuzz_range |
| `FSRSScheduler.schedule_with_fuzz(raw_interval_days)` | Public wrapper around `_fuzz`; not called anywhere in the current code |
| `FSRSScheduler.maybe_retrain(review_history, min_reviews)` | Stub — always returns `None`; retraining is not implemented |

### External Dependencies

- `study_system.types.card.CardRating`, `FSRSState`
- `math`, `random`, `datetime` (all stdlib)

### Error Handling

- `stability <= 0` in `_forgetting_curve`: returns `0.0` (special case guard)
- `stability < 0.1` in output: clamped to `0.1` via `max(0.1, new_stability)` in `rate()`
- No other error handling; invalid `rating` values (outside 1–4) will raise `ValueError` from `CardRating(rating)`

---

## Non-Technical Decisions Embedded in the Code

- **The line `raw_interval = new_stability * math.log(0.9) / math.log(0.9)`** (line 135) is mathematically `raw_interval = new_stability * 1.0 = new_stability`. The `math.log(0.9) / math.log(0.9)` cancels to 1. This appears to be a simplification remnant of the full FSRS interval formula `S * ln(desired_retention) / ln(0.9)`, where `desired_retention = 0.9` makes the ratio 1. The `raw_interval` variable is computed but never used — `interval` is computed from `_fuzz(new_stability)` on the next line.
- **Fuzz range `(0.95, 1.05)`** (±5%): this prevents cards from all coming due on the same day when many cards have the same stability. The range is set in `Config.fuzz_range` and passed to `FSRSScheduler`.
- **`elapsed_days` in the returned state** is set to the old `elapsed_days` value, not updated to reflect actual days elapsed since last review. This is consistent with how it is stored in SQLite — it is a persistent running value, not dynamically computed.
- **`lapses`** increments only when `rating == again AND reps > 0`. A "again" on the very first review does not count as a lapse.
- **`CardRating.hard` value** (`2`) is used as a special case in `_next_stability_recall` with `hard_penalty = w[15]`, and `CardRating.easy` (`4`) uses `easy_bonus = w[16]`. The numeric enum values are directly compared — this coupling between the enum and the algorithm is intentional FSRS design.

---

## Honest Gaps and Risks

- **`elapsed_days` is never dynamically computed from timestamps.** The value in SQLite is whatever was last written. If a card is overdue by 30 days, `elapsed_days` in the row may still be 7 (the scheduled interval). The forgetting curve will compute an optimistic retrievability. The correct approach would be to compute `elapsed = (now - last_reviewed_at).days` at review time.
- **`maybe_retrain()` is a stub** — the comment says "actual gradient-based FSRS optimisation would go here" but it is not implemented. The system will never automatically adapt weights to the user's actual review history.
- **`schedule_with_fuzz(raw_interval_days)`** is defined but not called anywhere in the active code path. It exists for future use.
- **No learning steps**: FSRS-4.5 typically uses short learning steps (1 min, 10 min) for cards in "learning" state before graduating to the review cycle. This implementation goes directly to interval-based scheduling even for the first "good" rating.

---

## Developer Notes

- To change FSRS weights: pass a custom `weights` list to `FSRSScheduler()`. The list must have exactly 19 elements.
- To disable fuzz: pass `fuzz_range=(1.0, 1.0)` to `FSRSScheduler()`.
- The `rate()` method is deterministic given `now` and `weights`, except for the `random.uniform` call in `_fuzz()`. For reproducibility in tests, mock `random.uniform` or pass a fixed seed.
- The FSRS-4.5 reference implementation (py-fsrs project, MIT licence) is the canonical source for weight meanings. This implementation follows that reference.
