# `select/__init__.py`

Turns a batch of deduplicated news extracts into a shortlist of candidate research seeds, then picks a winner deterministically in Python rather than letting the model choose. This is the first LLM stage of the whole pipeline (runs before any graph exists).

## Main entry points

### `select_candidate(run_id, extracts, groups, model) -> list[CandidateSeed]`
Calls `model.generate(..., prompt_name="select/candidate_selector.md", schema=CandidateSelection)` — no `model_tier` argument, so it runs on the default `"fast"` tier. The payload is `{"extracts": [...], "dedup_groups": [...]}` built from `DiscoveryExtract` and `DedupGroup` lists.

Before ranking, it filters the model's returned candidates: `clean = [c for c in response.candidates if c.source_item_ids and set(c.source_item_ids) <= supplied]`, where `supplied` is the set of `item_id`s actually present in `extracts`. A candidate with no source IDs, or with any source ID the model invented, is silently dropped here — never surfaced as an error, just excluded from ranking. The prompt explicitly forbids the model from picking a winner itself ("Do not select a winner; local code ranks and selects"), so `select_candidate` always defers to `rank_candidates`.

### `rank_candidates(candidates) -> list[CandidateSeed]`
Pure Python, no LLM call. Scores each candidate as a tuple `(gating, total, candidate.id)`:
- `gating = min(WEIGHT[grounded_starting_point], WEIGHT[indian_equity_transmission])` — the worse of these two specific grades, using the hardcoded map `{"low": 0, "medium": 1, "high": 2}`.
- `total = sum(WEIGHT[g] for g in grades.values())` — sum across all seven graded dimensions.

Sorts descending on that tuple (`reverse=True`) and keeps the top 3. Because ties are broken by `candidate.id` and the whole tuple sort is reversed, ties on `(gating, total)` are broken by **reverse-lexicographic candidate ID**, not by input order or any explicit tiebreak field — a minor, easy-to-miss ordering detail.

`viable` is then the subset of that top-3 whose `grounded_starting_point` and `indian_equity_transmission` are both not `"low"` (equivalently, `gating >= 1`, since gating is the min of those two grades' weights — so gating strictly separates viable from non-viable candidates, and the descending sort already puts every viable candidate ahead of every non-viable one before the top-3 cut is applied). If `viable` is empty, raises `NoViableCandidate("no supplied development has both a grounded premise and plausible Indian-equity route")`. Otherwise `winner_id = viable[0].id` (the best-ranked viable candidate), and every candidate in the top-3 gets `.selected` overwritten via `model_copy(update={"selected": c.id == winner_id})` — so even if the model set `selected=True` on some other candidate against instructions, that's discarded here.

**Note on scope:** only the top 3 candidates (by score) are returned at all, so if more than 3 viable candidates exist, the 4th+ are dropped from the result entirely — this doesn't affect which candidate wins (the winner is always the best-scoring viable one, and it's guaranteed to be in the top 3 since it scores at least as well as any excluded viable candidate), but it does limit how many "material alternative" candidates the caller ever sees.

### `class NoViableCandidate(RuntimeError)`
Raised by `rank_candidates` (see above) when no returned/surviving candidate clears the "low" bar on both starting-point groundedness and Indian-equity transmission plausibility. This is the one way `select_candidate` can fail outright rather than degrade gracefully — it propagates uncaught out of this module.

## Connects to
- `consequence_radar.models` — `CandidateSeed`, `CandidateSelection`, `DedupGroup`, `DiscoveryExtract` are the request/response shapes; `CandidateSeed.grades` is a `dict[str, Grade]` validated elsewhere to contain exactly the seven `SELECTION_DIMENSIONS` keys.
- `consequence_radar.providers.model.ModelClient` — the `.generate()` target.
- `consequence_radar.pipeline.__init__` — the sole caller (`from ..select import select_candidate`), which runs it once at the very start of a run, before any research or graph-building begins, on the `DiscoveryExtract`s and `DedupGroup`s produced by the ingest/dedupe stages.

## Test coverage
There is no `test_select.py` (or similarly named test file) anywhere under `src/consequence_radar/select/` — confirmed by directory listing, not assumed. `rank_candidates`'s scoring, tie-breaking, and `NoViableCandidate` path are, as far as the source tree shows, exercised only indirectly (if at all) through pipeline-level tests, not by a dedicated unit test for this module.
