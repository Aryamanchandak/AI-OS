# `research/claim_extractor.md`

Five-line system prompt for turning fetched source text into candidate atomic claims — the second step of the research cycle, after `gap_analyser.md` decides what to look for and search/fetch has pulled the source pages.

## Role in the pipeline
Consumed by `extract_claims()` in `research/__init__.py`, called once per research cycle after `retrieve_for_tasks` returns a batch of `SourceRecord`s. Its output is not trusted at face value — the prompt itself says so ("Local code will reject any passage that is not an exact normalized substring"), and the calling code enforces exactly that via `consequence_radar.evidence.verify_claims`.

## Expected inputs
`extract_claims()` sends JSON with two keys:
- `tasks` — the `ResearchTask` list that motivated the fetches (so extraction can stay "focused on the named graph tasks," as the prompt puts it).
- `sources` — the `SourceRecord` list, each with `extracted_text` truncated to the first 8000 characters (a tighter cap than the 80,000-character limit `PageFetcher` already applies at fetch time).

The prompt requires: an exact passage copied verbatim for every claim, using only supplied source IDs; classification of each claim as `fact`/`estimate`/`forecast`/`inference`/`assumption` and stance as `supports`/`contradicts`/`context`; no merging of materially different assertions; no invented numbers or sources; and specific guardrails against over-classifying — "an estimate is not an observed fact; a forecast is not a fact; model inference belongs only when the source itself makes that inference."

## Demanded output format
Structured JSON matching `EvidenceClaimDrafts` (`{"claims": [EvidenceClaimDraft, ...]}`), enforced via `response_json_schema`. Each `EvidenceClaimDraft` carries `source_id`, `claim`, `exact_passage`, `claim_type`, `stance`, `concepts`, and optional `geography`/`time_horizon` — notably it has no `id` and no `passage_verified` field; those are added downstream, not by the model.

## Downstream consumer
`extract_claims()` passes the raw `drafts.claims` straight to `consequence_radar.evidence.verify_claims(drafts.claims, sources, start)`. That function looks up each draft's `source_id` against the supplied sources, normalizes both the claimed passage and the source's full extracted text, and only promotes a draft to a full `EvidenceClaim` (assigning it an `id` like `C{n}` and `passage_verified=True`) if the normalized passage is found verbatim inside the source. Anything that references an unknown source, fails the substring check, or fails `EvidenceClaim`'s own field validation is instead recorded as a `RejectedClaim` with a reason — the model's raw output is never treated as ground truth on its own.
