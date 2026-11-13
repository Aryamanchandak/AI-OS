# `evidence/__init__.py`

Turns model-proposed `EvidenceClaimDraft`s into either verified `EvidenceClaim`s or `RejectedClaim`s, by checking that each draft's claimed exact quote actually appears in the cited source's extracted text. This is the fact-checking gate between claim-generation (wherever `EvidenceClaimDraft`s are produced — not in this package) and everything downstream that trusts `EvidenceClaim.passage_verified`, notably `report_context.compile_context`.

**`normalize_passage(value)`** collapses all whitespace runs to a single space, strips the ends, and casefolds. Used both on the draft's `exact_passage` and on the full source body before doing a substring check — so verification is whitespace- and case-insensitive but otherwise requires a literal substring match, not fuzzy or semantic matching.

**`verify_claims(drafts, sources, start=1) -> tuple[list[EvidenceClaim], list[RejectedClaim]]`** builds a `source_id -> SourceRecord` map and, for each draft:
- Rejects with reason `"unknown source"` if `draft.source_id` isn't in the map.
- Rejects with reason `"exact passage not found"` if the normalized passage is empty, or is not a substring of the normalized source text.
- Otherwise constructs an `EvidenceClaim` with a freshly minted ID (`f"C{start + len(accepted)}"` — sequential, based on how many claims have already been accepted in *this call*, offset by `start`) and `passage_verified=True`.
- If that `EvidenceClaim` construction raises `pydantic.ValidationError` (e.g. the draft's `claim` field, non-empty in `EvidenceClaimDraft`, was blank after whitespace-only content — `EvidenceClaim.claim` requires `NonEmpty`), it is caught and turned into a rejection with reason `"claim failed validation: {first pydantic error message}"` rather than propagating and failing the whole batch. The comment notes this used to crash the whole run on one bad claim.

ID generation is a real subtlety: IDs are assigned sequentially only among *accepted* claims in this single call, using the `start` parameter as an offset. If `verify_claims` is called multiple times (e.g. once per research task) without the caller tracking and passing forward the correct running `start`, IDs from different calls can collide (both starting at `C1`). Nothing in this file enforces global uniqueness — that's the caller's responsibility.

Input shape: `list[EvidenceClaimDraft]` (`source_id`, `claim`, `exact_passage`, `claim_type`, `stance`, `concepts`, optional `geography`/`time_horizon` — no `id`, no `passage_verified`) plus `list[SourceRecord]`. Output: `list[EvidenceClaim]` (same fields plus `id` and `passage_verified=True`) and `list[RejectedClaim]` (`claim`, `source_id`, `exact_passage`, `reason`) — rejections carry no `id` since they never entered the accepted-claim ID sequence.

Connects downstream to `report_context.compile_context`, which filters on `claim.passage_verified and c.stance` to decide `accepted_claims` vs `contradicting_claims`, and to `quantify`/`challenge` stages (not read here) that presumably cite `EvidenceClaim.id`s as `source_claim_ids`/`supporting_claim_ids`.
