# `select/candidate_selector.md`

Five-line system prompt for the very first LLM stage of the pipeline: turning a batch of ingested/deduplicated news into a short list of research-worthy "candidate seeds."

## Role in the pipeline
Consumed by `select_candidate()` in `select/__init__.py`. It runs before any causal graph exists — its output (`CandidateSeed`s) becomes the raw material that later stages (`research/`, then graph construction) build on. It explicitly delegates the final pick away from itself: "Do not select a winner; local code ranks and selects" — the model's job is to propose and grade candidates, not choose among them. `select/__init__.py`'s `rank_candidates` function does the actual selection deterministically.

## Expected inputs
`select_candidate()` sends JSON with two keys:
- `extracts` — the `DiscoveryExtract` list (one per ingested news item: headline, text, fetch status, etc.).
- `dedup_groups` — the `DedupGroup` list (clusters of extracts judged to be reporting the same underlying development, with `factual_status`, `agreement`/`disagreement` notes).

The prompt frames the audience explicitly ("an informed Indian equity-market reader") and instructs: never invent a premise or source item ID; distinguish observed fact from sourced forecast, assumption, inference, and estimate; preserve the stated factual status rather than promoting a rumour/proposal/forecast into a fact; require that any proposed "route" name a concrete operating, financial, demand, cost, regulatory, currency, competitive, or valuation mechanism (explicitly rejecting a route that's just "stock price" with no mechanism); and forbid using popularity or emotional intensity as selection criteria. It requires grading exactly seven named dimensions (`grounded_starting_point`, `immediate_effect_plausibility`, `knock_on_potential`, `indian_equity_transmission`, `researchability`, `decision_relevance`, `unresolved_assumptions`) each as `low`/`medium`/`high`.

## Demanded output format
Structured JSON matching `CandidateSelection` (`{"candidates": [CandidateSeed, ...]}`, capped at `MAX_GENERATED_ITEMS["candidates"]`), enforced via `response_json_schema`. Each `CandidateSeed` has `id`, `source_item_ids`, `reported_premise`, `factual_status`, `possible_immediate_effect`, `possible_indian_equity_route`, `grades` (a dict that a `CandidateSeed` field validator requires to contain exactly the seven dimensions listed above — no more, no fewer), `rationale`, `weaknesses`, and `selected` (which the prompt asks to leave unset/false, and which the Python side overwrites regardless).

## Downstream consumer
`select_candidate()` first drops any candidate whose `source_item_ids` is empty or references an item ID not present in the supplied `extracts` (guards against a hallucinated source citation) — silently, with no error surfaced for the dropped candidate specifically. The survivors go to `rank_candidates()`, which scores them from the `grades` dict using a hardcoded low/medium/high weight map, keeps the top 3, and requires at least one of them to be non-"low" on both `grounded_starting_point` and `indian_equity_transmission` — raising `NoViableCandidate` if none qualify. The single best-scoring viable candidate gets `.selected=True`; the prompt's own `selected` field on any candidate is ignored/overwritten.
